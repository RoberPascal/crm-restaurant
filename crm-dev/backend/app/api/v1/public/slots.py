# app/api/v1/public/slots.py
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import Response
from datetime import datetime, timedelta, time 
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from app.db.session import get_async_db
from app.db.models.restaurant import Restaurant
from app.db.models.table import Table
from app.db.models.booking import Booking, StatusEnum  
from app.core.security import validate_restaurant_slug, validate_date_format
from app.core.time_utils import get_moscow_now
from app.services.slot_generator import get_available_slots_for_frontend
from app.core.rate_limiter import public_rate_limit
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()

async def NoRateLimit():
    """Legacy placeholder"""
    return None

@router.options("/availability", include_in_schema=False)
async def options_availability(request: Request):
    from app.core.config import settings
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and origin in settings.safe_cors_origins else None
    headers = {
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-WebApp-Source, Authorization, User-Agent",
        "Access-Control-Max-Age": "86400",
    }
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
        headers["Access-Control-Allow-Credentials"] = "true"
    else:
        headers["Access-Control-Allow-Origin"] = "*"
    return Response(status_code=200, headers=headers)

@router.get(
    "/availability",
    response_model=Dict[str, Any],
    response_model_exclude_none=True,
    dependencies=[Depends(public_rate_limit)]
)
async def get_available_slots(
    request: Request,
    restaurant_slug: str = Query(..., min_length=3, max_length=50),
    booking_date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
    total_guests: int = Query(..., ge=1, le=20),
    only_available: bool = Query(True),
    db: AsyncSession = Depends(get_async_db)
):
    client_ip = request.client.host if request.client else "unknown"
    try:
        if not validate_restaurant_slug(restaurant_slug):
            logger.warning("Invalid restaurant slug", slug=restaurant_slug, client_ip=client_ip)
            raise HTTPException(status_code=400, detail="Invalid restaurant slug")
        if not validate_date_format(booking_date):
            logger.warning("Invalid date format", date=booking_date, client_ip=client_ip)
            raise HTTPException(status_code=400, detail="Invalid date format")
        if total_guests < 1 or total_guests > 20:
            raise HTTPException(status_code=400, detail="Total guests must be between 1 and 20")

        booking_date_obj = datetime.strptime(booking_date, "%Y-%m-%d").date()
        result = await db.execute(
            select(Restaurant).where(
                Restaurant.slug == restaurant_slug,
                Restaurant.is_published.is_(True)
            )
        )
        restaurant = result.scalar_one_or_none()
        if not restaurant:
            logger.warning("Restaurant not found", slug=restaurant_slug, client_ip=client_ip)
            raise HTTPException(status_code=404, detail="Restaurant not found")

        moscow_now = get_moscow_now()
        today = moscow_now.date()
        if booking_date_obj < today:
            raise HTTPException(status_code=400, detail="Cannot check availability for past dates")
        max_booking_date = today + timedelta(days=restaurant.max_booking_days)
        if booking_date_obj > max_booking_date:
            raise HTTPException(
                status_code=400,
                detail=f"Date exceeds maximum booking range of {restaurant.max_booking_days} days"
            )
        if booking_date_obj == today and restaurant.last_booking_time:
            try:
                cutoff_time = datetime.strptime(restaurant.last_booking_time.strip(), "%H:%M").time()
                if moscow_now.time() >= cutoff_time:
                    logger.info("Same-day booking cutoff passed", restaurant_slug=restaurant_slug)
                    return {"slots": []}
            except ValueError:
                # Защита от кривого времени в БД
                if moscow_now.time() >= time(18, 0):
                    return {"slots": []}

        slots = await get_available_slots_for_frontend(
            restaurant=restaurant,
            target_date=booking_date_obj,
            db=db,
            total_guests=total_guests,
        )

        filtered = [s for s in slots if s["available"]] if only_available else slots

        logger.info(
            "Slots calculated by guests",
            restaurant=restaurant_slug,
            date=booking_date,
            guests=total_guests,
            slots=len(filtered),
            client_ip=client_ip
        )
        return {"slots": filtered}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in /availability", error=str(e), exc_info=True, client_ip=client_ip)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/end-times",
    response_model=Dict[str, Any],
    response_model_exclude_none=True,
    dependencies=[Depends(public_rate_limit)]
)
async def get_available_end_times_endpoint(
    request: Request,
    restaurant_slug: str = Query(..., min_length=3, max_length=50),
    booking_date: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
    start_time: str = Query(..., regex=r"^\d{2}:\d{2}$"),
    total_guests: int = Query(..., ge=1, le=20),
    db: AsyncSession = Depends(get_async_db)
):
    client_ip = request.client.host if request.client else "unknown"
    try:
        if not validate_restaurant_slug(restaurant_slug):
            raise HTTPException(status_code=400, detail="Invalid restaurant slug")
        if not validate_date_format(booking_date):
            raise HTTPException(status_code=400, detail="Invalid date format")
        if total_guests < 1 or total_guests > 20:
            raise HTTPException(status_code=400, detail="Total guests must be between 1 and 20")

        booking_date_obj = datetime.strptime(booking_date, "%Y-%m-%d").date()
        start_time_obj = datetime.strptime(start_time, "%H:%M").time()

        result = await db.execute(
            select(Restaurant).where(
                Restaurant.slug == restaurant_slug,
                Restaurant.is_published.is_(True)
            )
        )
        restaurant = result.scalar_one_or_none()
        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")

        moscow_now = get_moscow_now()
        today = moscow_now.date()
        if booking_date_obj < today:
            raise HTTPException(status_code=400, detail="Cannot check availability for past dates")

        # === НОВАЯ ЛОГИКА: Расчет доступных времен окончания ===
        
        # Получаем все брони на эту дату
        start_of_day = datetime.combine(booking_date_obj, time(0, 0))
        end_of_day = start_of_day + timedelta(days=1)
        
        bookings_result = await db.execute(
            select(Booking).where(
                Booking.restaurant_id == restaurant.id,
                Booking.start_datetime >= start_of_day,
                Booking.start_datetime < end_of_day,
                Booking.status.in_([
                    StatusEnum.pending,
                    StatusEnum.pending_review,
                    StatusEnum.confirmed,
                    StatusEnum.assigned,
                    StatusEnum.arrived,
                ])
            )
        )
        all_bookings = bookings_result.scalars().all()

        # Время закрытия ресторана
        closing_datetime = None
        for item in restaurant.schedule or []:
            if item.get("day") == booking_date_obj.weekday():
                close_str = item.get("close")
                if close_str:
                    try:
                        close_time = datetime.strptime(close_str, "%H:%M").time()
                        closing_datetime = datetime.combine(booking_date_obj, close_time)
                        if close_time <= datetime.strptime(item.get("open", "00:00"), "%H:%M").time():
                            closing_datetime += timedelta(days=1)
                        break
                    except ValueError:
                        pass
        
        if not closing_datetime:
            closing_datetime = datetime.combine(booking_date_obj + timedelta(days=1), time(5, 0))

        # Создаем start_datetime для расчета
        start_datetime = datetime.combine(booking_date_obj, start_time_obj)

        # === Капацитетный расчёт доступных концов (15-мин шаг) ===
        # 1) Собираем столы по группе вместимости
        tables_result = await db.execute(
            select(Table).where(
                Table.restaurant_id == restaurant.id,
                Table.is_active.is_(True),
                Table.seats_min <= total_guests,
                Table.seats_max >= total_guests,
            )
        )
        suitable_tables = tables_result.scalars().all()
        suitable_table_ids = {t.id for t in suitable_tables}
        capacity = len(suitable_tables)

        # Fallback: если нет активных столов, пробуем ВСЕ столы (включая деактивированные синком)
        if capacity == 0:
            all_tables_result = await db.execute(
                select(Table).where(
                    Table.restaurant_id == restaurant.id,
                    Table.seats_min <= total_guests,
                    Table.seats_max >= total_guests,
                )
            )
            all_suitable = all_tables_result.scalars().all()
            if all_suitable:
                logger.warning(
                    "No active tables but found inactive ones — using all tables for end-time calc",
                    active_count=0,
                    total_count=len(all_suitable),
                    restaurant_slug=restaurant_slug,
                )
                suitable_tables = all_suitable
                suitable_table_ids = {t.id for t in suitable_tables}
                capacity = len(suitable_tables)

        # 2) Фильтруем релевантные брони (по группе вместимости)
        rel_bookings = []
        for b in all_bookings:
            b_total = (b.adults or 0) + (b.children or 0)
            if b.table_id and b.table_id in suitable_table_ids:
                # Бронь уже назначена на стол из нашей группы вместимости
                rel_bookings.append(b)
            elif b.table_id is None:
                # Неназначенная бронь: проверяем, попадает ли в ту же группу вместимости столов
                # Берём любой стол из группы для проверки диапазона
                if suitable_tables:
                    example_table = suitable_tables[0]
                    if example_table.seats_min <= b_total <= example_table.seats_max:
                        rel_bookings.append(b)

        # 3) Строим события для существующих броней с учётом буфера на уборку
        from app.services.booking_logic import BOOKING_MIN_DURATION_MINUTES, BUFFER_BETWEEN_BOOKINGS_MINUTES
        events = []  # (time, delta)
        for b in rel_bookings:
            b_start = b.start_datetime
            b_end = b.end_datetime or closing_datetime
            # блокируем до конца + буфер
            b_end_block = b_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
            events.append((b_start, +1))
            events.append((b_end_block, -1))
        events.sort(key=lambda x: x[0])

        # Быстрая функция проверки: можно ли держать нашу бронь до candidate_end
        def can_hold_until(candidate_end: datetime) -> bool:
            our_end_block = candidate_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
            current = 0
            i = 0
            # Линейный проход по событиям, учитывая нашу бронь [start_datetime, our_end_block)
            timeline = events + [(start_datetime, +1), (our_end_block, -1)]
            timeline.sort(key=lambda x: x[0])
            for t, delta in timeline:
                if t < start_datetime:
                    current += delta
                    continue
                if t >= our_end_block:
                    break
                current += delta
                if current > capacity:
                    return False
            return True

        # 4) Генерируем кандидаты концов с шагом 15 минут
        step = timedelta(minutes=15)
        min_end = start_datetime + timedelta(minutes=BOOKING_MIN_DURATION_MINUTES)
        # Ограничим не позже закрытия
        hard_limit = closing_datetime

        available_end_times = []
        cur = (min_end.replace(second=0, microsecond=0))
        # округляем вверх до ближайших 15 минут
        minutes = cur.minute
        rounded_minutes = ((minutes + 14) // 15) * 15
        cur = cur.replace(minute=rounded_minutes % 60, hour=cur.hour + (rounded_minutes // 60), second=0, microsecond=0)

        while cur <= hard_limit:
            if can_hold_until(cur):
                available_end_times.append(cur)
            else:
                # как только дальше нечего предлагать, можно не прерывать — дальше могут снова появиться окна,
                # но для простоты идем по всему дню
                pass
            cur += step

        # Признак, что до закрытия можно без выбора конца (нет будущих конфликтов по капацитету)
        # Проверяем возможность держать до закрытия
        can_till_close = can_hold_until(closing_datetime)

        # Если можно до закрытия, интервалы не требуются — очищаем список концов
        formatted_end_times = [] if can_till_close else [et.strftime("%H:%M") for et in available_end_times]

        response = {
            "start_time": start_time,
            "available_end_times": formatted_end_times,
            "free_tables_available": can_till_close
        }

        logger.info(
            "End times calculated",
            restaurant_slug=restaurant_slug,
            date=booking_date,
            start_time=start_time,
            available_end_times_count=len(formatted_end_times),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in /end-times", error=str(e), exc_info=True, client_ip=client_ip)
        raise HTTPException(status_code=500, detail="Internal server error")