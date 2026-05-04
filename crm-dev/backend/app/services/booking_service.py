# app/services/booking_service.py
from typing import Any, Dict, List, Optional, Set
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, cast, Date, Time, or_
from sqlalchemy.orm import selectinload
from app.db.models.booking import Booking, StatusEnum
from app.db.models.restaurant import Restaurant
from app.db.models.table import Table
from app.services.redis_service import RedisService
from app.services.slot_generator import invalidate_slots_cache
from app.services.slot_state_manager import SlotStateManager, BUFFER_BETWEEN_BOOKINGS_MINUTES
from app.services.booking_logic import BOOKING_MIN_DURATION_MINUTES
from app.core.time_utils import get_moscow_now, get_moscow_today
from datetime import datetime, timedelta, date, time
from uuid import uuid4
import json
import structlog
import asyncio
import enum
from app.db.session import AsyncSessionLocal
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, retry_if_exception
from app.db.models.enums import SlotStatus
from app.db.models.slot import TimeSlot

logger = structlog.get_logger(__name__)

# === Telegram Bot (ленивая инициализация) ===
_bot = None

def get_bot():
    global _bot
    if _bot is None:
        try:
            from telegram import Bot
            from app.core.config import settings
            _bot = Bot(token=settings.TELEGRAM_BOT_TOKEN.get_secret_value()) if settings.TELEGRAM_BOT_TOKEN else None
        except Exception as e:
            logger.warning("Telegram import failed", error=str(e))
            _bot = None
    return _bot


# === BOOKING STATUS HISTORY LOGGING ===
async def log_booking_status_change(
    booking_id: int,
    old_status: StatusEnum,
    new_status: StatusEnum,
    changed_by_user_id: Optional[int],
    reason: Optional[str],
    db: AsyncSession
):
    """Логирование изменения статуса бронирования в историю (если таблица существует)"""
    try:
        # Используем SAVEPOINT (nested transaction), чтобы ошибка в логе 
        # не приводила к аборту основной транзакции (InFailedSQLTransactionError)
        async with db.begin_nested():
            from sqlalchemy import text
            query = text("""
                INSERT INTO booking_history 
                (booking_id, old_status, new_status, changed_by_user_id, reason, changed_at)
                VALUES (:booking_id, :old_status, :new_status, :changed_by_user_id, :reason, :changed_at)
            """)
            
            await db.execute(query, {
                "booking_id": booking_id,
                "old_status": old_status.value,
                "new_status": new_status.value,
                "changed_by_user_id": changed_by_user_id,
                "reason": reason,
                "changed_at": get_moscow_now()
            })
            
        logger.info(
            "Booking status change logged",
            booking_id=booking_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_by_user_id=changed_by_user_id
        )
    except Exception as e:
        # Не прерываем основной процесс, если таблица не существует или логирование не удалось
        logger.warning(
            "Failed to log booking status change (non-critical)",
            booking_id=booking_id,
            error=str(e)
        )
        # При возникновении ошибки в begin_nested() произойдет автоматический rollback к savepoint


def _normalize_capacity(total_guests: int, seats_min: Optional[int], seats_max: Optional[int]) -> bool:
    """Проверка соответствия количества гостей диапазону стола."""
    if seats_min is not None and total_guests < seats_min:
        return False
    if seats_max is not None and total_guests > seats_max:
        return False
    return True


async def _get_assigned_table_conflicts(
    restaurant: Optional[Restaurant],
    restaurant_id: int,
    start_datetime: datetime,
    db: AsyncSession,
    exclude_booking_id: Optional[int] = None,
) -> Set[int]:
    """
    Возвращает набор столов, занятых назначенными бронированиями,
    которые пересекаются по времени со слотом start_datetime.
    """
    slot_dt = start_datetime.replace(tzinfo=None) if start_datetime.tzinfo else start_datetime
    target_date = slot_dt.date()

    window_start = datetime.combine(target_date - timedelta(days=1), time.min)
    window_end = datetime.combine(target_date + timedelta(days=1), time.max)

    result = await db.execute(
        select(Booking).where(
            Booking.restaurant_id == restaurant_id,
            Booking.start_datetime >= window_start,
            Booking.start_datetime < window_end,
            Booking.table_id.isnot(None),
            Booking.status.in_(StatusEnum.get_active_statuses()),
        )
    )
    bookings = result.scalars().all()
    if not bookings:
        return set()

    if restaurant is None:
        restaurant = await db.get(Restaurant, restaurant_id)

    conflicts: Set[int] = set()
    for booking in bookings:
        if exclude_booking_id and booking.id == exclude_booking_id:
            continue

        b_start = booking.start_datetime
        b_end = booking.end_datetime
        if b_start and b_start.tzinfo:
            b_start = b_start.replace(tzinfo=None)
        if b_end and b_end.tzinfo:
            b_end = b_end.replace(tzinfo=None)

        if not b_start:
            continue

        if b_end:
            freeze_until = b_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
        elif booking.has_time_limit and booking.time_limit_hours:
            freeze_until = (
                b_start
                + timedelta(hours=booking.time_limit_hours)
                + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
            )
        else:
            booking_day = b_start.date()
            close_dt = (
                SlotStateManager._get_closing_time(restaurant, booking_day)
                if restaurant
                else datetime.combine(booking_day + timedelta(days=1), time(5, 0))
            )
            if close_dt.tzinfo:
                close_dt = close_dt.replace(tzinfo=None)
            freeze_until = close_dt + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)

        if b_start <= slot_dt < freeze_until and booking.table_id:
            conflicts.add(booking.table_id)

    return conflicts


