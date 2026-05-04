# app/api/v1/public/tables.py
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, time, timedelta
from typing import List, Dict, Any
from app.db.session import get_async_db
from app.db.models.table import Table
from app.db.models.booking import Booking, StatusEnum
from app.db.models.enums import CapacityEnum
from app.db.models.restaurant import Restaurant
from app.core.security import validate_restaurant_slug
from app.core.time_utils import get_moscow_now
from app.core.rate_limiter import public_rate_limit
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()

async def NoRateLimit():
    """Заглушка для отключения лимитов"""
    return None

@router.options("/availability", include_in_schema=False)
async def options_tables_availability(request: Request):
    """Обработка CORS preflight запроса для /tables/availability"""
    from app.core.config import settings
    
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and origin in settings.safe_cors_origins else None
    
    headers = {
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-WebApp-Source, Authorization, User-Agent",
        "Access-Control-Max-Age": "86400",
    }
    
    # Исправление: не используем "*" с credentials
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
async def get_available_tables(
    request: Request,
    restaurant_slug: str = Query(..., min_length=1, max_length=50, description="Slug ресторана"),
    date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
    time_str: str = Query(..., regex=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", description="Время в формате HH:MM"),
    capacity_category: CapacityEnum = Query(..., description="Категория стола"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Получить список доступных столов для указанного времени с улучшенной безопасностью.
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # === ВАЛИДАЦИЯ ВХОДНЫХ ДАННЫХ ===
        
        if not validate_restaurant_slug(restaurant_slug):
            logger.warning("Invalid restaurant slug", slug=restaurant_slug, client_ip=client_ip)
            raise HTTPException(status_code=400, detail="Invalid restaurant slug")
        
        # Парсинг даты и времени
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            time_obj = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            logger.warning("Invalid date or time format", date=date, time=time_str, client_ip=client_ip)
            raise HTTPException(status_code=400, detail="Invalid date or time format")
        
        # === ПОИСК РЕСТОРАНА ===
        result = await db.execute(
            select(Restaurant).where(
                and_(
                    Restaurant.slug == restaurant_slug,
                    Restaurant.is_published.is_(True)
                )
            )
        )
        restaurant = result.scalars().first()
        if not restaurant:
            logger.warning("Restaurant not found", slug=restaurant_slug, client_ip=client_ip)
            raise HTTPException(status_code=404, detail="Restaurant not found")
        
        # === ПРОВЕРКА ВАЛИДНОСТИ ВРЕМЕНИ ===
        moscow_now = get_moscow_now()
        today = moscow_now.date()
        
        if date_obj < today:
            logger.warning("Attempt to check past date", date=date, client_ip=client_ip)
            raise HTTPException(status_code=400, detail="Cannot check availability for past dates")
        
        if date_obj == today:
            current_time = moscow_now.time()

            # Запрещаем прошедшее время сегодня
            if time_obj < current_time:
                raise HTTPException(status_code=400, detail="Cannot check availability for past times")

            # Проверяем дедлайн ТОЛЬКО если last_booking_time задан
            if restaurant.last_booking_time:
                try:
                    cutoff = datetime.strptime(restaurant.last_booking_time.strip(), "%H:%M").time()
                    if current_time >= cutoff:
                        logger.info(
                            "Same-day booking cutoff passed",
                            restaurant_slug=restaurant_slug,
                            cutoff=restaurant.last_booking_time,
                            now=current_time.strftime("%H:%M")
                        )
                        return {"tables": [], "available": False}
                except ValueError:
                    # Если время в БД кривое — на всякий случай запрещаем после 18:00
                    if current_time >= time(18, 0):
                        return {"tables": [], "available": False}

            # Если last_booking_time = null или пустое — можно бронировать всё!
        
        # === ПОЛУЧЕНИЕ ЗАБРОНИРОВАННЫХ СТОЛОВ ===
        slot_start = datetime.combine(date_obj, time_obj)
        slot_end = slot_start + timedelta(hours=2)
        booked_result = await db.execute(
            select(Booking.table_id).where(
                and_(
                    Booking.restaurant_id == restaurant.id,
                    Booking.start_datetime >= slot_start,
                    Booking.start_datetime < slot_end,
                    Booking.status.in_([StatusEnum.pending, StatusEnum.confirmed]),
                    Booking.table_id.is_not(None)
                )
            )
        )
        booked_table_ids = {row[0] for row in booked_result.all()}
        
        # === ПОЛУЧЕНИЕ ДОСТУПНЫХ СТОЛОВ ===
        avail_result = await db.execute(
            select(Table).where(
                and_(
                    Table.restaurant_id == restaurant.id,
                    Table.is_active.is_(True),
                    Table.type == capacity_category,
                    Table.id.notin_(booked_table_ids) if booked_table_ids else True
                )
            ).order_by(Table.number)
        )
        available_tables = avail_result.scalars().all()
        
        # === ФОРМАТИРОВАНИЕ РЕЗУЛЬТАТА ===
        result = [
            {
                "id": table.id,
                "number": table.number,
                "location_mark": table.location_mark,
                "type": table.type.value,
                "seats_min": table.seats_min,
                "seats_max": table.seats_max
            }
            for table in available_tables
        ]
        
        logger.info(
            "Available tables fetched",
            restaurant=restaurant_slug,
            date=date,
            time=time_str,
            capacity=capacity_category.value,
            count=len(result),
            client_ip=client_ip
        )
        
        return {
            "tables": result,
            "available": len(result) > 0,
            "total_available": len(result)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error fetching available tables",
            error=str(e),
            restaurant_slug=restaurant_slug,
            client_ip=client_ip
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )