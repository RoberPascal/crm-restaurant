from typing import List, Dict, Any, Optional
from datetime import date, time, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.db.models.restaurant import Restaurant
from app.db.models.table import Table
from app.db.models.booking import Booking, StatusEnum
from app.db.models.slot import TimeSlot
from app.db.models.enums import SlotStatus
from app.core.time_utils import get_moscow_now, MOSCOW_TZ
from app.services.booking_logic import BOOKING_MIN_DURATION_MINUTES, BUFFER_BETWEEN_BOOKINGS_MINUTES
from app.services.slot_state_manager import SlotStateManager
from app.services.redis_service import RedisService
import structlog
import json

logger = structlog.get_logger(__name__)


async def get_available_slots_for_frontend(
    restaurant: Restaurant,
    target_date: date,
    db: AsyncSession,
    total_guests: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃР»РѕС‚С‹ РґР»СЏ С„СЂРѕРЅС‚РµРЅРґР°.
    РўРµРїРµСЂСЊ РїСЂРѕРІРµСЂСЏРµС‚ РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ РЅР° Р’РЎРЃ РјРёРЅРёРјР°Р»СЊРЅРѕРµ РѕРєРЅРѕ РІСЂРµРјРµРЅРё Р±СЂРѕРЅРёСЂРѕРІР°РЅРёСЏ.
    РќР• С„РёР»СЊС‚СЂСѓРµС‚ РїРѕ last_booking_time - СЌС‚Рѕ РґРµР»Р°РµС‚СЃСЏ РЅР° РєР»РёРµРЅС‚Рµ.
    РћРџРўРРњРР—РђР¦РРЇ: РљСЌС€РёСЂСѓРµРј СЂРµР·СѓР»СЊС‚Р°С‚ РІ Redis РЅР° 10 СЃРµРєСѓРЅРґ.
    """
    # === РљР­РЁРР РћР’РђРќРР•: РџСЂРѕРІРµСЂСЏРµРј Redis РєСЌС€ ===
    cache_key = f"slots:{restaurant.id}:{target_date.isoformat()}:{total_guests or 'all'}"
    try:
        cached = await RedisService.call("get", cache_key)
        if cached:
            logger.debug("Slots cache hit", key=cache_key)
            return json.loads(cached)
    except Exception as e:
        logger.debug("Slots cache read error", error=str(e))

    moscow_now = get_moscow_now()
    is_today = target_date == moscow_now.date()

    # === 1. РџСЂРѕРІРµСЂСЏРµРј, РЅРµ Р·Р°РєСЂС‹С‚ Р»Рё РґРµРЅСЊ РїРѕР»РЅРѕСЃС‚СЊСЋ ===
    closed_slots_result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.restaurant_id == restaurant.id,
            TimeSlot.date == target_date,
            TimeSlot.status == SlotStatus.UNAVAILABLE
        )
    )
    closed_slots = closed_slots_result.scalars().all()
    
    # Р•СЃР»Рё РІСЃРµ СЃР»РѕС‚С‹ РґРЅСЏ РёРјРµСЋС‚ СЃС‚Р°С‚СѓСЃ UNAVAILABLE, РІРѕР·РІСЂР°С‰Р°РµРј РїСѓСЃС‚РѕР№ СЃРїРёСЃРѕРє
    if closed_slots:
        all_slots_result = await db.execute(
            select(TimeSlot).where(
                TimeSlot.restaurant_id == restaurant.id,
                TimeSlot.date == target_date
            )
        )
        all_slots = all_slots_result.scalars().all()
        
        if all_slots and all(slot.status == SlotStatus.UNAVAILABLE for slot in all_slots):
            logger.info("Day is fully closed", restaurant_id=restaurant.id, date=target_date)
            return []

    # === 2. РџРѕРґС…РѕРґСЏС‰РёРµ СЃС‚РѕР»С‹ РїРѕ РІРјРµСЃС‚РёРјРѕСЃС‚Рё ===
    if total_guests is None:
        where_clause = and_(Table.restaurant_id == restaurant.id, Table.is_active.is_(True))
    else:
        where_clause = and_(
            Table.restaurant_id == restaurant.id,
            Table.is_active.is_(True),
            Table.seats_min <= total_guests,
            Table.seats_max >= total_guests,
        )

    suitable_tables = (await db.execute(select(Table).where(where_clause))).scalars().all()
    suitable_table_ids = {t.id for t in suitable_tables}
    if not suitable_tables:
        return []

    # ИСПРАВЛЕНИЕ: Вспомогательная функция для проверки, конкурирует ли
    # неназначенная бронь за те же столы (проверяем ВСЕ подходящие столы, а не первый)
    def _competes_for_same_tables(b_total: int) -> bool:
        return any(t.seats_min <= b_total <= t.seats_max for t in suitable_tables)

    # === 3. Р’СЃРµ Р°РєС‚РёРІРЅС‹Рµ Р±СЂРѕРЅРё РЅР° СЌС‚Сѓ РґР°С‚Сѓ ===
    active_statuses = [
        StatusEnum.pending,
        StatusEnum.pending_review,
        StatusEnum.confirmed,
        StatusEnum.assigned,
        StatusEnum.arrived,
    ]

    # РРЎРџР РђР’Р›Р•РќРР•: РСЃРїРѕР»СЊР·СѓРµРј naive datetime РґР»СЏ SQL Р·Р°РїСЂРѕСЃР°
    start_of_day = datetime.combine(target_date, time(0, 0))  # naive datetime
    end_of_day = start_of_day + timedelta(days=1)  # naive datetime

    from sqlalchemy import or_
    bookings_result = await db.execute(
        select(Booking).where(
            Booking.restaurant_id == restaurant.id,
            # ПРАВКА ОВЕРЛАПА: Брони, которые КАСАЮТСЯ этого дня.
            # (Начались ДО конца текущего дня) И (Закончились ПОСЛЕ начала текущего дня)
            Booking.start_datetime < end_of_day,
            or_(
                Booking.end_datetime > start_of_day,
                Booking.end_datetime.is_(None)
            ),
            Booking.status.in_(active_statuses),
        )
    )
    # ПРИМЕЧАНИЕ: SQLAlchemy может ругаться на 'if Booking.end_datetime is not None else True' внутри фильтра.
    # Правильнее использовать or_ или просто проверять наличие end_datetime.
    # Но так как в нашей модели end_datetime обычно есть (или мы считаем до закрытия), 
    # упростим до классического интервального пересечения.
    all_bookings: List[Booking] = bookings_result.scalars().all()

    # === 4. Р’СЂРµРјСЏ СЂР°Р±РѕС‚С‹ СЂРµСЃС‚РѕСЂР°РЅР° Рё СЃР»РѕС‚С‹ ===
    time_slots = await SlotStateManager._generate_time_slots(restaurant, target_date)
    #if is_today:
        # Р”Р»СЏ СЃСЂР°РІРЅРµРЅРёСЏ СЃ С‚РµРєСѓС‰РёРј РІСЂРµРјРµРЅРµРј РёСЃРїРѕР»СЊР·СѓРµРј aware datetime
    #    time_slots = [t for t in time_slots if datetime.combine(target_date, t, tzinfo=MOSCOW_TZ) >= moscow_now]

    closing_datetime = SlotStateManager._get_closing_time(restaurant, target_date)
    closing_datetime_msk = closing_datetime.replace(tzinfo=MOSCOW_TZ) if closing_datetime.tzinfo is None else closing_datetime.astimezone(MOSCOW_TZ)

    # === 6. РћСЃРЅРѕРІРЅРѕР№ С†РёРєР» РїРѕ СЃР»РѕС‚Р°Рј ===
    result = []
    for slot_time in time_slots:
        slot_dt = datetime.combine(target_date, slot_time, tzinfo=MOSCOW_TZ)

        # === РџСЂРѕРІРµСЂРєР° РґРѕСЃС‚СѓРїРЅРѕСЃС‚Рё РґР»СЏ РњРРќРРњРђР›Р¬РќРћР“Рћ РћРљРќРђ Р±СЂРѕРЅРёСЂРѕРІР°РЅРёСЏ ===
        # РњРёРЅРёРјР°Р»СЊРЅР°СЏ Р±СЂРѕРЅРёСЂСѓРµРјР°СЏ РїСЂРѕРґРѕР»Р¶РёС‚РµР»СЊРЅРѕСЃС‚СЊ: 1:45 + 15 РјРёРЅСѓС‚ Р±СѓС„РµСЂ = СЂРѕРІРЅРѕ 2 С‡Р°СЃР°
        window_end = slot_dt + timedelta(minutes=BOOKING_MIN_DURATION_MINUTES + BUFFER_BETWEEN_BOOKINGS_MINUTES)

        occupied_for_window = set()
        unassigned_for_window = 0

        # ИСПРАВЛЕНИЕ: Point-in-time подсчёт для отображаемого количества столов
        occupied_at_slot = set()
        unassigned_at_slot = 0

        for booking in all_bookings:
            # РџСЂРёРІРѕРґРёРј Р±СЂРѕРЅРё Рє UTC РґР»СЏ РєРѕСЂСЂРµРєС‚РЅРѕРіРѕ СЃСЂР°РІРЅРµРЅРёСЏ
            b_start = booking.start_datetime.astimezone(MOSCOW_TZ) if booking.start_datetime.tzinfo else booking.start_datetime.replace(tzinfo=MOSCOW_TZ)
            b_end = booking.end_datetime.astimezone(MOSCOW_TZ) if booking.end_datetime and booking.end_datetime.tzinfo else (
                booking.end_datetime.replace(tzinfo=MOSCOW_TZ) if booking.end_datetime else closing_datetime_msk)

            # РџРµСЂРµСЃРµС‡РµРЅРёРµ СЃ РѕРєРЅРѕРј [slot_dt, window_end)
            if b_start < window_end and b_end > slot_dt:
                if booking.table_id and booking.table_id in suitable_table_ids:
                    occupied_for_window.add(booking.table_id)
                elif booking.table_id is None:
                    # РќРµРЅР°Р·РЅР°С‡РµРЅРЅР°СЏ Р±СЂРѕРЅСЊ: СѓС‡РёС‚С‹РІР°РµРј С‚РѕР»СЊРєРѕ РµСЃР»Рё РїРѕРїР°РґР°РµС‚ РІ С‚Сѓ Р¶Рµ РіСЂСѓРїРїСѓ РІРјРµСЃС‚РёРјРѕСЃС‚Рё
                    b_total = (booking.adults or 0) + (booking.children or 0)
                    if _competes_for_same_tables(b_total):
                        unassigned_for_window += 1

            # ИСПРАВЛЕНИЕ: Point-in-time проверка — бронь занимает стол В МОМЕНТ slot_dt
            # (с учётом буфера на уборку после окончания)
            b_end_with_buffer = b_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
            if b_start <= slot_dt < b_end_with_buffer:
                if booking.table_id and booking.table_id in suitable_table_ids:
                    occupied_at_slot.add(booking.table_id)
                elif booking.table_id is None:
                    b_total = (booking.adults or 0) + (booking.children or 0)
                    if _competes_for_same_tables(b_total):
                        unassigned_at_slot += 1

        # РЎРІРѕР±РѕРґРЅС‹Рµ СЃС‚РѕР»С‹ РЅР° Р’Р•РЎР¬ РјРёРЅРёРјР°Р»СЊРЅС‹Р№ РёРЅС‚РµСЂРІР°Р»
        free_tables_for_window = [t for t in suitable_tables if t.id not in occupied_for_window]
        # РЈРјРµРЅСЊС€Р°РµРј РЅР° РєРѕР»РёС‡РµСЃС‚РІРѕ РЅРµРЅР°Р·РЅР°С‡РµРЅРЅС‹С… Р±СЂРѕРЅРµР№ (РєР°Р¶РґР°СЏ Р·Р°РЅРёРјР°РµС‚ РѕРґРёРЅ СЃС‚РѕР»)
        truly_free_tables_for_window = free_tables_for_window[:max(0, len(free_tables_for_window) - unassigned_for_window)]

        # ИСПРАВЛЕНИЕ: Point-in-time свободные столы (для отображаемого количества)
        free_tables_at_slot = [t for t in suitable_tables if t.id not in occupied_at_slot]
        display_free_count = max(0, len(free_tables_at_slot) - unassigned_at_slot)
        display_free_tables = free_tables_at_slot[:display_free_count]

        # Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕ: РїСЂРѕРІРµСЂРєР° РµРјРєРѕСЃС‚Рё Р”Рћ Р—РђРљР Р«РўРРЇ
        # Р’РђР–РќРћ: СЌС‚Р° РїСЂРѕРІРµСЂРєР° РќР• РґРѕР»Р¶РЅР° РІС‹РєР»СЋС‡Р°С‚СЊ СЃР»РѕС‚ С†РµР»РёРєРѕРј.
        # РћРЅР° Р»РёС€СЊ СЃРѕРѕР±С‰Р°РµС‚ С„СЂРѕРЅС‚Сѓ, С‡С‚Рѕ РґР»СЏ РґР°РЅРЅРѕРіРѕ СЃС‚Р°СЂС‚Р° РґРѕ Р·Р°РєСЂС‹С‚РёСЏ РїРѕСЃР°РґРёС‚СЊ РЅРµР»СЊР·СЏ,
        # Рё РЅСѓР¶РЅРѕ РїСЂРµРґР»РѕР¶РёС‚СЊ РІС‹Р±РѕСЂ С„РёРєСЃРёСЂРѕРІР°РЅРЅРѕРіРѕ РєРѕРЅС†Р°.
        occupied_till_close_ids = set()
        unassigned_till_close = 0
        for booking in all_bookings:
            b_start = booking.start_datetime.astimezone(MOSCOW_TZ) if booking.start_datetime.tzinfo else booking.start_datetime.replace(tzinfo=MOSCOW_TZ)
            b_end = booking.end_datetime.astimezone(MOSCOW_TZ) if booking.end_datetime and booking.end_datetime.tzinfo else (
                booking.end_datetime.replace(tzinfo=MOSCOW_TZ) if booking.end_datetime else closing_datetime_msk)
            if b_start < closing_datetime_msk and b_end > slot_dt:
                if booking.table_id and booking.table_id in suitable_table_ids:
                    occupied_till_close_ids.add(booking.table_id)
                elif booking.table_id is None:
                    # РќРµРЅР°Р·РЅР°С‡РµРЅРЅР°СЏ Р±СЂРѕРЅСЊ: СѓС‡РёС‚С‹РІР°РµРј С‚РѕР»СЊРєРѕ РµСЃР»Рё РїРѕРїР°РґР°РµС‚ РІ С‚Сѓ Р¶Рµ РіСЂСѓРїРїСѓ РІРјРµСЃС‚РёРјРѕСЃС‚Рё
                    b_total = (booking.adults or 0) + (booking.children or 0)
                    if _competes_for_same_tables(b_total):
                        unassigned_till_close += 1

        free_till_close = [t for t in suitable_tables if t.id not in occupied_till_close_ids]
        # РЈРјРµРЅСЊС€Р°РµРј РЅР° РєРѕР»РёС‡РµСЃС‚РІРѕ РЅРµРЅР°Р·РЅР°С‡РµРЅРЅС‹С… Р±СЂРѕРЅРµР№ (РєР°Р¶РґР°СЏ Р·Р°РЅРёРјР°РµС‚ РѕРґРёРЅ СЃС‚РѕР»)
        truly_free_till_close = free_till_close[:max(0, len(free_till_close) - unassigned_till_close)]

        # Р”РѕСЃС‚СѓРїРЅРѕСЃС‚СЊ СЃР»РѕС‚Р°: Р»РёР±Рѕ РјРёРЅРёРјР°Р»СЊРЅРѕРµ РѕРєРЅРѕ, Р»РёР±Рѕ РєРѕСЂРѕС‚РєРёР№ РёРЅС‚РµСЂРІР°Р» РґРѕ Р±Р»РёР¶Р°Р№С€РµР№ Р±СЂРѕРЅРё
        available = len(truly_free_tables_for_window) > 0

        interval_available = False
        nearest_block_start: Optional[datetime] = None
        if not available:
            # РћС†РµРЅРёРј СЃРІРѕР±РѕРґРЅС‹Рµ СЃС‚РѕР»С‹ РЅР° РњРћРњР•РќРў РЎРўРђР РўРђ СЃР»РѕС‚Р°
            occupied_at_start = set()
            unassigned_at_start = 0
            for booking in all_bookings:
                b_start = booking.start_datetime.astimezone(MOSCOW_TZ) if booking.start_datetime.tzinfo else booking.start_datetime.replace(tzinfo=MOSCOW_TZ)
                b_end = booking.end_datetime.astimezone(MOSCOW_TZ) if booking.end_datetime and booking.end_datetime.tzinfo else (
                    booking.end_datetime.replace(tzinfo=MOSCOW_TZ) if booking.end_datetime else closing_datetime_msk)
                if b_start <= slot_dt < b_end:
                    if booking.table_id and booking.table_id in suitable_table_ids:
                        occupied_at_start.add(booking.table_id)
                    elif booking.table_id is None:
                        # РќРµРЅР°Р·РЅР°С‡РµРЅРЅР°СЏ Р±СЂРѕРЅСЊ: СѓС‡РёС‚С‹РІР°РµРј С‚РѕР»СЊРєРѕ РµСЃР»Рё РїРѕРїР°РґР°РµС‚ РІ С‚Сѓ Р¶Рµ РіСЂСѓРїРїСѓ РІРјРµСЃС‚РёРјРѕСЃС‚Рё
                        b_total = (booking.adults or 0) + (booking.children or 0)
                        if _competes_for_same_tables(b_total):
                            unassigned_at_start += 1

            free_tables_at_start = [t for t in suitable_tables if t.id not in occupied_at_start]
            # РЈРјРµРЅСЊС€Р°РµРј РЅР° РєРѕР»РёС‡РµСЃС‚РІРѕ РЅРµРЅР°Р·РЅР°С‡РµРЅРЅС‹С… Р±СЂРѕРЅРµР№ (РєР°Р¶РґР°СЏ Р·Р°РЅРёРјР°РµС‚ РѕРґРёРЅ СЃС‚РѕР»)
            truly_free_tables_at_start = free_tables_at_start[:max(0, len(free_tables_at_start) - unassigned_at_start)]

            # РќР°Р№РґС‘Рј Р±Р»РёР¶Р°Р№С€РµРµ РЅР°С‡Р°Р»Рѕ РїРµСЂРµСЃРµРєР°СЋС‰РµР№ Р±СЂРѕРЅРё РїРѕ СЌС‚РѕР№ РІРјРµСЃС‚РёРјРѕСЃС‚Рё (РїРѕСЃР»Рµ СЃС‚Р°СЂС‚Р° СЃР»РѕС‚Р°)
            for booking in all_bookings:
                b_start = booking.start_datetime.astimezone(MOSCOW_TZ) if booking.start_datetime.tzinfo else booking.start_datetime.replace(tzinfo=MOSCOW_TZ)
                b_total = (booking.adults or 0) + (booking.children or 0)
                
                # РџСЂРѕРІРµСЂСЏРµРј, РѕС‚РЅРѕСЃРёС‚СЃСЏ Р»Рё Р±СЂРѕРЅСЊ Рє РЅР°С€РµР№ РіСЂСѓРїРїРµ РІРјРµСЃС‚РёРјРѕСЃС‚Рё
                same_capacity = False
                if booking.table_id and booking.table_id in suitable_table_ids:
                    same_capacity = True
                elif booking.table_id is None and suitable_tables:
                    # Р”Р»СЏ РЅРµРЅР°Р·РЅР°С‡РµРЅРЅС‹С… Р±СЂРѕРЅРµР№ РїСЂРѕРІРµСЂСЏРµРј РґРёР°РїР°Р·РѕРЅ РІРјРµСЃС‚РёРјРѕСЃС‚Рё
                    if _competes_for_same_tables(b_total):
                        same_capacity = True
                
                if same_capacity and b_start > slot_dt:
                    if nearest_block_start is None or b_start < nearest_block_start:
                        nearest_block_start = b_start

            # РРЅС‚РµСЂРІР°Р» РІРѕР·РјРѕР¶РµРЅ С‚РѕР»СЊРєРѕ РµСЃР»Рё РµСЃС‚СЊ С…РѕС‚СЏ Р±С‹ РћР”РРќ СЃС‚РѕР» СЃРІРѕР±РѕРґРµРЅ РЅР° СЃС‚Р°СЂС‚Рµ
            if truly_free_tables_at_start and nearest_block_start:
                # РРЅС‚РµСЂРІР°Р» РґРѕРїСѓСЃС‚РёРј, С‚РѕР»СЊРєРѕ РµСЃР»Рё РѕС‚ СЃС‚Р°СЂС‚Р° РґРѕ Р±Р»РёР¶Р°Р№С€РµР№ Р±СЂРѕРЅРё
                # С…РІР°С‚Р°РµС‚ РЅР° РјРёРЅРёРјР°Р»СЊРЅСѓСЋ РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ + Р±СѓС„РµСЂ (СЂРѕРІРЅРѕ 2 С‡Р°СЃР°)
                required = timedelta(minutes=BOOKING_MIN_DURATION_MINUTES + BUFFER_BETWEEN_BOOKINGS_MINUTES)
                if nearest_block_start - slot_dt >= required:
                    interval_available = True

            # РС‚РѕРіРѕРІР°СЏ РґРѕСЃС‚СѓРїРЅРѕСЃС‚СЊ: РјРёРЅРёРјР°Р»СЊРЅРѕРµ РѕРєРЅРѕ РёР»Рё РёРЅС‚РµСЂРІР°Р»
            available = interval_available

        result.append({
            "time": slot_time.strftime("%H:%M"),
            "available": available,
            "available_table_count": display_free_count,
            "total_table_count": len(suitable_tables),
            "status": "AVAILABLE" if available else "BOOKED",
            "table_ids": [t.id for t in display_free_tables],
            "tables": [
                {
                    "id": t.id,
                    "number": t.number,
                    "seats_min": t.seats_min,
                    "seats_max": t.seats_max,
                }
                for t in display_free_tables
            ],
            "meta": {
                # Р•СЃР»Рё РЅРµС‚ РµРјРєРѕСЃС‚Рё РґРѕ Р·Р°РєСЂС‹С‚РёСЏ вЂ” С„СЂРѕРЅС‚ РґРѕР»Р¶РµРЅ Р·Р°РїСЂРѕСЃРёС‚СЊ end-times
                "has_end_times": len(truly_free_till_close) == 0,
                "free_tables_available": display_free_count > 0,
                "interval_available": interval_available,
                "nearest_block_start": nearest_block_start.isoformat() if nearest_block_start else None,
            },
        })

        # Р”РёР°РіРЅРѕСЃС‚РёРєР°: РїРѕС‡РµРјСѓ СЃР»РѕС‚ РґРѕСЃС‚СѓРїРµРЅ/РЅРµРґРѕСЃС‚СѓРїРµРЅ
        try:
            logger.debug(
                "Slot diag",
                time=slot_time.strftime("%H:%M"),
                available=available,
                free_for_window=len(truly_free_tables_for_window),
                free_at_slot=display_free_count,
                total_tables=len(suitable_tables),
                interval_available=interval_available,
                nearest_block_start=nearest_block_start.isoformat() if nearest_block_start else None,
                has_end_times=(len(truly_free_till_close) == 0)
            )
        except Exception:
            pass

    # Р›РѕРіРёСЂСѓРµРј СЂРµР·СѓР»СЊС‚Р°С‚ РґР»СЏ РѕС‚Р»Р°РґРєРё
    available_slots = [s for s in result if s["available"]]
    logger.info(
        "Slots calculation completed",
        restaurant_id=restaurant.id,
        date=target_date.isoformat(),
        total_slots=len(result),
        available_slots=len(available_slots),
        first_available=available_slots[0]["time"] if available_slots else None,
        last_available=available_slots[-1]["time"] if available_slots else None,
        last_booking_time=restaurant.last_booking_time
    )

    # === РљР­РЁРР РћР’РђРќРР•: РЎРѕС…СЂР°РЅСЏРµРј СЂРµР·СѓР»СЊС‚Р°С‚ РІ Redis (TTL = 10 СЃРµРє) ===
    try:
        await RedisService.call("setex", cache_key, 10, json.dumps(result, default=str), for_write=True)
        logger.debug("Slots cached", key=cache_key)
    except Exception as e:
        logger.debug("Slots cache write error", error=str(e))

    return result


async def invalidate_slots_cache(restaurant_id: int, target_date: date):
    base_key = f"slots:{restaurant_id}:{target_date.isoformat()}"
    try:
        # РЈРґР°Р»СЏРµРј РІСЃРµ РєР»СЋС‡Рё РїРѕ РїР°С‚С‚РµСЂРЅСѓ slots:{id}:{date}:* (РІРєР»СЋС‡Р°СЏ :all, :2, :3 Рё С‚.Рґ.)
        cursor = 0
        deleted_count = 0
        while True:
            result = await RedisService.call("scan", cursor, match=f"{base_key}:*", count=100, for_write=True)
            if result is None:
                break
            cursor, keys = result
            if keys:
                await RedisService.call("delete", *keys, for_write=True)
                deleted_count += len(keys)
            if cursor == 0:
                break
        # РўР°РєР¶Рµ СѓРґР°Р»СЏРµРј Р±Р°Р·РѕРІС‹Р№ РєР»СЋС‡ (Р±РµР· СЃСѓС„С„РёРєСЃР°) РЅР° СЃР»СѓС‡Р°Р№ СЃС‚Р°СЂРѕРіРѕ С„РѕСЂРјР°С‚Р°
        await RedisService.call("delete", base_key, for_write=True)
        deleted_count += 1
        logger.info("Slots cache invalidated", base_key=base_key, deleted_count=deleted_count)
    except Exception as e:
        logger.error("Cache invalidation failed", error=str(e), key=base_key)
