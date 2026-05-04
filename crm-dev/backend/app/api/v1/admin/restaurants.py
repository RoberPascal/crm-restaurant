# app/api/v1/admin/restaurants.py
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, func
from app.db.session import get_async_db
from app.db.models.restaurant import Restaurant
from app.db.models.user import User, RoleEnum
from app.schemas.restaurant import RestaurantResponse
from .deps import get_current_user_from_cookie, require_operator_role, validate_restaurant_access, NoRateLimit, require_admin_role
import structlog
import re
from pydantic import BaseModel, field_validator
from datetime import datetime, date, timedelta, time as dtime
from app.services.slot_state_manager import SlotStateManager
from app.db.models.slot import TimeSlot
from app.db.models.enums import SlotStatus, StatusEnum
from app.db.models.table import Table
from app.services.slot_generator import invalidate_slots_cache
from app.core.security import validate_csrf_dependency
from app.db.models.booking import Booking

logger = structlog.get_logger(__name__)
router = APIRouter()

class RestaurantQueryParams:
    """Безопасные параметры запроса для ресторанов"""
    def __init__(
        self,
        skip: int = Query(0, ge=0, le=1000, description="Number of records to skip"),
        limit: int = Query(50, ge=1, le=200, description="Number of records to return"),
        search: str = Query(None, max_length=50, description="Search by name")
    ):
        self.skip = skip
        self.limit = limit
        self.search = search

def sanitize_search_term(term: str) -> str:
    """Санитизация поискового запроса для защиты от SQL injection"""
    if not term:
        return ""
    # Удаляем специальные символы, оставляем только буквы, цифры и пробелы
    sanitized = re.sub(r'[^\w\sа-яА-ЯёЁ]', '', term, flags=re.UNICODE)
    return sanitized.strip()