async def _collect_table_states(
    restaurant_id: int,
    db: AsyncSession,
    total_guests: int,
    start_datetime: datetime,
    exclude_booking_id: Optional[int] = None,
) -> tuple[list[Dict[str, Any]], Optional[TimeSlot]]:
    """
    Возвращает информацию о всех активных столах и их доступности для указанного времени.
    """
    date_ = start_datetime.date()
    time_ = start_datetime.time()

    # ОПТИМИЗАЦИЯ: Инициализируем слоты ТОЛЬКО если их ещё нет для этой даты
    # (ранее вызывалось на каждый запрос, вызывая тяжёлую пересчётку)
    existing_slot_check = await db.scalar(
        select(TimeSlot.id).where(
            TimeSlot.restaurant_id == restaurant_id,
            TimeSlot.date == date_,
        ).limit(1)
    )
    if not existing_slot_check:
        await SlotStateManager.initialize_daily_slots(
            restaurant_id=restaurant_id,
            target_date=date_,
            db=db,
        )
        # ИСПРАВЛЕНИЕ: autoflush=False в сессии, поэтому нужен явный flush
        # чтобы созданные слоты стали видны в последующем SELECT FOR UPDATE
        await db.flush()

    slot = await db.scalar(
        select(TimeSlot).where(
            TimeSlot.restaurant_id == restaurant_id,
            TimeSlot.date == date_,
            TimeSlot.time == time_,
        ).with_for_update()  # ИСПРАВЛЕНИЕ: Убрали skip_locked=True для надежности
    )

    restaurant = await db.get(Restaurant, restaurant_id)

    tables_result = await db.execute(
        select(Table).where(
            Table.restaurant_id == restaurant_id,
            Table.is_active.is_(True),
        )
    )
    tables = tables_result.scalars().all()

    assigned_conflicts = await _get_assigned_table_conflicts(
        restaurant=restaurant,
        restaurant_id=restaurant_id,
        start_datetime=start_datetime,
        db=db,
        exclude_booking_id=exclude_booking_id,
    )

    conflicting_table_ids: Set[int] = set()
    if slot and slot.locked_tables:
        conflicting_table_ids.update(slot.locked_tables)
    conflicting_table_ids.update(assigned_conflicts)

    if exclude_booking_id and conflicting_table_ids:
        exclude_booking = await db.get(Booking, exclude_booking_id)
        if exclude_booking and exclude_booking.table_id:
            conflicting_table_ids.discard(exclude_booking.table_id)

    logger.info(
        "Conflict check via TimeSlot",
        time=time_,
        booked_tables_in_slot=slot.booked_tables if slot else None,
        final_conflicting_ids=list(conflicting_table_ids),
        exclude_booking_id=exclude_booking_id,
    )

    table_states: List[Dict[str, Any]] = []
    for table in tables:
        capacity_ok = _normalize_capacity(total_guests, table.seats_min, table.seats_max)
        is_conflicting = table.id in conflicting_table_ids
        is_available = capacity_ok and not is_conflicting

        features = []
        if hasattr(table, "features") and table.features is not None:
            try:
                features = json.loads(table.features) if isinstance(table.features, str) else table.features
            except (json.JSONDecodeError, TypeError):
                features = []

        table_states.append(
            {
                "id": table.id,
                "number": table.number,
                "seats_min": table.seats_min,
                "seats_max": table.seats_max,
                "location_mark": table.location_mark or "",
                "is_active": table.is_active,
                "features": features,
                "capacity_ok": capacity_ok,
                "is_conflicting": is_conflicting,
                "is_available": is_available,
                "status_reason": "capacity"
                if not capacity_ok
                else ("conflict" if is_conflicting else None),
            }
        )

    return table_states, slot


