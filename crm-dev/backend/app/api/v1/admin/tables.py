# app/api/v1/admin/tables.py
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from app.db.session import get_async_db
from app.db.models.restaurant import Restaurant
from app.db.models.table import Table
from app.db.models.booking import Booking, StatusEnum
from app.services.redis_service import RedisService
from app.core.security import validate_restaurant_slug, validate_date_format
from .deps import NoRateLimit
import structlog
import re

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Tables Public"])


class TableAvailabilityParams:
    """Безопасные параметры запроса доступности столов"""
    def __init__(
        self,
        restaurant_slug: str = Query(..., min_length=1, max_length=50, description="Restaurant slug"),
        date: str = Query(..., description="Date in YYYY-MM-DD"),
        time: str = Query(..., regex=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$", description="Time in HH:MM"),
        total_guests: int = Query(..., ge=1, le=50, description="Number of guests")
    ):
        self.restaurant_slug = restaurant_slug
        self.date = date
        self.time = time
        self.total_guests = total_guests


def get_moscow_time() -> datetime:
    """Получение текущего времени в московском часовом поясе"""
    return datetime.now(timezone(timedelta(hours=3)))


def validate_booking_time(date_obj: datetime.date, time_obj: datetime.time, restaurant: Restaurant) -> None:
    """Валидация времени бронирования — теперь работает как надо"""
    moscow_now = get_moscow_time()
    today = moscow_now.date()
    current_time = moscow_now.time()
    
    # Нельзя бронировать в прошлом
    if date_obj < today:
        raise HTTPException(status_code=400, detail="Past dates not allowed")
    
    # Нельзя дальше чем max_booking_days
    max_booking_date = today + timedelta(days=restaurant.max_booking_days)
    if date_obj > max_booking_date:
        raise HTTPException(
            status_code=400, 
            detail=f"Date too far. Maximum booking days ahead: {restaurant.max_booking_days}"
        )
    
    # === КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: только если last_booking_time задан ===
    if date_obj == today and restaurant.last_booking_time:
        try:
            cutoff_time = datetime.strptime(restaurant.last_booking_time.strip(), "%H:%M").time()
            if current_time >= cutoff_time:  # >= — чтобы 23:00 нельзя было забронировать в 23:00
                raise HTTPException(status_code=400, detail="Same-day booking cutoff passed")
        except ValueError:
            # Если в БД кривое время — на всякий случай запрещаем после 18:00
            if current_time.hour >= 18:
                raise HTTPException(status_code=400, detail="Same-day booking cutoff passed")

@router.get(
    "/availability",
    response_model=Dict[str, Any],
    dependencies=[Depends(NoRateLimit)]
)
async def get_available_tables(
    request: Request,
    params: TableAvailabilityParams = Depends(),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Получение доступных столов с улучшенной безопасностью и валидацией.
    Защищено от SQL injection, timing attacks и информационных утечек.
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # === ВАЛИДАЦИЯ ВХОДНЫХ ДАННЫХ ===
        
        # Валидация slug ресторана
        if not validate_restaurant_slug(params.restaurant_slug):
            logger.warning(
                "Invalid restaurant slug", 
                slug=params.restaurant_slug,
                client_ip=client_ip
            )
            raise HTTPException(status_code=400, detail="Invalid restaurant slug format")
        
        # Валидация формата даты
        if not validate_date_format(params.date):
            logger.warning(
                "Invalid date format", 
                date=params.date,
                client_ip=client_ip
            )
            raise HTTPException(status_code=400, detail="Invalid date format")
        
        # Парсинг даты и времени
        try:
            date_obj = datetime.strptime(params.date, "%Y-%m-%d").date()
            time_obj = datetime.strptime(params.time, "%H:%M").time()
        except ValueError:
            logger.warning(
                "Invalid date/time parsing", 
                date=params.date,
                time=params.time,
                client_ip=client_ip
            )
            raise HTTPException(status_code=400, detail="Invalid date or time format")
        
        # === ПОИСК РЕСТОРАНА ===
        result = await db.execute(
            select(Restaurant).where(
                and_(
                    Restaurant.slug == params.restaurant_slug,
                    Restaurant.is_published.is_(True)
                )
            )
        )
        restaurant = result.scalars().first()
        
        if not restaurant:
            # Используем одинаковое время ответа для скрытия существования ресторана
            logger.warning(
                "Restaurant not found or not published", 
                slug=params.restaurant_slug,
                client_ip=client_ip
            )
            raise HTTPException(status_code=404, detail="Restaurant not found")
        
        # === ВАЛИДАЦИЯ ВРЕМЕНИ БРОНИРОВАНИЯ ===
        validate_booking_time(date_obj, time_obj, restaurant)
        
        # === ПОИСК ЗАБРОНИРОВАННЫХ СТОЛОВ ===
        slot_start = datetime.combine(date_obj, time_obj)
        slot_end = slot_start + timedelta(hours=2)  # Проверяем окно в 2 часа
        booked_result = await db.execute(
            select(Booking.table_id).where(
                and_(
                    Booking.restaurant_id == restaurant.id,
                    Booking.start_datetime >= slot_start,
                    Booking.start_datetime < slot_end,
                    Booking.status.in_([StatusEnum.pending, StatusEnum.confirmed, StatusEnum.assigned]),
                    Booking.table_id.is_not(None)
                )
            )
        )
        
        booked_table_ids = {row[0] for row in booked_result.all()}
        
        # === ПОИСК ДОСТУПНЫХ СТОЛОВ ===
        available_query = select(Table).where(
            and_(
                Table.restaurant_id == restaurant.id,
                Table.is_active.is_(True),
                Table.seats_min <= params.total_guests,
                Table.seats_max >= params.total_guests,
                Table.id.notin_(booked_table_ids) if booked_table_ids else True
            )
        ).order_by(Table.number)
        
        tables_result = await db.execute(available_query)
        tables = tables_result.scalars().all()
        
        # === ПРОВЕРКА БЛОКИРОВОК В REDIS ===
        available_tables = []
        redis_conn = await RedisService.ensure_connection()
        if redis_conn:
            # Атомарная проверка блокировок для избежания race condition
            pipe = redis_conn.pipeline()
            
            for table in tables:
                lock_key = f"slot_lock:{restaurant.id}:{date_obj.isoformat()}:{time_obj.strftime('%H:%M')}"
                pipe.get(lock_key)
            
            lock_results = await pipe.execute()
            
            for i, table in enumerate(tables):
                if not lock_results[i]:  # Стол не заблокирован
                    available_tables.append({
                        "table_id": table.id,
                        "number": table.number,
                        "location_mark": table.location_mark,
                        "seats_min": table.seats_min,
                        "seats_max": table.seats_max
                    })
        else:
            # Если Redis недоступен, возвращаем все доступные столы
            available_tables = [
                {
                    "table_id": table.id,
                    "number": table.number,
                    "location_mark": table.location_mark,
                    "seats_min": table.seats_min,
                    "seats_max": table.seats_max
                }
                for table in tables
            ]
        
        # === ФОРМИРОВАНИЕ ОТВЕТА ===
        response_data = {
            "tables": available_tables,
            "available": len(available_tables) > 0,
            "total_available": len(available_tables),
            "restaurant": {
                "name": restaurant.name,
                "max_booking_days": restaurant.max_booking_days
            }
        }
        
        logger.info(
            "Table availability checked",
            restaurant_slug=params.restaurant_slug,
            date=params.date,
            time=params.time,
            total_guests=params.total_guests,
            available_count=len(available_tables),
            client_ip=client_ip
        )
        
        return response_data
        
    except HTTPException:
        # Перебрасываем известные исключения
        raise
    except ValueError as e:
        # Ловим ошибки парсинга
        logger.warning(
            "Value error in table availability",
            error=str(e),
            client_ip=client_ip
        )
        raise HTTPException(status_code=400, detail="Invalid input data")
    except Exception as e:
        # Общие ошибки логируем без деталей
        logger.error(
            "Internal error in table availability",
            error=str(e),
            client_ip=client_ip
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.get("/capacities")
async def get_available_capacities(
    request: Request,
    restaurant_slug: str = Query(..., min_length=1, max_length=50),
    db: AsyncSession = Depends(get_async_db),
):
    """Получение доступных вместимостей столов для ресторана"""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        if not validate_restaurant_slug(restaurant_slug):
            raise HTTPException(status_code=400, detail="Invalid restaurant slug")
        
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
            raise HTTPException(status_code=404, detail="Restaurant not found")
        
        # Получаем уникальные вместимости активных столов
        cap_result = await db.execute(
            select(Table.type).where(
                and_(
                    Table.restaurant_id == restaurant.id,
                    Table.is_active.is_(True)
                )
            ).distinct()
        )
        capacities = cap_result.all()
        
        available_capacities = [capacity[0].value for capacity in capacities]
        
        logger.debug(
            "Capacities fetched",
            restaurant_slug=restaurant_slug,
            capacities=available_capacities,
            client_ip=client_ip
        )
        
        return {"capacities": available_capacities}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error fetching capacities",
            error=str(e),
            restaurant_slug=restaurant_slug,
            client_ip=client_ip
        )
        raise HTTPException(status_code=500, detail="Internal server error")