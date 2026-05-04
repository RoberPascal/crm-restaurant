import asyncio
import json
from datetime import datetime, timedelta, date, time, timezone
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models.slot import TimeSlot
from app.db.models.table import Table
from app.db.models.restaurant import Restaurant
from app.db.models.booking import Booking, StatusEnum
from app.db.models.enums import SlotStatus
from app.services.redis_service import RedisService
from app.services.slot_broadcast import broadcast_slots_update
import structlog

logger = structlog.get_logger(__name__)

BUFFER_BETWEEN_BOOKINGS_MINUTES = 15


class SlotStateManager:
    @staticmethod
    async def initialize_daily_slots(restaurant_id: int, target_date: date, db: AsyncSession):
        """Полная инициализация слотов на день — работает с start_datetime / end_datetime"""
        logger.info("Initializing daily slots", restaurant_id=restaurant_id, date=target_date.isoformat())

        restaurant = (await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))).scalar_one_or_none()
        if not restaurant:
            logger.warning("Restaurant not found", restaurant_id=restaurant_id)
            return

        # === Активные столы ===
        tables = (await db.execute(
            select(Table).where(Table.restaurant_id == restaurant_id, Table.is_active.is_(True))
        )).scalars().all()
        if not tables:
            logger.info("No active tables", restaurant_id=restaurant_id)
            return

        table_ids = [t.id for t in tables]

        # === Генерация временных слотов ===
        time_slots = await SlotStateManager._generate_time_slots(restaurant, target_date)
        if not time_slots:
            logger.info("No working hours on this day", restaurant_id=restaurant_id, date=target_date)
            return

        closing_datetime = SlotStateManager._get_closing_time(restaurant, target_date)

        # === ИСПРАВЛЕНИЕ: Создаем datetime без часового пояса ===
        start_of_day = datetime.combine(target_date, time.min)
        end_of_day = datetime.combine(target_date, time.max)
        
        # Альтернативный вариант: явно убираем часовой пояс если он есть
        # start_of_day = datetime.combine(target_date, time.min).replace(tzinfo=None)
        # end_of_day = datetime.combine(target_date, time.max).replace(tzinfo=None)

        # === Все активные брони на эту дату (с учётом оверлапа) ===
        from sqlalchemy import or_
        bookings = (await db.execute(
            select(Booking).where(
                Booking.restaurant_id == restaurant_id,
                # ПРАВКА ОВЕРЛАПА: Брони, которые КАСАЮТСЯ этого дня.
                Booking.start_datetime < end_of_day,
                or_(
                    Booking.end_datetime > start_of_day,
                    Booking.end_datetime.is_(None)
                ),
                Booking.status.in_([
                    StatusEnum.pending,
                    StatusEnum.pending_review,
                    StatusEnum.confirmed,
                    StatusEnum.assigned,
                    StatusEnum.arrived,
                ])
            )
        )).scalars().all()

        # === ОПТИМИЗАЦИЯ: Предварительно загружаем все существующие слоты на этот день ===
        existing_slots_result = await db.execute(
            select(TimeSlot).where(
                TimeSlot.restaurant_id == restaurant_id,
                TimeSlot.date == target_date
            )
        )
        existing_slots_map = {s.time: s for s in existing_slots_result.scalars().all()}

        slots_created = 0
        slots_updated = 0

        for slot_time in time_slots:
            # ИСПРАВЛЕНИЕ: Создаем datetime без часового пояса для слота
            slot_dt = datetime.combine(target_date, slot_time)

            assigned_booked = set()
            unassigned_count = 0

            for b in bookings:
                # ИСПРАВЛЕНИЕ: Нормализуем часовые пояса бронирований
                b_start = b.start_datetime
                b_end = b.end_datetime
                
                # Если datetime имеет часовой пояс, преобразуем его в naive (без часового пояса)
                if b_start and b_start.tzinfo:
                    b_start = b_start.replace(tzinfo=None)
                if b_end and b_end.tzinfo:
                    b_end = b_end.replace(tzinfo=None)

                # До какого времени блокирует бронь
                if b_end:
                    freeze_until = b_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
                elif b.has_time_limit and b.time_limit_hours:
                    freeze_until = b_start + timedelta(hours=b.time_limit_hours) + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
                else:
                    # До закрытия + буфер
                    close_naive = closing_datetime
                    if closing_datetime.tzinfo:
                        close_naive = closing_datetime.replace(tzinfo=None)
                    freeze_until = close_naive + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)

                if b_start <= slot_dt < freeze_until:
                    if b.table_id:
                        assigned_booked.add(b.table_id)
                    else:
                        unassigned_count += 1

            # Резервируем столы под неназначенные брони
            booked_tables = list(assigned_booked)
            remaining = unassigned_count
            for tid in table_ids:
                if remaining <= 0:
                    break
                if tid not in booked_tables:
                    booked_tables.append(tid)
                    remaining -= 1

            available_count = len(table_ids) - len(booked_tables)
            status = SlotStatus.BOOKED if available_count == 0 else SlotStatus.AVAILABLE

            # Обновляем/создаём слот (теперь из мапы, без N+1)
            existing = existing_slots_map.get(slot_time)

            if existing:
                existing.table_ids = table_ids
                existing.booked_tables = booked_tables
                existing.available_table_count = available_count
                existing.total_table_count = len(table_ids)
                # ИСПРАВЛЕНИЕ: Мы НЕ перезаписываем статус, если он был установлен вручную как UNAVAILABLE
                if existing.status != SlotStatus.UNAVAILABLE:
                    existing.status = status
                slots_updated += 1
            else:
                slot = TimeSlot(
                    restaurant_id=restaurant_id,
                    date=target_date,
                    time=slot_time,
                    table_ids=table_ids,
                    booked_tables=booked_tables,
                    available_table_count=available_count,
                    total_table_count=len(table_ids),
                    status=status,
                )
                db.add(slot)
                slots_created += 1

        # ИСПРАВЛЕНИЕ: Нужен flush() чтобы новые слоты были видны в последующих запросах
        # (autoflush=False в сессии, поэтому без явного flush SELECT не найдёт добавленные объекты)
        await db.flush()
        
        await SlotStateManager._invalidate_cache(restaurant_id, target_date)
        await SlotStateManager._publish_slot_update(restaurant_id, target_date)

        logger.info(
            "Slots initialized",
            restaurant_id=restaurant_id,
            date=target_date.isoformat(),
            created=slots_created,
            updated=slots_updated,
            total=len(time_slots)
        )

    @staticmethod
    async def _generate_time_slots(restaurant: Restaurant, target_date: date) -> List[time]:
        try:
            logger.info("Generating time slots",
                        restaurant_id=restaurant.id,
                        restaurant_slug=restaurant.slug,
                        date=target_date,
                        schedule=restaurant.schedule)

            if not restaurant.schedule:
                logger.warning("Empty schedule", restaurant_id=restaurant.id)
                return []

            schedule_data = restaurant.schedule
            if isinstance(schedule_data, str):
                try:
                    schedule_data = json.loads(schedule_data)
                except json.JSONDecodeError:
                    logger.error("Failed to parse schedule JSON", schedule=schedule_data)
                    return []

            if not isinstance(schedule_data, list):
                logger.error("Schedule is not a list", type=type(schedule_data))
                return []

            day_idx = target_date.weekday()
            schedule_item = next((item for item in schedule_data if isinstance(item, dict) and item.get('day') == day_idx), None)
            if not schedule_item:
                logger.info("Restaurant closed on this day", restaurant_id=restaurant.id, date=target_date, day_of_week=day_idx)
                return []

            open_time_str = schedule_item.get('open')
            close_time_str = schedule_item.get('close')
            if not open_time_str or not close_time_str:
                logger.error("Missing open/close time", open=open_time_str, close=close_time_str)
                return []

            open_time = datetime.strptime(open_time_str, "%H:%M").time()
            close_time = datetime.strptime(close_time_str, "%H:%M").time()

            # УДАЛЕНА фильтрация по last_booking_time - теперь делается на клиенте
            # Генерируем слоты до времени закрытия ресторана

            current_dt = datetime.combine(target_date, open_time)
            if close_time < open_time:
                end_dt = datetime.combine(target_date + timedelta(days=1), close_time)
            else:
                end_dt = datetime.combine(target_date, close_time)

            slot_interval = 15
            slots = []

            while current_dt < end_dt:
                slots.append(current_dt.time())
                current_dt += timedelta(minutes=slot_interval)

            logger.info("Successfully generated slots",
                        count=len(slots),
                        first_slot=slots[0].strftime("%H:%M") if slots else None,
                        last_slot=slots[-1].strftime("%H:%M") if slots else None,
                        time_range=f"{open_time_str}-{close_time_str}")
            return slots

        except Exception as e:
            logger.error("Error generating time slots", error=str(e), restaurant_id=restaurant.id, exc_info=True)
            return []

    @staticmethod
    async def _invalidate_cache(restaurant_id: int, target_date: date):
        """Invalidate all slot cache keys for this restaurant+date (including per-guest keys)."""
        from app.services.slot_generator import invalidate_slots_cache
        await invalidate_slots_cache(restaurant_id, target_date)

    @staticmethod
    async def _publish_slot_update(restaurant_id: int, target_date: date):
        await broadcast_slots_update(restaurant_id, target_date)

    @staticmethod
    def _get_closing_time(restaurant: Restaurant, target_date: date) -> datetime:
        try:
            schedule_data = restaurant.schedule
            if isinstance(schedule_data, str):
                schedule_data = json.loads(schedule_data)
            if not isinstance(schedule_data, list):
                return datetime.combine(target_date + timedelta(days=1), time(5, 0))

            day_idx = target_date.weekday()
            item = next((i for i in schedule_data if isinstance(i, dict) and i.get('day') == day_idx), None)
            if not item or not item.get('close'):
                return datetime.combine(target_date + timedelta(days=1), time(5, 0))

            close_time = datetime.strptime(item['close'], "%H:%M").time()
            open_time = datetime.strptime(item.get('open', "00:00"), "%H:%M").time()

            if close_time < open_time:
                return datetime.combine(target_date + timedelta(days=1), close_time)
            return datetime.combine(target_date, close_time)
        except Exception as e:
            logger.error("Error getting closing time", error=str(e))
            return datetime.combine(target_date + timedelta(days=1), time(5, 0))

    @staticmethod
    async def cancel_booking(restaurant_id: int, date: date, time: time, table_id: int, db: AsyncSession):
        await SlotStateManager.initialize_daily_slots(restaurant_id, date, db)
        await SlotStateManager._invalidate_cache(restaurant_id, date)
        await SlotStateManager._publish_slot_update(restaurant_id, date)

    @staticmethod
    async def release_slot_without_table(restaurant_id: int, date: date, time: time, db: AsyncSession):
        await SlotStateManager.initialize_daily_slots(restaurant_id, date, db)
        await SlotStateManager._invalidate_cache(restaurant_id, date)
        await SlotStateManager._publish_slot_update(restaurant_id, date)