@router.get("/", response_model=list[RestaurantResponse])
async def read_restaurants(
    request: Request,
    params: RestaurantQueryParams = Depends(),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_operator_role),
    _: None = Depends(NoRateLimit)
):
    """
    Получение списка ресторанов с проверкой прав доступа.
    Для операторов можно добавить фильтрацию по привязанным ресторанам.
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # Базовый запрос
        query = select(Restaurant).where(Restaurant.is_published.is_(True))  # Используем select и is_published
        
        # Поиск по имени (если указан)
        if params.search:
            sanitized_search = sanitize_search_term(params.search)
            if sanitized_search:
                # Используем case-insensitive поиск (работает в SQLite и PostgreSQL)
                from sqlalchemy import func
                query = query.where(func.lower(Restaurant.name).contains(func.lower(sanitized_search)))
        
        # Сортировка и пагинация
        query = query.order_by(Restaurant.name).offset(params.skip).limit(params.limit)
        
        result = await db.execute(query)
        restaurants = result.scalars().all()
        
        # Логируем без чувствительной информации
        logger.info(
            "Restaurants fetched successfully", 
            count=len(restaurants),
            user_id=current_user.id,
            user_role=current_user.role.value,
            client_ip=client_ip,
            has_search=bool(params.search)
        )
        
        return restaurants
        
    except Exception as e:
        logger.error(
            "Error fetching restaurants", 
            error=str(e),
            user_id=current_user.id,
            client_ip=client_ip
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

@router.get("/{restaurant_id}", response_model=RestaurantResponse)
async def get_restaurant(
    request: Request,
    restaurant_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_operator_role),
):
    """Получение информации о конкретном ресторане с проверкой прав доступа"""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # Проверка существования ресторана
        result = await db.execute(
            select(Restaurant).where(  # Используем select и is_published
                and_(
                    Restaurant.id == restaurant_id,
                    Restaurant.is_published.is_(True)
                )
            )
        )
        restaurant = result.scalar_one_or_none()
        
        if not restaurant:
            logger.warning(
                "Restaurant not found", 
                restaurant_id=restaurant_id,
                user_id=current_user.id,
                client_ip=client_ip
            )
            raise HTTPException(
                status_code=404,
                detail="Restaurant not found"
            )
        
        # Проверка прав доступа к ресторану
        if not await validate_restaurant_access(restaurant_id, current_user):
            logger.warning(
                "Restaurant access denied", 
                user_id=current_user.id,
                restaurant_id=restaurant_id,
                client_ip=client_ip
            )
            raise HTTPException(
                status_code=403,
                detail="Access to restaurant denied"
            )
        
        logger.debug(
            "Restaurant details fetched", 
            restaurant_id=restaurant_id,
            user_id=current_user.id,
            client_ip=client_ip
        )
        
        return restaurant
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error fetching restaurant details", 
            error=str(e),
            restaurant_id=restaurant_id,
            user_id=current_user.id,
            client_ip=client_ip
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

# === Admin: Settings and Slot Controls ===

class UpdateLastBookingTime(BaseModel):
    last_booking_time: str | None

    @field_validator('last_booking_time')
    @classmethod
    def validate_hhmm(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("last_booking_time must be in HH:MM format")
        return v

class DayPayload(BaseModel):
    date: str  # YYYY-MM-DD

    @property
    def as_date(self) -> date:
        try:
            return datetime.strptime(self.date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

class RangePayload(BaseModel):
    start_date: str
    end_date: str
    time_from: str | None = None  # HH:MM
    time_to: str | None = None

    @property
    def range_dates(self) -> tuple[date, date]:
        try:
            s = datetime.strptime(self.start_date, "%Y-%m-%d").date()
            e = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")
        if e < s:
            raise HTTPException(status_code=400, detail="end_date must be >= start_date")
        return s, e

    @property
    def time_window(self) -> tuple[dtime | None, dtime | None]:
        tf = None
        tt = None
        if self.time_from:
            try:
                tf = datetime.strptime(self.time_from, "%H:%M").time()
            except ValueError:
                raise HTTPException(status_code=400, detail="time_from must be HH:MM")
        if self.time_to:
            try:
                tt = datetime.strptime(self.time_to, "%H:%M").time()
            except ValueError:
                raise HTTPException(status_code=400, detail="time_to must be HH:MM")
        return tf, tt

@router.patch(
    "/{restaurant_id}/settings/last-booking-time",
    response_model=RestaurantResponse,
    dependencies=[Depends(validate_csrf_dependency)]
)
async def set_last_booking_time(
    request: Request,
    restaurant_id: int,
    payload: UpdateLastBookingTime,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role),
):
    client_ip = request.client.host if request.client else "unknown"
    try:
        restaurant = await db.get(Restaurant, restaurant_id)
        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")
        if not await validate_restaurant_access(restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access denied")

        restaurant.last_booking_time = payload.last_booking_time
        await db.commit()
        await db.refresh(restaurant)

        logger.info("Updated last_booking_time", restaurant_id=restaurant_id, value=payload.last_booking_time, user_id=current_user.id)
        return restaurant
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update last_booking_time", error=str(e), restaurant_id=restaurant_id, client_ip=client_ip)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post(
    "/{restaurant_id}/slots/rebuild",
    dependencies=[Depends(NoRateLimit), Depends(validate_csrf_dependency)]
)
async def rebuild_slots_for_day(
    request: Request,
    restaurant_id: int,
    payload: DayPayload,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role),
):
    client_ip = request.client.host if request.client else "unknown"
    try:
        if not await validate_restaurant_access(restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access denied")

        target_date = payload.as_date
        await SlotStateManager.initialize_daily_slots(restaurant_id, target_date, db)
        await db.commit()
        await invalidate_slots_cache(restaurant_id, target_date)
        await SlotStateManager._publish_slot_update(restaurant_id, target_date)
        logger.info("Slots rebuilt", restaurant_id=restaurant_id, date=payload.date, user_id=current_user.id)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to rebuild slots", error=str(e), restaurant_id=restaurant_id, client_ip=client_ip)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post(
    "/{restaurant_id}/slots/close-day",
    dependencies=[Depends(NoRateLimit), Depends(validate_csrf_dependency)]
)
async def close_day_slots(
    request: Request,
    restaurant_id: int,
    payload: DayPayload,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role),
):
    try:
        if not await validate_restaurant_access(restaurant_id, current_user):
            raise HTTPException(403, "Access denied")

        target_date = payload.as_date

        # Получаем все активные столы
        tables_result = await db.execute(
            select(Table.id).where(
                Table.restaurant_id == restaurant_id,
                Table.is_active.is_(True)
            )
        )
        all_table_ids = [row[0] for row in tables_result.all()]

        # Получаем все слоты на этот день
        slots_result = await db.execute(
            select(TimeSlot).where(
                TimeSlot.restaurant_id == restaurant_id,
                TimeSlot.date == target_date
            )
        )
        existing_slots = slots_result.scalars().all()

        # Если слоты уже существуют - обновляем их
        if existing_slots:
            await db.execute(
                update(TimeSlot)
                .where(
                    TimeSlot.restaurant_id == restaurant_id,
                    TimeSlot.date == target_date
                )
                .values(
                    status=SlotStatus.UNAVAILABLE,
                    booked_tables=all_table_ids,
                    available_table_count=0,
                    total_table_count=len(all_table_ids)
                )
            )
        else:
            # Если слотов нет - создаем их с статусом UNAVAILABLE
            restaurant = await db.get(Restaurant, restaurant_id)
            if restaurant:
                time_slots = await SlotStateManager._generate_time_slots(restaurant, target_date)
                for slot_time in time_slots:
                    slot = TimeSlot(
                        restaurant_id=restaurant_id,
                        date=target_date,
                        time=slot_time,
                        table_ids=all_table_ids,
                        booked_tables=all_table_ids,  # Все столы заняты
                        available_table_count=0,  # Нет доступных столов
                        total_table_count=len(all_table_ids),
                        status=SlotStatus.UNAVAILABLE,  # Явно указываем статус
                    )
                    db.add(slot)

        await db.commit()

        # Инвалидируем кэш и отправляем обновление
        await invalidate_slots_cache(restaurant_id, target_date)
        await SlotStateManager._publish_slot_update(restaurant_id, target_date)

        logger.info("Day fully closed", restaurant_id=restaurant_id, date=target_date)
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to close day", error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(500, "Ошибка закрытия дня")

# === BULK RANGE OPERATIONS ===
@router.post(
    "/{restaurant_id}/slots/rebuild-range",
    dependencies=[Depends(NoRateLimit), Depends(validate_csrf_dependency)]
)
async def rebuild_slots_range(
    request: Request,
    restaurant_id: int,
    payload: RangePayload,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role),
):
    try:
        if not await validate_restaurant_access(restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access denied")
        start_date, end_date = payload.range_dates
        d = start_date
        while d <= end_date:
            await SlotStateManager.initialize_daily_slots(restaurant_id, d, db)
            await invalidate_slots_cache(restaurant_id, d)
            await SlotStateManager._publish_slot_update(restaurant_id, d)
            d += timedelta(days=1)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to rebuild range", error=str(e))
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post(
    "/{restaurant_id}/slots/close-range",
    dependencies=[Depends(NoRateLimit), Depends(validate_csrf_dependency)]
)
async def close_slots_range(
    request: Request,
    restaurant_id: int,
    payload: RangePayload,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role),
):
    try:
        if not await validate_restaurant_access(restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access denied")
        start_date, end_date = payload.range_dates
        time_from, time_to = payload.time_window
        d = start_date
        
        # Получаем все активные столы один раз
        tables_result = await db.execute(
            select(Table.id).where(
                Table.restaurant_id == restaurant_id,
                Table.is_active.is_(True)
            )
        )
        all_table_ids = [row[0] for row in tables_result.all()]
        
        while d <= end_date:
            # Создаем базовый запрос для обновления
            q = update(TimeSlot).where(
                and_(
                    TimeSlot.restaurant_id == restaurant_id,
                    TimeSlot.date == d,
                )
            )
            
            # Добавляем фильтры по времени если указаны
            if time_from and time_to:
                q = q.where(and_(TimeSlot.time >= time_from, TimeSlot.time <= time_to))
            elif time_from:
                q = q.where(TimeSlot.time >= time_from)
            elif time_to:
                q = q.where(TimeSlot.time <= time_to)
                
            # Обновляем слоты
            await db.execute(q.values(
                status=SlotStatus.UNAVAILABLE, 
                booked_tables=all_table_ids,
                available_table_count=0,
                total_table_count=len(all_table_ids)
            ))
            
            await invalidate_slots_cache(restaurant_id, d)
            await SlotStateManager._publish_slot_update(restaurant_id, d)
            d += timedelta(days=1)
            
        await db.commit()
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to close range", error=str(e))
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post(
    "/{restaurant_id}/slots/open-range",
    dependencies=[Depends(NoRateLimit), Depends(validate_csrf_dependency)]
)
async def open_slots_range(
    request: Request,
    restaurant_id: int,
    payload: RangePayload,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role),
):
    """Переинициализировать слоты для диапазона дат (считай открыть обратно). Если указан time_from/time_to, просто переинициализация дня покроет корректные слоты."""
    try:
        if not await validate_restaurant_access(restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access denied")
        start_date, end_date = payload.range_dates
        d = start_date
        while d <= end_date:
            await SlotStateManager.initialize_daily_slots(restaurant_id, d, db)
            await db.commit()
            await invalidate_slots_cache(restaurant_id, d)
            await SlotStateManager._publish_slot_update(restaurant_id, d)
            d += timedelta(days=1)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to open range", error=str(e))
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

# === STATS ===
@router.get(
    "/{restaurant_id}/stats",
    dependencies=[Depends(NoRateLimit)]
)
async def get_restaurant_stats(
    request: Request,
    restaurant_id: int,
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role),
):
    try:
        if not await validate_restaurant_access(restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access denied")
        try:
            s = datetime.strptime(start, "%Y-%m-%d").date()
            e = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")
        if e < s:
            raise HTTPException(status_code=400, detail="end must be >= start")

        # Bookings by status
        bookings_q = select(Booking.status, func.count(Booking.id)).where(
            Booking.restaurant_id == restaurant_id,
            Booking.start_datetime >= datetime.combine(s, datetime.min.time()),
            Booking.start_datetime < datetime.combine(e + timedelta(days=1), datetime.min.time()),
        ).group_by(Booking.status)
        bookings_res = await db.execute(bookings_q)
        bookings_by_status = { (row[0].value if isinstance(row[0], StatusEnum) else str(row[0])): row[1] for row in bookings_res.all() }

        # Slots utilization (sum per day): available vs total
        slots_q = select(
            TimeSlot.date,
            func.sum(TimeSlot.total_table_count).label("total"),
            func.sum(TimeSlot.available_table_count).label("available"),
        ).where(
            TimeSlot.restaurant_id == restaurant_id,
            TimeSlot.date >= s,
            TimeSlot.date <= e,
            TimeSlot.status != SlotStatus.UNAVAILABLE,
        ).group_by(TimeSlot.date).order_by(TimeSlot.date)
        slots_res = await db.execute(slots_q)
        utilization = [
            {
                "date": row[0].isoformat(),
                "total": int(row[1] or 0),
                "available": int(row[2] or 0),
                "used": int((row[1] or 0) - (row[2] or 0)),
            }
            for row in slots_res.all()
        ]

        # Totals
        total_bookings = sum(bookings_by_status.values()) if bookings_by_status else 0
        total_used = sum(u["used"] for u in utilization)

        return {
            "bookings_by_status": bookings_by_status,
            "utilization": utilization,
            "totals": {"bookings": total_bookings, "used_tables": total_used},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to load stats", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")