# === ПОДБОР СТОЛОВ ТОЛЬКО ПО ГОСТЯМ (по start_datetime) ===
async def get_suitable_tables(
    restaurant_id: int,
    db: AsyncSession,
    total_guests: int,
    start_datetime: datetime,
    exclude_booking_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Возвращает список подходящих столов на указанное время.
    Учитывает вместимость, забронированные столы в слоте и активные брони.
    """
    try:
        table_states, slot = await _collect_table_states(
            restaurant_id=restaurant_id,
            db=db,
            total_guests=total_guests,
            start_datetime=start_datetime,
            exclude_booking_id=exclude_booking_id,
        )

        time_ = start_datetime.time()
        date_ = start_datetime.date()

        # ИСПРАВЛЕНИЕ: блокируем ТОЛЬКО если слот закрыт администратором (UNAVAILABLE).
        # BOOKED слоты — результат «резервирования» столов под неназначенные брони,
        # но это НЕ должно блокировать создание брони если физически есть свободные столы.
        if slot and slot.status == SlotStatus.UNAVAILABLE:
            logger.info(
                "Slot blocked by admin",
                date=date_,
                time=time_,
                status=slot.status.value,
            )
            return []

        if not slot:
            logger.info(
                "Slot not found",
                date=date_,
                time=time_,
            )
            return []

        suitable = [table for table in table_states if table.get("is_available")]

        logger.info(
            "get_suitable_tables result",
            count=len(suitable),
            time=time_,
            guests=total_guests,
            suitable_tables=[table["number"] for table in suitable],
            excluded_booking=exclude_booking_id,
        )
        return suitable

    except Exception as e:
        logger.error("get_suitable_tables crashed", error=str(e), exc_info=True)
        return []

# === CREATE BOOKING WITH AUTO TABLE ASSIGNMENT ===
def should_retry_booking(exception):
    """Only retry on server errors, not client errors like 409 conflict"""
    if isinstance(exception, HTTPException):
        # Don't retry 4xx client errors (400-499)
        return exception.status_code >= 500
    return False

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=0.1, max=1),
    retry=retry_if_exception(should_retry_booking),
)
async def create_booking_with_tables(
    booking_data,
    db: AsyncSession,
    is_admin: bool = False,
    user_public_id: Optional[int] = None,
    total_guests: Optional[int] = None,
    lock_value: Optional[str] = None,
):
    """
    Создание бронирования с автоматическим подбором столов
    """
    total_guests = total_guests or (booking_data.adults + booking_data.children)
    if total_guests <= 0:
        raise HTTPException(400, "Total guests must be at least 1")

    logger.info(
        "create_booking_with_tables called",
        restaurant_slug=booking_data.restaurant_slug,
        date=booking_data.date.isoformat(),
        time=booking_data.time.strftime("%H:%M"),
        adults=booking_data.adults,
        children=booking_data.children,
        user_public_id=user_public_id,
        is_admin=is_admin,
        has_lock_value=bool(lock_value),
        lock_value_length=len(lock_value) if lock_value else 0
    )

    try:
        # === Получаем ресторан ===
        restaurant = await db.scalar(
            select(Restaurant).where(
                Restaurant.slug == booking_data.restaurant_slug,
                Restaurant.is_published.is_(True)
            )
        )
        if not restaurant:
            raise HTTPException(404, "Restaurant not found")

        restaurant_id = restaurant.id
        moscow_today = get_moscow_today()
        
        # Проверка максимальной даты бронирования
        if booking_data.date > moscow_today + timedelta(days=restaurant.max_booking_days):
            raise HTTPException(400, "Date too far in the future")

        # === Idempotency check ===
        if booking_data.idempotency_key:
            existing = await db.scalar(
                select(Booking).where(Booking.idempotency_key == booking_data.idempotency_key)
            )
            if existing:
                logger.info("Idempotency key found, returning existing booking", booking_id=existing.id)
                return existing

        # === БЛОКИРОВКА СЛОТА - ЕДИНАЯ ЛОГИКА ДЛЯ ВСЕХ ===
        start_dt = datetime.combine(booking_data.date, booking_data.time)
        time_str = booking_data.time.strftime('%H:%M')
        
        # ЕДИНЫЙ ключ блокировки (без total_guests — избегаем race condition)
        redis_key = f"slot_lock:{restaurant_id}:{booking_data.date}:{time_str}"
        
        logger.info(
            "Checking slot lock", 
            redis_key=redis_key,
            provided_lock_value=lock_value[:10] + "..." if lock_value else None,
            total_guests=total_guests
        )

        # ЕДИНАЯ ЛОГИКА БЛОКИРОВКИ
        # Админам не мешаем создавать — пропускаем строгую проверку блокировки.
        if not is_admin:
            if lock_value:
                current_lock = await RedisService.call("get", redis_key)
                logger.info(
                    "Current lock value in Redis", 
                    current_lock=current_lock[:10] + "..." if current_lock else None,
                    key_exists=bool(current_lock)
                )
                if current_lock != lock_value:
                    logger.warning(
                        "Slot lock verification FAILED", 
                        expected=lock_value[:10] + "..." if lock_value else None,
                        actual=current_lock[:10] + "..." if current_lock else None
                    )
                    raise HTTPException(409, "Slot locked by another user")
                else:
                    logger.info("✅ Slot lock verified successfully")
            else:
                existing_lock = await RedisService.call("get", redis_key)
                if existing_lock:
                    logger.warning("Slot already locked (no lock_value provided)")
                    raise HTTPException(409, "Slot locked by another user")
        else:
            # Для администратора: мягкая логика — если ключ отсутствует, можно продолжать.
            # При наличии lock_value и пустом ключе — установим его для консистентности.
            if lock_value and RedisService.redis:
                current_lock = await RedisService.call("get", redis_key)
                if not current_lock:
                    await RedisService.call("set", redis_key, lock_value, for_write=True)
                    logger.info("Admin set slot lock for consistency", key=redis_key)

        # === Подбор столов ===
        suitable_tables = await get_suitable_tables(
            restaurant_id=restaurant_id,
            db=db,
            total_guests=total_guests,
            start_datetime=start_dt,
        )
        
        logger.info(
            "Suitable tables found for booking", 
            count=len(suitable_tables),
            time=time_str,
            total_guests=total_guests,
            is_admin=is_admin
        )
        
        # ЕДИНАЯ ЛОГИКА: если нет подходящих столов - ошибка для всех
        if not suitable_tables:
            if is_admin:
                # Для админа: попробуем включить неактивные столы (могли быть деактивированы sync)
                logger.warning(
                    "No active suitable tables for admin booking, trying all tables including inactive",
                    time=time_str,
                    total_guests=total_guests,
                )
                all_tables_result = await db.execute(
                    select(Table).where(
                        Table.restaurant_id == restaurant_id,
                    )
                )
                all_tables = all_tables_result.scalars().all()
                # Фильтруем по вместимости вручную
                suitable_tables = [
                    {
                        "id": t.id,
                        "number": t.number,
                        "seats_min": t.seats_min,
                        "seats_max": t.seats_max,
                        "location_mark": t.location_mark or "",
                        "is_active": t.is_active,
                        "features": [],
                        "capacity_ok": True,
                        "is_conflicting": False,
                        "is_available": True,
                    }
                    for t in all_tables
                    if t.seats_min <= total_guests <= t.seats_max
                ]
                if suitable_tables:
                    logger.info(
                        "Found inactive tables for admin booking",
                        count=len(suitable_tables),
                    )
                    # Reactivate these tables
                    for t in all_tables:
                        if t.seats_min <= total_guests <= t.seats_max and not t.is_active:
                            t.is_active = True
                            logger.info("Reactivated table for admin booking", table_id=t.id, number=t.number)
                    await db.flush()

            if not suitable_tables:
                # Очищаем блокировку если нет столов
                if lock_value and RedisService.redis:
                    await RedisService.call("delete", redis_key, for_write=True)
                    logger.info("Cleared slot lock due to no suitable tables")
                raise HTTPException(400, "Нет подходящих столов на это время")

        # === Определяем время закрытия ===
        closing_dt = None
        for item in restaurant.schedule:
            if item.get("day") == booking_data.date.weekday():
                close_str = item.get("close")
                if close_str:
                    try:
                        close_time = datetime.strptime(close_str, "%H:%M").time()
                        closing_dt = datetime.combine(booking_data.date, close_time)
                        # Обработка работы после полуночи
                        open_time = datetime.strptime(item.get("open", "00:00"), "%H:%M").time()
                        if close_time <= open_time:
                            closing_dt += timedelta(days=1)
                        break
                    except ValueError as e:
                        logger.error("Error parsing close time", error=str(e), close_str=close_str)
                        continue

        if not closing_dt:
            # Дефолтное время закрытия
            closing_dt = datetime.combine(booking_data.date + timedelta(days=1), time(5, 0))

        # === Определяем end_datetime ===
        # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: если end_time НЕ указан, оставляем end_dt = None
        # Это будет означать бронь "до закрытия", но мы проверим доступность
        if getattr(booking_data, 'end_time', None):
            end_dt = datetime.combine(booking_data.date, booking_data.end_time)
            # Обработка окончания после полуночи
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
        else:
            # НЕ устанавливаем автоматически до закрытия!
            # Сначала проверим доступность
            end_dt = None

        # === ПРОВЕРКА ДОСТУПНОСТИ ДЛЯ БРОНЕЙ "ДО ЗАКРЫТИЯ" ===
        if end_dt is None:
            # Пользователь НЕ указал end_time → хочет до закрытия
            # Проверяем, свободен ли хотя бы один стол на ВСЁ время от start_dt до closing_dt
            logger.info(
                "Checking availability for until-closing booking",
                start=start_dt.isoformat(),
                closing=closing_dt.isoformat()
            )
            
            # Получаем все брони, которые пересекаются с [start_dt, closing_dt]
            overlapping_bookings_result = await db.execute(
                select(Booking).where(
                    Booking.restaurant_id == restaurant_id,
                    Booking.start_datetime >= start_dt - timedelta(hours=24),
                    Booking.start_datetime < closing_dt,
                    Booking.status.in_([
                        StatusEnum.pending,
                        StatusEnum.pending_review,
                        StatusEnum.confirmed,
                        StatusEnum.assigned,
                        StatusEnum.arrived,
                    ])
                )
            )
            overlapping_bookings = overlapping_bookings_result.scalars().all()
            
            # Фильтруем брони, которые реально пересекаются с нашим окном
            # Учитываем буфер между бронями — стол недоступен ещё BUFFER минут после end_datetime
            conflicting_bookings = []
            for b in overlapping_bookings:
                b_end = b.end_datetime or closing_dt
                b_end_with_buffer = b_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
                # Бронь пересекается если начинается до closing_dt И заканчивается (с буфером) после start_dt
                if b.start_datetime < closing_dt and b_end_with_buffer > start_dt:
                    conflicting_bookings.append(b)
            
            # Вспомогательная функция для проверки конкуренции за столы
            def _competes_for_same_tables(b_total: int, suitable_tables: list) -> bool:
                return any(t.get("seats_min") <= b_total <= t.get("seats_max") for t in suitable_tables)

            # Множество ID подходящих столов для быстрой проверки
            suitable_table_ids = {t.get("id") for t in suitable_tables}

            # Занятые конкретные столы (назначенные брони)
            occupied_table_ids: Set[int] = set()
            # Количество пересекающихся броней той же вместимости, без назначенного стола
            overlapping_same_capacity_unassigned = 0
            for b in conflicting_bookings:
                b_total_guests = (b.adults or 0) + (b.children or 0)
                if b.table_id and b.table_id in suitable_table_ids:
                    occupied_table_ids.add(b.table_id)
                elif not b.table_id and _competes_for_same_tables(b_total_guests, suitable_tables):
                    # Бронь ПОДХОДЯЩЕЙ вместимости без назначенного стола — резервирует одно место в группе
                    overlapping_same_capacity_unassigned += 1

            # Количество свободных мест в группе вместимости
            assigned_free_count = len(suitable_tables) - len(occupied_table_ids)
            free_capacity_count = assigned_free_count - overlapping_same_capacity_unassigned
            
            # Свободные столы на весь интервал (по идентификаторам назначенных столов)
            free_tables_till_closing = [t for t in suitable_tables if t.get("id") not in occupied_table_ids]
            
            if free_capacity_count <= 0:
                logger.warning(
                    "No tables available till closing",
                    start=start_dt.isoformat(),
                    occupied_assigned_count=len(occupied_table_ids),
                    overlapping_same_capacity_unassigned=overlapping_same_capacity_unassigned,
                    total_suitable=len(suitable_tables)
                )
                raise HTTPException(
                    409, 
                    "Нет свободных столов до закрытия на это время. Пожалуйста, выберите время окончания бронирования."
                )
            
            logger.info(
                "Tables available till closing",
                free_count=free_capacity_count,
                free_table_ids=[t.get("id") for t in free_tables_till_closing]
            )
            
            # Если всё ок - устанавливаем end_dt = closing_dt
            end_dt = closing_dt
        
        # === Проверка минимальной длительности ===
        min_end = start_dt + timedelta(minutes=BOOKING_MIN_DURATION_MINUTES)
        if end_dt and end_dt < min_end:
            raise HTTPException(400, "Минимальная длительность — 1 час 45 минут")
        
        # Ограничиваем максимальное время закрытием
        if end_dt and closing_dt and end_dt > closing_dt:
            end_dt = closing_dt

        # === Определяем статус ===
        status = StatusEnum.pending
        if not is_admin and booking_data.date == moscow_today:
            if restaurant.last_booking_time:
                try:
                    cutoff = datetime.strptime(restaurant.last_booking_time.strip(), "%H:%M").time()
                    if get_moscow_now().time() > cutoff:
                        status = StatusEnum.pending_review
                except ValueError:
                    # Защита от кривых данных
                    if get_moscow_now().time() >= time(18, 0):
                        status = StatusEnum.pending_review
            # Если last_booking_time = null → остаётся pending (нормальная бронь)

        # === Создание брони ===
        booking = Booking(
            restaurant_id=restaurant_id,
            start_datetime=start_dt,
            end_datetime=end_dt,
            adults=booking_data.adults,
            children=booking_data.children,
            name=booking_data.name,
            phone=booking_data.phone,
            wishes=booking_data.wishes,
            status=status,
            table_id=None,  # Автоматический подбор позже
            idempotency_key=booking_data.idempotency_key or str(uuid4()),
            user_public_id=user_public_id,
        )
        
        db.add(booking)
        await db.flush()  # Получаем ID брони

        await db.commit()
        await db.refresh(booking)

        logger.info(
            "Booking created successfully",
            booking_id=booking.id,
            table_id=booking.table_id,
            status=booking.status.value,
            is_admin=is_admin
        )

        # === Очистка блокировки после успешного создания ===
        if lock_value and RedisService.redis:
            current_lock = await RedisService.call("get", redis_key)
            if current_lock == lock_value:
                await RedisService.call("delete", redis_key, for_write=True)
                logger.info("✅ Slot lock cleared after successful booking", key=redis_key)
            else:
                logger.warning("Lock value changed during booking process", 
                              expected=lock_value[:10] + "...",
                              actual=current_lock[:10] + "..." if current_lock else None)

        # === Обновление состояния слотов ===
        try:
            await SlotStateManager.initialize_daily_slots(
                restaurant_id=restaurant_id,
                target_date=booking_data.date,
                db=db
            )
            await invalidate_slots_cache(restaurant_id, booking_data.date)
            
            # Публикация обновления
            await publish_booking_update(booking, restaurant)
            
            logger.info("Slot state updated after booking creation")
            
        except Exception as e:
            logger.error("Failed to update slot state", error=str(e), exc_info=True)

        return booking

    except HTTPException:
        await db.rollback()
        # Освобождаем блокировку при ошибке
        if lock_value and RedisService.redis:
            await RedisService.call("delete", redis_key, for_write=True)
            logger.info("Slot lock cleared due to error", key=redis_key)
        raise
        
    except Exception as e:
        await db.rollback()
        logger.error("Booking creation failed", error=str(e), exc_info=True)
        # Освобождаем блокировку при неожиданной ошибке
        if lock_value and RedisService.redis:
            await RedisService.call("delete", redis_key, for_write=True)
            logger.info("Slot lock cleared due to unexpected error", key=redis_key)
        raise HTTPException(500, "Booking creation failed")


# === UPDATE BOOKING STATUS (ADMIN) ===
async def update_booking_service(booking_id: int, update_data, db: AsyncSession, admin_user_id: int = None):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")

    old_status = booking.status
    
    # Валидация перехода статуса
    if update_data.status:
        if update_data.status == old_status:
            logger.info("Status update skipped (same status)", booking_id=booking_id, status=old_status.value)
        elif not StatusEnum.can_transition_to(old_status, update_data.status):
            logger.warning(
                "Invalid status transition attempted",
                booking_id=booking_id,
                old_status=old_status.value,
                new_status=update_data.status.value,
                admin_user_id=admin_user_id
            )
            raise HTTPException(
                400, 
                f"Cannot transition from {old_status.value} to {update_data.status.value}"
            )
        
        booking.status = update_data.status
        
        # Освобождение стола при завершающих статусах
        if update_data.status in [StatusEnum.completed, StatusEnum.cancelled, StatusEnum.no_show]:
            if booking.table_id:
                old_table_id = booking.table_id
                booking.table_id = None
                logger.info(
                    "Table released on booking completion",
                    booking_id=booking_id,
                    table_id=old_table_id,
                    new_status=update_data.status.value
                )
        
        # Логирование изменения статуса (необязательно)
        try:
            await log_booking_status_change(
                booking_id=booking_id,
                old_status=old_status,
                new_status=update_data.status,
                changed_by_user_id=admin_user_id,
                reason=getattr(update_data, 'status_change_reason', None),
                db=db
            )
        except Exception as log_error:
            logger.warning(
                "Failed to log status change (non-critical)",
                booking_id=booking_id,
                error=str(log_error)
            )
        
        if update_data.status == StatusEnum.confirmed and not booking.table_id:
            booking.status = StatusEnum.assigned

    if update_data.wishes is not None:
        booking.wishes = update_data.wishes

    if update_data.has_time_limit is not None:
        booking.has_time_limit = update_data.has_time_limit

    if update_data.time_limit_hours is not None:
        booking.time_limit_hours = update_data.time_limit_hours

    await db.commit()
    await db.refresh(booking)

    # === ОБНОВЛЕНИЕ СОСТОЯНИЯ СЛОТОВ ===
    # После любого обновления брони (статус, время, столы) нужно пересчитать слоты
    try:
        booking_date = booking.start_datetime.date() if booking.start_datetime else None
        if booking_date:
            await SlotStateManager.initialize_daily_slots(
                restaurant_id=booking.restaurant_id,
                target_date=booking_date,
                db=db
            )
            await invalidate_slots_cache(booking.restaurant_id, booking_date)
            await SlotStateManager._publish_slot_update(booking.restaurant_id, booking_date)
    except Exception as e:
        logger.error("Failed to update slot state after booking update", error=str(e))

    result = await db.execute(select(Restaurant).where(Restaurant.id == booking.restaurant_id))
    restaurant = result.scalar_one_or_none()
    if restaurant:
        await publish_booking_update(booking, restaurant)

    return booking

# === DELETE BOOKING (ADMIN) ===
async def delete_booking_service(booking_id: int, db: AsyncSession):
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")

    result = await db.execute(select(Restaurant).where(Restaurant.id == booking.restaurant_id))
    restaurant = result.scalar_one_or_none()

    # Извлекаем дату и время из start_datetime (booking.date/time не существуют в модели)
    booking_date = booking.start_datetime.date() if booking.start_datetime else None
    booking_time = booking.start_datetime.time() if booking.start_datetime else None
    restaurant_id = booking.restaurant_id  # Сохраняем до delete — после commit объект detached

    # === ИСПРАВЛЕНИЕ: cancel_booking не нужен — initialize_daily_slots ниже пересчитает всё ===

    await db.delete(booking)
    await db.commit()

    # === Пересчитываем состояние слотов после удаления брони ===
    # ИСПРАВЛЕНО: используем сохранённый restaurant_id (booking detached после commit)
    try:
        if booking_date:
            await SlotStateManager.initialize_daily_slots(
                restaurant_id=restaurant_id,
                target_date=booking_date,
                db=db
            )
            await SlotStateManager._invalidate_cache(restaurant_id, booking_date)
            await SlotStateManager._publish_slot_update(restaurant_id, booking_date)
    except Exception as e:
        logger.error("Failed to update slot state after booking deletion", error=str(e))

    if restaurant and booking_date:
        await invalidate_slots_cache(restaurant.id, booking_date)
        await publish_booking_update(booking, restaurant, deleted=True)

    return None

# === ASSIGN TABLE TO BOOKING ===
async def assign_table_to_booking(booking_id: int, table_id: int, db: AsyncSession):
    """Назначение стола бронированию администратором"""
    result = await db.execute(select(Booking).where(Booking.id == booking_id))
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.table_id:
        raise HTTPException(409, "Table already assigned")

    if not booking.start_datetime:
        raise HTTPException(400, "Booking start time is not defined")

    booking_date = booking.start_datetime.date()
    booking_time = booking.start_datetime.time()

    # Проверяем, что стол существует и активен
    result = await db.execute(
        select(Table).where(
            and_(
                Table.id == table_id,
                Table.restaurant_id == booking.restaurant_id,
                Table.is_active.is_(True)
            )
        )
    )
    table = result.scalar_one_or_none()
    if not table:
        raise HTTPException(404, "Table not found or not available")

    # Проверяем конфликты (уже назначенные столы) С УЧЁТОМ ПЕРЕСЕЧЕНИЯ ВРЕМЕНИ
    active_statuses = [
        StatusEnum.pending,
        StatusEnum.pending_review,
        StatusEnum.confirmed,
        StatusEnum.assigned,
        StatusEnum.arrived
    ]
    
    # Получаем все активные брони на этот стол
    conflict_result = await db.execute(
        select(Booking).where(
            and_(
                Booking.restaurant_id == booking.restaurant_id,
                Booking.table_id == table_id,
                Booking.status.in_(active_statuses),
                Booking.id != booking_id
            )
        )
    )
    existing_bookings = conflict_result.scalars().all()
    
    # Определяем временной интервал текущей брони
    current_start = booking.start_datetime
    current_end = booking.end_datetime
    if not current_end:
        # Если нет end_datetime — считаем до закрытия (или +4 часа как fallback)
        restaurant_obj = await db.get(Restaurant, booking.restaurant_id)
        if restaurant_obj:
            current_end = SlotStateManager._get_closing_time(restaurant_obj, booking_date)
            if current_end.tzinfo:
                current_end = current_end.replace(tzinfo=None)
        else:
            current_end = current_start + timedelta(hours=4)
    
    # Проверяем пересечение с каждой существующей бронью
    for existing in existing_bookings:
        e_start = existing.start_datetime
        e_end = existing.end_datetime
        if not e_end:
            if existing.has_time_limit and existing.time_limit_hours:
                e_end = e_start + timedelta(hours=existing.time_limit_hours)
            else:
                restaurant_obj = restaurant_obj if 'restaurant_obj' in dir() else await db.get(Restaurant, booking.restaurant_id)
                if restaurant_obj:
                    e_end = SlotStateManager._get_closing_time(restaurant_obj, e_start.date())
                    if e_end.tzinfo:
                        e_end = e_end.replace(tzinfo=None)
                else:
                    e_end = e_start + timedelta(hours=4)
        
        # Добавляем буфер между бронями
        e_end_with_buffer = e_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
        current_end_with_buffer = current_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
        
        # Проверяем пересечение: (A.start < B.end + buffer) AND (A.end + buffer > B.start)
        if current_start < e_end_with_buffer and current_end_with_buffer > e_start:
            raise HTTPException(409, "Table already booked for this time slot")

    # --- ГЛАВНОЕ ИЗМЕНЕНИЕ ---
    # При назначении стола, мы **не изменяем available_table_count**,
    # потому что место в категории уже было зарезервировано при создании заявки.
    # Мы просто фиксируем table_id.
    booking.table_id = table_id
    booking.status = StatusEnum.assigned
    await db.commit()
    await db.refresh(booking)

    # Пересчитываем слоты для UI
    try:
        await SlotStateManager.initialize_daily_slots(
            restaurant_id=booking.restaurant_id,
            target_date=booking_date,
            db=db
        )
        await SlotStateManager._invalidate_cache(booking.restaurant_id, booking_date)
        await SlotStateManager._publish_slot_update(booking.restaurant_id, booking_date)
    except Exception as e:
        logger.error("Failed to update slot state after table assignment", error=str(e))

    # Публикуем обновление
    restaurant = await db.get(Restaurant, booking.restaurant_id)
    if restaurant:
        await publish_booking_update(booking, restaurant)
    return booking

async def publish_booking_update(booking: Booking, restaurant: Restaurant, deleted: bool = False):
    """Публикация обновления бронирования через Redis для WebSocket."""
    if not RedisService.redis:
        return

    # Сохраняем данные заранее для использования в except блоке
    booking_id = booking.id
    restaurant_slug = restaurant.slug
    
    try:
        # ИСПРАВЛЕНО: При удалении НЕ пытаемся перечитать бронь из БД — она уже удалена
        if deleted:
            booking_start_date = booking.start_datetime.date().isoformat() if booking.start_datetime else None
            # Включаем данные брони в событие для корректных уведомлений в ботах
            booking_data = {
                "id": booking_id,
                "start_datetime": booking.start_datetime.isoformat() if booking.start_datetime else None,
                "end_datetime": booking.end_datetime.isoformat() if booking.end_datetime else None,
                "name": booking.name,
                "phone": booking.phone,
                "adults": booking.adults,
                "children": booking.children or 0,
                "status": booking.status.value if booking.status else "cancelled",
                "table_id": booking.table_id,
                "cancelled_by": "admin",
            }
            payload = {
                "type": "booking_deleted",
                "booking": booking_data,
                "booking_id": booking_id,
                "date": booking_start_date,
                "restaurant_slug": restaurant_slug
            }
            await RedisService.call("publish", "booking_updates", json.dumps(payload, ensure_ascii=False, default=str), for_write=True)
            logger.info("Published booking deletion", booking_id=booking_id, restaurant=restaurant_slug)
            return

        # ИСПРАВЛЕНО: Используем async сессию вместо sync (SyncSessionLocal блокировал event loop)
        async with AsyncSessionLocal() as async_db:
            # Получаем свежие данные брони
            fresh_booking = await async_db.get(Booking, booking_id)
            if not fresh_booking:
                return
                
            # Получаем номер стола
            table_number = None
            if fresh_booking.table_id:
                table = await async_db.get(Table, fresh_booking.table_id)
                table_number = table.number if table else None

            # Получаем название ресторана и расписание
            restaurant_name = restaurant.name if restaurant else None
            fresh_restaurant = None
            if not restaurant_name:
                fresh_restaurant = await async_db.get(Restaurant, fresh_booking.restaurant_id)
                restaurant_name = fresh_restaurant.name if fresh_restaurant else "Бар"
            else:
                fresh_restaurant = await async_db.get(Restaurant, fresh_booking.restaurant_id)
            
            # Получаем время закрытия на дату бронирования
            closing_time = None
            if fresh_restaurant:
                opening_hours = fresh_restaurant.get_opening_hours(fresh_booking.start_datetime.date())
                closing_time = opening_hours.get('close')
            
            # Подготовка данных для фронтенда
            booking_data = {
                "id": fresh_booking.id,
                "restaurant_id": fresh_booking.restaurant_id,
                "restaurant_name": restaurant_name,
                "name": fresh_booking.name,
                "phone": fresh_booking.phone,
                "adults": fresh_booking.adults,
                "children": fresh_booking.children or 0,
                "date": fresh_booking.start_datetime.date().isoformat(),
                "time": fresh_booking.start_datetime.time().strftime("%H:%M"),
                "end_time": fresh_booking.end_datetime.time().strftime("%H:%M") if fresh_booking.end_datetime else None,
                "closing_time": closing_time,
                "status": fresh_booking.status.value,
                "table_id": fresh_booking.table_id,
                "table_number": table_number,
                "wishes": fresh_booking.wishes,
                "created_at": fresh_booking.created_at.isoformat() if fresh_booking.created_at else None,
                "suitable_tables_json": fresh_booking.suitable_tables_json,
            }

        booking_start_date = booking.start_datetime.date().isoformat()
        booking_created_at = booking.created_at
        
        if deleted:
            payload = {
                "type": "booking_deleted",
                "booking_id": booking_id,
                "date": booking_start_date,
                "restaurant_slug": restaurant_slug
            }
        else:
            payload = {
                "type": "booking_created" if booking_created_at and (datetime.now().timestamp() - booking_created_at.timestamp()) < 10 else "booking_update",
                "booking": booking_data,
                "date": booking_start_date,
                "restaurant_slug": restaurant_slug
            }

        # ИСПРАВЛЕНИЕ: Публикуем в ОБЩИЙ канал "booking_updates" вместо "booking_updates:{restaurant.slug}"
        await RedisService.call("publish", "booking_updates", json.dumps(payload, default=str), for_write=True)
        
        logger.info(
            "Booking update published",
            booking_id=booking_id,
            type=payload["type"],
            restaurant_slug=restaurant_slug,
            channel="booking_updates"
        )

    except Exception as e:
        logger.error("Error publishing booking update", error=str(e), booking_id=booking_id, exc_info=True)

async def publish_booking_created(booking: Booking, restaurant: Restaurant, db: AsyncSession):
    """Публикация события создания бронирования"""
    suitable_tables = await get_suitable_tables(
        restaurant_id=booking.restaurant_id,
        db=db,
        total_guests=booking.adults + (booking.children or 0),
        start_datetime=booking.start_datetime,
        exclude_booking_id=booking.id
    )

    table_number = None
    if booking.table_id:
        table_number = (await db.execute(
            select(Table.number).where(Table.id == booking.table_id)
        )).scalar_one_or_none()

    booking_data = {
        "id": booking.id,
        "start_datetime": booking.start_datetime.isoformat(),
        "end_datetime": booking.end_datetime.isoformat() if booking.end_datetime else None,
        "adults": booking.adults,
        "children": booking.children,
        "name": booking.name,
        "phone": booking.phone,
        "status": booking.status.value,
        "table_id": booking.table_id,
        "table_number": table_number,
        "suitable_tables_json": json.dumps(suitable_tables),
        "user_public_id": booking.user_public_id,
    }

    payload = {
        "type": "booking_created",
        "booking": booking_data,
        "restaurant_slug": restaurant.slug,
        "restaurant_id": restaurant.id,
    }
    
    # ИСПРАВЛЕНИЕ: Публикуем в ОБЩИЙ канал "booking_updates"
    await RedisService.call("publish", "booking_updates", json.dumps(payload, ensure_ascii=False, default=str), for_write=True)
    
    logger.info(
        "Booking created event published", 
        booking_id=booking.id, 
        channel="booking_updates"
    )


async def publish_booking_cancelled(booking: Booking, restaurant: Restaurant, db: AsyncSession, cancelled_by: str = "user"):
    """Публикация события отмены бронирования"""
    table_number = None
    if booking.table_id:
        table_number = (await db.execute(
            select(Table.number).where(Table.id == booking.table_id)
        )).scalar_one_or_none()

    booking_data = {
        "id": booking.id,
        "start_datetime": booking.start_datetime.isoformat(),
        "end_datetime": booking.end_datetime.isoformat() if booking.end_datetime else None,
        "adults": booking.adults,
        "children": booking.children,
        "name": booking.name,
        "phone": booking.phone,
        "status": booking.status.value,
        "table_id": booking.table_id,
        "table_number": table_number,
        "user_public_id": booking.user_public_id,
        "cancelled_by": cancelled_by,
    }

    payload = {
        "type": "booking_cancelled",
        "booking": booking_data,
        "restaurant_slug": restaurant.slug,
        "restaurant_id": restaurant.id,
    }
    
    await RedisService.call("publish", "booking_updates", json.dumps(payload, ensure_ascii=False, default=str), for_write=True)
    
    logger.info(
        "Booking cancelled event published", 
        booking_id=booking.id,
        cancelled_by=cancelled_by,
        channel="booking_updates"
    )


async def publish_booking_delay_notification(booking: Booking, restaurant: Restaurant, db: AsyncSession, delay_minutes: int = None):
    """Публикация уведомления об опоздании"""
    table_number = None
    if booking.table_id:
        table_number = (await db.execute(
            select(Table.number).where(Table.id == booking.table_id)
        )).scalar_one_or_none()

    booking_data = {
        "id": booking.id,
        "start_datetime": booking.start_datetime.isoformat(),
        "end_datetime": booking.end_datetime.isoformat() if booking.end_datetime else None,
        "adults": booking.adults,
        "children": booking.children,
        "name": booking.name,
        "phone": booking.phone,
        "status": booking.status.value,
        "table_id": booking.table_id,
        "table_number": table_number,
        "user_public_id": booking.user_public_id,
        "delay_minutes": delay_minutes,
    }

    payload = {
        "type": "booking_delay",
        "booking": booking_data,
        "restaurant_slug": restaurant.slug,
        "restaurant_id": restaurant.id,
    }
    
    await RedisService.call("publish", "booking_updates", json.dumps(payload, ensure_ascii=False, default=str), for_write=True)
    
    logger.info(
        "Booking delay notification published", 
        booking_id=booking.id,
        delay_minutes=delay_minutes,
        channel="booking_updates"
    )

# === Утилита: сериализация дат ===
def _serialize_dates(data: dict):
    # Сериализуем даты и время
    for key in ["date", "created_at", "updated_at", "extended_until", "cleaning_started_at", "reservation_end_time"]:
        if isinstance(data.get(key), (date, datetime)):
            data[key] = data[key].isoformat()
    
    # Сериализуем time объекты
    for key in ["time", "end_time"]:
        if isinstance(data.get(key), time):
            data[key] = data[key].strftime("%H:%M:%S")

async def get_suitable_tables_for_booking(booking_id: int, db: AsyncSession) -> Dict[str, Any]:
    """Получить информацию о подходящих и занятых столах для существующей брони"""
    try:
        # Получаем бронь (без загрузки связанных объектов)
        result = await db.execute(
            select(Booking).where(Booking.id == booking_id)
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(404, "Booking not found")

        table_states, slot = await _collect_table_states(
            restaurant_id=booking.restaurant_id,
            db=db,
            total_guests=booking.adults + (booking.children or 0),
            start_datetime=booking.start_datetime,
            exclude_booking_id=booking_id,
        )

        suitable_tables = [table for table in table_states if table.get("is_available")]
        suitable_table_ids = [table["id"] for table in suitable_tables]

        booking.suitable_tables_json = (
            json.dumps(suitable_table_ids) if suitable_table_ids else None
        )
        await db.commit()

        logger.info(
            "Returning suitable tables with time conflict check",
            booking_id=booking_id,
            tables_count=len(suitable_tables),
        )
        return {
            "all_tables": table_states,
            "suitable_tables": suitable_tables,
            "available_table_ids": suitable_table_ids,
            "total_tables": len(table_states),
            "slot_status": slot.status.value if slot else None,
        }

    except Exception as e:
        logger.error("Error getting suitable tables for booking", error=str(e), exc_info=True)
        return {
            "all_tables": [],
            "suitable_tables": [],
            "available_table_ids": [],
            "total_tables": 0,
            "slot_status": None,
        }
