"""
Автоматизация жизненного цикла бронирований
- Завершение броней после end_datetime
- Маркировка no-show для неявившихся гостей
- Уведомления персоналу о скорых бронированиях
"""
import asyncio
from datetime import datetime, timedelta
from typing import List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal, async_engine
from app.db.models.booking import Booking, StatusEnum
from app.db.models.restaurant import Restaurant
from app.core.time_utils import get_moscow_now
from app.services.redis_service import RedisService
from app.services.slot_state_manager import SlotStateManager
from app.core.config import settings
import structlog

logger = structlog.get_logger(__name__)

# Константы
NO_SHOW_GRACE_PERIOD_MINUTES = 15  # Опоздание до маркировки no-show
UPCOMING_BOOKING_ALERT_MINUTES = 30  # За сколько минут уведомлять персонал
CHECK_INTERVAL_SECONDS = 60  # Как часто проверять
MAX_CONCURRENT_OPERATIONS = 5  # Максимум одновременных операций в БД
BATCH_SIZE = 50  # Размер батча для обработки


class BookingLifecycleService:
    """Сервис для автоматического управления жизненным циклом бронирований"""
    
    def __init__(self):
        self.is_running = False
        self._shutdown_event = asyncio.Event()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_OPERATIONS)  # Ограничение одновременных опер
    
    async def start(self):
        """Запуск фоновой задачи"""
        if self.is_running:
            logger.warning("Booking lifecycle service already running")
            return
        
        self.is_running = True
        logger.info("Starting booking lifecycle automation service")
        
        # Запускаем все задачи параллельно
        await asyncio.gather(
            self._auto_complete_bookings_loop(),
            self._auto_mark_no_show_loop(),
            self._send_upcoming_alerts_loop(),
            return_exceptions=True
        )
    
    async def stop(self):
        """Остановка сервиса"""
        logger.info("Stopping booking lifecycle automation service")
        self._shutdown_event.set()
        self.is_running = False
    
    # ==================== АВТОЗАВЕРШЕНИЕ БРОНЕЙ ====================
    
    async def _auto_complete_bookings_loop(self):
        """Цикл автоматического завершения бронирований"""
        while not self._shutdown_event.is_set():
            try:
                await self._complete_ended_bookings()
            except Exception as e:
                logger.error("Error in auto-complete loop", error=str(e), exc_info=True)
            
            # Ждем до следующей проверки
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=CHECK_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass
    
    async def _complete_ended_bookings(self):
        """
        Находит и завершает бронирования со статусом 'arrived',
        у которых прошло end_datetime
        """
        async with self._semaphore:  # Контролируем одновременный доступ к БД
            async with AsyncSessionLocal() as db:
                try:
                    # Используем осознанные/наивные даты корректно: для БД (naive), для вычислений/логов (aware)
                    now_aware = get_moscow_now()
                    now_naive = now_aware.replace(tzinfo=None)
                    
                    # Находим брони в статусе arrived, которые закончились
                    result = await db.execute(
                        select(Booking)
                        .where(
                            Booking.status == StatusEnum.arrived,
                            Booking.end_datetime.isnot(None),
                            Booking.end_datetime <= now_naive
                        )
                    )
                    bookings_to_complete = result.scalars().all()
                    
                    if not bookings_to_complete:
                        return
                    
                    logger.info(
                        "Auto-completing ended bookings",
                        count=len(bookings_to_complete)
                    )
                    
                    # Обрабатываем батчами для избежания переполнения памяти
                    for i in range(0, len(bookings_to_complete), BATCH_SIZE):
                        batch = bookings_to_complete[i:i+BATCH_SIZE]
                        completed_bookings = []
                        
                        for booking in batch:
                            try:
                                old_status = booking.status
                                booking.status = StatusEnum.completed
                                
                                # Освобождаем стол и слот
                                table_id_before = booking.table_id
                                if booking.table_id:
                                    booking.table_id = None
                                
                                completed_bookings.append((booking, old_status, table_id_before))
                                
                                logger.info(
                                    "Booking auto-completed",
                                    booking_id=booking.id,
                                    old_status=old_status.value,
                                    new_status=booking.status.value
                                )
                                
                            except Exception as e:
                                logger.error(
                                    "Failed to prepare booking completion",
                                    booking_id=booking.id,
                                    error=str(e)
                                )
                        
                        # ИСПРАВЛЕНО: Один commit на весь батч вместо commit на каждую заявку
                        try:
                            await db.commit()
                        except Exception as e:
                            await db.rollback()
                            logger.error("Failed to commit completed bookings batch", error=str(e))
                            continue
                        
                        # Публикуем события после commit
                        for booking, old_status, table_id_before in completed_bookings:
                            await self._publish_status_change(booking, old_status)
                            # Освобождаем слот через SlotStateManager
                            try:
                                if table_id_before:
                                    await SlotStateManager.cancel_booking(
                                        restaurant_id=booking.restaurant_id,
                                        date=booking.start_datetime.date(),
                                        time=booking.start_datetime.time(),
                                        table_id=table_id_before,
                                        db=db
                                    )
                                else:
                                    await SlotStateManager.release_slot_without_table(
                                        restaurant_id=booking.restaurant_id,
                                        date=booking.start_datetime.date(),
                                        time=booking.start_datetime.time(),
                                        db=db
                                    )
                            except Exception as slot_err:
                                logger.error(
                                    "Failed to release slot after auto-complete",
                                    booking_id=booking.id,
                                    error=str(slot_err)
                                )
                        
                        # Небольшая пауза между батчами
                        await asyncio.sleep(0.1)
                
                except Exception as e:
                    logger.error("Error completing bookings", error=str(e), exc_info=True)
    
    # ==================== АВТОМАРКИРОВКА NO-SHOW ====================
    
    async def _auto_mark_no_show_loop(self):
        """Цикл автоматической маркировки no-show"""
        while not self._shutdown_event.is_set():
            try:
                await self._mark_no_show_bookings()
            except Exception as e:
                logger.error("Error in no-show loop", error=str(e), exc_info=True)
            
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=CHECK_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass
    
    async def _mark_no_show_bookings(self):
        """
        Находит и маркирует как no_show бронирования, 
        где гость не явился через 15 минут после начала
        """
        async with self._semaphore:  # Контролируем одновременный доступ к БД
            async with AsyncSessionLocal() as db:
                try:
                    # now_aware — для вычислений; *_naive — для сравнений в БД
                    now_aware = get_moscow_now()
                    grace_cutoff_aware = now_aware - timedelta(minutes=NO_SHOW_GRACE_PERIOD_MINUTES)
                    grace_cutoff_naive = grace_cutoff_aware.replace(tzinfo=None)
                    
                    # Находим брони, которые должны были начаться, но гость не пришел
                    result = await db.execute(
                        select(Booking)
                        .where(
                            Booking.status.in_([
                                StatusEnum.pending,
                                StatusEnum.confirmed,
                                StatusEnum.assigned
                            ]),
                            Booking.start_datetime <= grace_cutoff_naive
                        )
                    )
                    bookings_to_mark = result.scalars().all()
                    
                    if not bookings_to_mark:
                        return
                    
                    logger.info(
                        "Auto-marking no-show bookings",
                        count=len(bookings_to_mark)
                    )
                    
                    # Обрабатываем батчами
                    for i in range(0, len(bookings_to_mark), BATCH_SIZE):
                        batch = bookings_to_mark[i:i+BATCH_SIZE]
                        marked_bookings = []
                        
                        for booking in batch:
                            try:
                                old_status = booking.status
                                booking.status = StatusEnum.no_show
                                
                                # Освобождаем стол
                                table_id_before = booking.table_id
                                if booking.table_id:
                                    booking.table_id = None
                                
                                marked_bookings.append((booking, old_status, table_id_before))
                                
                                # Преобразуем наивное время из БД в aware для корректной математики
                                from app.core.time_utils import to_moscow_time
                                booking_start_aware = to_moscow_time(booking.start_datetime)
                                minutes_late = int((now_aware - booking_start_aware).total_seconds() / 60)
                                logger.info(
                                    "Booking marked as no-show",
                                    booking_id=booking.id,
                                    old_status=old_status.value,
                                    start_datetime=booking.start_datetime.isoformat(),
                                    minutes_late=minutes_late
                                )
                                
                            except Exception as e:
                                logger.error(
                                    "Failed to prepare no-show marking",
                                    booking_id=booking.id,
                                    error=str(e)
                                )
                        
                        # ИСПРАВЛЕНО: Один commit на весь батч вместо commit на каждую заявку
                        try:
                            await db.commit()
                        except Exception as e:
                            await db.rollback()
                            logger.error("Failed to commit no-show batch", error=str(e))
                            continue
                        
                        # Публикуем события после commit
                        for booking, old_status, table_id_before in marked_bookings:
                            await self._publish_status_change(booking, old_status)
                            # Освобождаем слот через SlotStateManager
                            try:
                                if table_id_before:
                                    await SlotStateManager.cancel_booking(
                                        restaurant_id=booking.restaurant_id,
                                        date=booking.start_datetime.date(),
                                        time=booking.start_datetime.time(),
                                        table_id=table_id_before,
                                        db=db
                                    )
                                else:
                                    await SlotStateManager.release_slot_without_table(
                                        restaurant_id=booking.restaurant_id,
                                        date=booking.start_datetime.date(),
                                        time=booking.start_datetime.time(),
                                        db=db
                                    )
                            except Exception as slot_err:
                                logger.error(
                                    "Failed to release slot after no-show",
                                    booking_id=booking.id,
                                    error=str(slot_err)
                                )
                        
                        # Небольшая пауза между батчами
                        await asyncio.sleep(0.1)
                
                except Exception as e:
                    logger.error("Error marking no-show", error=str(e), exc_info=True)
    
    # ==================== УВЕДОМЛЕНИЯ ПЕРСОНАЛУ ====================
    
    async def _send_upcoming_alerts_loop(self):
        """Цикл отправки уведомлений о скорых бронированиях"""
        while not self._shutdown_event.is_set():
            try:
                await self._send_upcoming_booking_alerts()
            except Exception as e:
                logger.error("Error in upcoming alerts loop", error=str(e), exc_info=True)
            
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=CHECK_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass
    
    async def _send_upcoming_booking_alerts(self):
        """
        Отправляет уведомления персоналу о бронированиях,
        которые начнутся через 30 минут
        """
        if not RedisService.redis:
            return
        
        async with self._semaphore:  # Контролируем одновременный доступ к БД
            async with AsyncSessionLocal() as db:
                try:
                    # now_aware — для вычислений/логов; *_naive — для фильтров БД
                    now_aware = get_moscow_now()
                    alert_window_start_aware = now_aware + timedelta(minutes=UPCOMING_BOOKING_ALERT_MINUTES - 2)
                    alert_window_end_aware = now_aware + timedelta(minutes=UPCOMING_BOOKING_ALERT_MINUTES + 2)
                    alert_window_start_naive = alert_window_start_aware.replace(tzinfo=None)
                    alert_window_end_naive = alert_window_end_aware.replace(tzinfo=None)
                    
                    # Находим брони, которые скоро начнутся
                    result = await db.execute(
                        select(Booking)
                        .options(selectinload(Booking.restaurant))
                        .where(
                            Booking.status.in_([
                                StatusEnum.confirmed,
                                StatusEnum.assigned
                            ]),
                            Booking.start_datetime >= alert_window_start_naive,
                            Booking.start_datetime <= alert_window_end_naive
                        )
                    )
                    upcoming_bookings = result.scalars().all()
                    
                    if not upcoming_bookings:
                        return
                    
                    # Обрабатываем батчами
                    for i in range(0, len(upcoming_bookings), BATCH_SIZE):
                        batch = upcoming_bookings[i:i+BATCH_SIZE]
                        
                        for booking in batch:
                            # Проверяем, не отправляли ли уже уведомление
                            alert_key = f"booking:upcoming_alert:{booking.id}"
                            
                            if await RedisService.call("exists", alert_key):
                                continue
                            
                            # Отправляем уведомление
                            await self._publish_upcoming_alert(booking)
                            
                            # Маркируем как отправленное (на 2 часа)
                            await RedisService.call(
                                "setex", alert_key, 7200, "sent",
                                for_write=True
                            )
                            
                            from app.core.time_utils import to_moscow_time
                            start_aware = to_moscow_time(booking.start_datetime)
                            start_in_minutes = int((start_aware - now_aware).total_seconds() / 60)
                            logger.info(
                                "Upcoming booking alert sent",
                                booking_id=booking.id,
                                restaurant_id=booking.restaurant_id,
                                start_in_minutes=start_in_minutes
                            )
                        
                        # Небольшая пауза между батчами
                        await asyncio.sleep(0.1)
                
                except Exception as e:
                    logger.error("Error sending upcoming alerts", error=str(e), exc_info=True)
    
    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================
    
    async def _publish_status_change(self, booking: Booking, old_status: StatusEnum):
        """Публикация изменения статуса в Redis"""
        if not RedisService.redis:
            return
        
        try:
            from app.services.booking_service import publish_booking_update
            from app.db.models.restaurant import Restaurant
            
            async with AsyncSessionLocal() as db:
                restaurant = await db.get(Restaurant, booking.restaurant_id)
                if restaurant:
                    await publish_booking_update(booking, restaurant)
        
        except Exception as e:
            logger.error(
                "Failed to publish status change",
                booking_id=booking.id,
                error=str(e)
            )
    
    async def _publish_upcoming_alert(self, booking: Booking):
        """Публикация уведомления о скором бронировании"""
        if not RedisService.redis:
            return
        
        try:
            # Публикуем событие в канал CRM для уведомления персонала
            alert_data = {
                "type": "upcoming_booking_alert",
                "booking_id": booking.id,
                "restaurant_id": booking.restaurant_id,
                "restaurant_slug": booking.restaurant.slug if booking.restaurant else None,
                "name": booking.name,
                "phone": booking.phone,
                "total_guests": booking.adults + (booking.children or 0),
                "start_datetime": booking.start_datetime.isoformat(),
                "table_id": booking.table_id,
                "status": booking.status.value,
                "minutes_until": UPCOMING_BOOKING_ALERT_MINUTES
            }
            
            import json as _json
            await RedisService.call(
                "publish",
                f"crm_booking:{booking.restaurant_id}",
                _json.dumps(alert_data, default=str),
                for_write=True
            )
            
            logger.info(
                "Published upcoming booking alert",
                booking_id=booking.id,
                minutes_until=UPCOMING_BOOKING_ALERT_MINUTES
            )
        
        except Exception as e:
            logger.error(
                "Failed to publish upcoming alert",
                booking_id=booking.id,
                error=str(e)
            )


# Глобальный экземпляр сервиса
_lifecycle_service: BookingLifecycleService = None


async def start_booking_lifecycle_service():
    """Запуск сервиса автоматизации"""
    global _lifecycle_service
    
    if _lifecycle_service is None:
        _lifecycle_service = BookingLifecycleService()
    
    await _lifecycle_service.start()


async def stop_booking_lifecycle_service():
    """Остановка сервиса"""
    global _lifecycle_service
    
    if _lifecycle_service:
        await _lifecycle_service.stop()


def get_lifecycle_service() -> BookingLifecycleService:
    """Получение экземпляра сервиса"""
    return _lifecycle_service
