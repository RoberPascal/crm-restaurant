# app/api/v1/admin/bookings.py
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, cast, Date, Time, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, date, time, timedelta
from typing import List, Optional
import structlog
from app.services.redis_service import RedisService
from app.db.session import get_async_db
from app.db.models.booking import Booking, StatusEnum
from app.db.models.table import Table
from app.db.models.restaurant import Restaurant
from app.db.models.user import User
from app.schemas.booking import (
    AdminBookingSchema,
    BookingUpdate,
    BookingAssignTable,
    BookingCreateAdmin
)
from app.services.booking_service import (
    get_suitable_tables,
    create_booking_with_tables,
    publish_booking_update,
    log_booking_status_change,
)
from app.services.slot_state_manager import BUFFER_BETWEEN_BOOKINGS_MINUTES
from app.services.slot_state_manager import SlotStateManager
from app.services.slot_generator import invalidate_slots_cache
from app.core.security import validate_csrf_dependency
from app.core.validation_utils import validate_person_name, validate_phone_number
from app.core.time_utils import get_moscow_now, strict_parse_date, parse_time_strict
from .deps import require_staff_role, validate_restaurant_access, NoRateLimit
import json
import asyncio

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Bookings"])

# Кастомный JSON encoder для сериализации datetime объектов
class DateTimeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, time):
            return obj.strftime('%H:%M:%S')
        return super().default(obj)

def json_dumps_custom(obj):
    return json.dumps(obj, cls=DateTimeJSONEncoder, ensure_ascii=False)


def _get_end_from_schedule(restaurant, start_dt):
    """Extract closing time from restaurant schedule for a given start datetime."""
    if not restaurant or not restaurant.schedule:
        return None
    for schedule in restaurant.schedule:
        if schedule.get("day") == start_dt.weekday():
            close_time_str = schedule.get("close")
            if close_time_str:
                try:
                    close_time = datetime.strptime(close_time_str, "%H:%M").time()
                    end = datetime.combine(start_dt.date(), close_time)
                    if close_time <= start_dt.time():
                        end += timedelta(days=1)
                    return end
                except ValueError:
                    continue
    return None


class BookingsQueryParams:
    def __init__(
        self,
        restaurant_id: int = Query(..., gt=0, description="ID ресторана"),
        date: str = Query(..., description="Дата в формате YYYY-MM-DD"),
        status: Optional[StatusEnum] = Query(None, description="Статус бронирования"),
        phone: Optional[str] = Query(None, description="Фильтр по номеру телефона"),
        name: Optional[str] = Query(None, description="Фильтр по имени клиента")
    ):
        self.restaurant_id = restaurant_id
        self.date = date
        self.status = status
        self.phone = phone
        self.name = name


@router.get("/", response_model=List[AdminBookingSchema])
async def read_bookings(
    request: Request,
    params: BookingsQueryParams = Depends(),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_staff_role),
    skip: int = Query(0, ge=0, le=1000),
    limit: int = Query(100, ge=1, le=200)
):
    """Получение списка бронирований за конкретную дату"""
    client_ip = request.client.host if request.client else "unknown"

    try:
        # Проверка доступа к ресторану
        if not await validate_restaurant_access(params.restaurant_id, current_user):
            logger.warning(
                "Restaurant access denied",
                user_id=current_user.id,
                restaurant_id=params.restaurant_id,
                client_ip=client_ip
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to restaurant denied")

        # Валидация даты
        date_obj = strict_parse_date(params.date)
        if not date_obj:
            logger.warning("Invalid date format", date=params.date, client_ip=client_ip)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")

        # Диапазон для дня (с 00:00 до 23:59:59.999999)
        day_start = datetime.combine(date_obj, time.min)
        day_end = day_start + timedelta(days=1)

        # Основной запрос — фильтрация по start_datetime
        query = (
            select(Booking)
            .where(
                and_(
                    Booking.restaurant_id == params.restaurant_id,
                    Booking.start_datetime >= day_start,
                    Booking.start_datetime < day_end
                )
            )
            .options(
                selectinload(Booking.table),
                selectinload(Booking.restaurant),
                selectinload(Booking.user_public)
            )
        )

        # Фильтры
        if params.status:
            query = query.where(Booking.status == params.status)
        if params.phone:
            safe_phone = params.phone.replace('%', '\\%').replace('_', '\\_')
            query = query.where(Booking.phone.ilike(f"%{safe_phone}%"))
        if params.name:
            safe_name = params.name.replace('%', '\\%').replace('_', '\\_')
            query = query.where(Booking.name.ilike(f"%{safe_name}%"))

        # Сортировка по времени бронирования, потом по дате создания
        query = query.order_by(Booking.start_datetime, Booking.created_at).offset(skip).limit(limit)

        result = await db.execute(query)
        bookings = result.scalars().all()

        # NOTE: suitable_tables_json больше НЕ пересчитывается в списке бронирований.
        # Используйте GET /{booking_id}/suitable-tables для актуальных данных.
        # Это устраняет N+1 проблему (ранее 3+ SQL-запросов на каждую бронь).

        logger.info(
            "Bookings fetched successfully",
            count=len(bookings),
            restaurant_id=params.restaurant_id,
            date=params.date,
            user_id=current_user.id
        )

        return [AdminBookingSchema.from_orm(booking) for booking in bookings]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error loading bookings",
            error=str(e),
            restaurant_id=getattr(params, "restaurant_id", None),
            client_ip=client_ip,
            exc_info=True
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")

async def _update_booking_suitable_tables(db: AsyncSession, booking: Booking, total_guests: int):
    """Обновление поля suitable_tables_json для брони"""
    try:
        logger.info(f"Updating suitable tables for booking {booking.id}, guests: {total_guests}")
        
        # ИСПРАВЛЕНИЕ: убираем параметр end_datetime
        suitable_tables = await get_suitable_tables(
            restaurant_id=booking.restaurant_id,
            db=db,
            total_guests=total_guests,
            start_datetime=booking.start_datetime,
            exclude_booking_id=booking.id
        )
        
        logger.info(f"Found {len(suitable_tables)} suitable tables for booking {booking.id}")
        
        # ИСПРАВЛЕНИЕ: Сохраняем только ID столов, а не всю информацию
        if suitable_tables:
            suitable_table_ids = [table['id'] for table in suitable_tables]
            booking.suitable_tables_json = json.dumps(suitable_table_ids)
        else:
            booking.suitable_tables_json = None
        
        # Принудительно сохраняем изменения
        await db.flush()
        
    except Exception as e:
        logger.error(f"Error updating suitable tables for booking {booking.id}: {str(e)}", exc_info=True)

@router.patch("/{booking_id}/status", response_model=AdminBookingSchema, dependencies=[Depends(NoRateLimit), Depends(validate_csrf_dependency)])
async def update_booking_status(
    request: Request,
    booking_id: int,
    booking_update: BookingUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_staff_role),
):
    client_ip = request.client.host if request.client else "unknown"

    try:
        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(selectinload(Booking.table), selectinload(Booking.restaurant))
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if not await validate_restaurant_access(booking.restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access to booking denied")

        old_status = booking.status
        new_status = booking_update.status

        if not StatusEnum.can_transition_to(old_status, new_status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot transition from {old_status.value} to {new_status.value}"
            )

        # Освобождение стола при отмене/неявке
        if old_status in [StatusEnum.assigned, StatusEnum.confirmed] and new_status in [StatusEnum.cancelled, StatusEnum.no_show]:
            if booking.table_id:
                await SlotStateManager.cancel_booking(
                    restaurant_id=booking.restaurant_id,
                    date=booking.start_datetime.date(),
                    time=booking.start_datetime.time(),
                    table_id=booking.table_id,
                    db=db
                )
            else:
                await SlotStateManager.release_slot_without_table(
                    restaurant_id=booking.restaurant_id,
                    date=booking.start_datetime.date(),
                    time=booking.start_datetime.time(),
                    db=db
                )

        # Автоматическое присвоение статуса assigned при confirmed без стола
        if new_status == StatusEnum.confirmed and not booking.table_id:
            booking.status = StatusEnum.assigned
        else:
            booking.status = new_status

        # Освобождение стола при завершающих статусах
        if booking.status in [StatusEnum.completed, StatusEnum.cancelled, StatusEnum.no_show]:
            if booking.table_id:
                old_table_id = booking.table_id
                booking.table_id = None
                logger.info(
                    "Table released on booking completion",
                    booking_id=booking_id,
                    table_id=old_table_id,
                    new_status=booking.status.value
                )

        # Сохраняем ВСЕ данные для последующего использования ДО commit
        restaurant_id = booking.restaurant_id
        start_date = booking.start_datetime.date()
        restaurant_obj = booking.restaurant
        
        # Создаем копию данных брони для publish (до commit/refresh)
        from copy import copy
        booking_snapshot = copy(booking)
        booking_snapshot.id = booking.id
        booking_snapshot.start_datetime = booking.start_datetime
        booking_snapshot.created_at = booking.created_at

        await db.commit()

        # Re-fetch booking with relationships to ensure table_number is available
        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(selectinload(Booking.table), selectinload(Booking.restaurant))
        )
        booking = result.scalar_one()

        # Логирование изменения статуса в историю (необязательно, не прерывает процесс)
        try:
            await log_booking_status_change(
                booking_id=booking_id,
                old_status=old_status,
                new_status=booking.status,
                changed_by_user_id=current_user.id,
                reason=getattr(booking_update, 'status_change_reason', None),
                db=db
            )
        except Exception as log_error:
            logger.warning(
                "Failed to log status change (non-critical)",
                booking_id=booking_id,
                error=str(log_error)
            )

        # Обновление слотов
        await SlotStateManager.initialize_daily_slots(
            restaurant_id=restaurant_id,
            target_date=start_date,
            db=db
        )
        await SlotStateManager._invalidate_cache(restaurant_id, start_date)
        await SlotStateManager._publish_slot_update(restaurant_id, start_date)

        await invalidate_slots_cache(restaurant_id, start_date)
        await publish_booking_update(booking_snapshot, restaurant_obj)

        logger.info("Booking status updated", booking_id=booking_id, old_status=old_status.value, new_status=booking.status.value)
        return AdminBookingSchema.from_orm(booking)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating booking status", booking_id=booking_id, error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{booking_id}/assign-table", response_model=AdminBookingSchema, dependencies=[Depends(NoRateLimit), Depends(validate_csrf_dependency)])
async def assign_table(
    request: Request,
    booking_id: int,
    assign: BookingAssignTable,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_staff_role),
):
    """
    Назначение конкретного стола бронированию.
    Гарантирует, что стол свободен в этот момент времени.
    """
    client_ip = request.client.host if request.client else "unknown"

    try:
        # 1. Получаем бронь
        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(
                selectinload(Booking.table),
                selectinload(Booking.restaurant)
            )
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Бронь не найдена")

        if not await validate_restaurant_access(booking.restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Нет доступа к ресторану")

        # 2. Проверяем стол
        table = await db.get(Table, assign.table_id)
        if not table:
            raise HTTPException(status_code=400, detail="Стол не найден")
        if table.restaurant_id != booking.restaurant_id:
            raise HTTPException(status_code=400, detail="Стол принадлежит другому ресторану")
        if not table.is_active:
            raise HTTPException(status_code=400, detail="Стол неактивен")

        total_guests = booking.adults + (booking.children or 0)
        if not table.can_accommodate(total_guests):
            raise HTTPException(status_code=400, detail="Стол не подходит по количеству мест")

        # 3. Проверка слота: только если админ закрыл день (UNAVAILABLE)
        #    НЕ блокируем по BOOKED — админ должен мочь назначать столы
        #    даже когда система «зарезервировала» столы под неназначенные брони.
        from app.db.models.slot import TimeSlot
        from app.db.models.enums import SlotStatus
        slot = await db.scalar(
            select(TimeSlot).where(
                TimeSlot.restaurant_id == booking.restaurant_id,
                TimeSlot.date == booking.start_datetime.date(),
                TimeSlot.time == booking.start_datetime.time(),
            )
        )
        if slot and slot.status == SlotStatus.UNAVAILABLE:
            raise HTTPException(
                status_code=409,
                detail="Этот слот закрыт администратором"
            )

        # 4. Основная проверка: прямой поиск конфликта по table_id + пересечение времени
        if await _check_table_conflict(db, booking, assign.table_id):
            # Получаем детали конфликтующей брони для информативного сообщения
            conflict_check = await db.execute(
                select(Booking.id, Booking.name, Booking.start_datetime, Booking.end_datetime).where(
                    Booking.restaurant_id == booking.restaurant_id,
                    Booking.table_id == assign.table_id,
                    Booking.id != booking.id,
                    Booking.status.in_(StatusEnum.get_active_statuses()),
                )
            )
            conflicts = conflict_check.all()
            
            # Найдём конфликтующую бронь для отображения в сообщении
            conflict_info = None
            for conflict in conflicts:
                conflict_start = conflict.start_datetime
                conflict_end = conflict.end_datetime or (conflict_start + timedelta(hours=4))
                booking_start = booking.start_datetime
                booking_end = booking.end_datetime or (booking_start + timedelta(hours=4))
                
                # Проверяем пересечение: (B1.start < A2.end) AND (B1.end > A2.start)
                if conflict_start < booking_end and conflict_end > booking_start:
                    conflict_info = conflict
                    break
            
            if conflict_info:
                raise HTTPException(
                    status_code=409,
                    detail=f"Стол #{table.number} уже назначен брони #{conflict_info.id} ({conflict_info.name}) на пересекающееся время"
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"Стол #{table.number} уже занят другой бронью на пересекающееся время"
                )

        # 5. Всё ок — назначаем
        old_table_id = booking.table_id
        booking.table_id = assign.table_id
        if booking.status == StatusEnum.pending:
            booking.status = StatusEnum.assigned

        # 6. Освобождаем старый стол, если был
        if old_table_id and old_table_id != assign.table_id:
            await SlotStateManager.cancel_booking(
                restaurant_id=booking.restaurant_id,
                date=booking.start_datetime.date(),
                time=booking.start_datetime.time(),
                table_id=old_table_id,
                db=db
            )

        await db.commit()

        # Re-fetch booking with relationships to ensure table_number is available
        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(selectinload(Booking.table), selectinload(Booking.restaurant))
        )
        booking = result.scalar_one()

        # 7. Пересчитываем слоты и кэш
        await SlotStateManager.initialize_daily_slots(
            restaurant_id=booking.restaurant_id,
            target_date=booking.start_datetime.date(),
            db=db
        )
        await SlotStateManager._invalidate_cache(booking.restaurant_id, booking.start_datetime.date())
        await SlotStateManager._publish_slot_update(booking.restaurant_id, booking.start_datetime.date())

        await invalidate_slots_cache(booking.restaurant_id, booking.start_datetime.date())
        await publish_booking_update(booking, booking.restaurant)

        logger.info(
            "Table assigned successfully",
            booking_id=booking.id,
            table_id=assign.table_id,
            table_number=table.number,
            user_id=current_user.id
        )

        return AdminBookingSchema.from_orm(booking)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Assign table error", booking_id=booking_id, table_id=assign.table_id, error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Ошибка при назначении стола")

async def _check_table_conflict(db: AsyncSession, booking: Booking, table_id: int) -> bool:
    """Проверяет конфликты бронирований с учетом временных интервалов и буфера"""
    active_statuses = StatusEnum.get_active_statuses()
    
    # Pre-fetch restaurant once (avoid N+1 in loop below)
    restaurant = await db.get(Restaurant, booking.restaurant_id)
    
    # Получаем время начала и окончания текущей брони
    current_start = booking.start_datetime
    current_end = booking.end_datetime
    
    # Если нет явного времени окончания, считаем что бронь до закрытия
    if not current_end:
        current_end = _get_end_from_schedule(restaurant, current_start)
        if not current_end:
            current_end = current_start + timedelta(hours=4)
    
    # Добавляем буфер к текущей брони
    current_end_with_buffer = current_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
    
    # Получаем все активные брони на этот стол
    result = await db.execute(
        select(Booking).where(
            and_(
                Booking.restaurant_id == booking.restaurant_id,
                Booking.table_id == table_id,
                Booking.status.in_(active_statuses),
                Booking.id != booking.id,
            )
        )
    )
    existing_bookings = result.scalars().all()
    
    # Проверяем каждую существующую бронь на пересечение
    for existing in existing_bookings:
        existing_start = existing.start_datetime
        existing_end = existing.end_datetime
        
        # Если у существующей брони нет времени окончания
        if not existing_end:
            # Reuse the already-fetched restaurant (same restaurant_id)
            existing_end = _get_end_from_schedule(restaurant, existing_start)
            if not existing_end:
                existing_end = existing_start + timedelta(hours=4)
        
        # Добавляем буфер к существующей брони
        existing_end_with_buffer = existing_end + timedelta(minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES)
        
        # Проверяем пересечение с учетом буфера:
        # (B1.start < A2.end + buffer) AND (B1.end + buffer > A2.start)
        if current_start < existing_end_with_buffer and current_end_with_buffer > existing_start:
            logger.warning(
                "Table conflict detected", 
                table_id=table_id,
                booking_id=booking.id,
                conflicting_booking_id=existing.id,
                current_slot=f"{current_start.strftime('%H:%M')}-{current_end.strftime('%H:%M')}",
                existing_slot=f"{existing_start.strftime('%H:%M')}-{existing_end.strftime('%H:%M')}",
                buffer_minutes=BUFFER_BETWEEN_BOOKINGS_MINUTES
            )
            return True
    
    return False

async def update_suitable_tables_for_slot(db: AsyncSession, restaurant_id: int, date: date, time: time):
    """Обновление suitable_tables для всех броней в указанном слоте"""
    active_statuses = StatusEnum.get_active_statuses()
    day_start = datetime.combine(date, time.min)
    day_end = day_start + timedelta(days=1)

    result = await db.execute(
        select(Booking).where(
            Booking.restaurant_id == restaurant_id,
            Booking.start_datetime >= day_start,
            Booking.start_datetime < day_end,
            cast(Booking.start_datetime, Time) == time,
            Booking.status.in_(active_statuses)
        )
    )
    bookings = result.scalars().all()

    logger.info(f"Updating suitable tables for {len(bookings)} bookings in slot {time}")

    tasks = []
    for b in bookings:
        total_guests = b.adults + (b.children or 0)
        tasks.append(_update_booking_suitable_tables(db, b, total_guests))

    if tasks:
        # Execute sequentially — AsyncSession is not safe for concurrent use in gather
        for task in tasks:
            try:
                await task
            except Exception as e:
                logger.error(f"Error updating tables: {str(e)}")
    
    # ОДИН общий commit для всех изменений
    await db.commit()


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(NoRateLimit), Depends(validate_csrf_dependency)])
async def delete_booking(
    request: Request,
    booking_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_staff_role),
):
    client_ip = request.client.host if request.client else "unknown"

    try:
        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(selectinload(Booking.restaurant))
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if not await validate_restaurant_access(booking.restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access to booking denied")

        if booking.status in StatusEnum.get_active_statuses():
            if booking.table_id:
                await SlotStateManager.cancel_booking(
                    restaurant_id=booking.restaurant_id,
                    date=booking.start_datetime.date(),
                    time=booking.start_datetime.time(),
                    table_id=booking.table_id,
                    db=db
                )
            else:
                await SlotStateManager.release_slot_without_table(
                    restaurant_id=booking.restaurant_id,
                    date=booking.start_datetime.date(),
                    time=booking.start_datetime.time(),
                    db=db
                )

        restaurant_id = booking.restaurant_id
        booking_date = booking.start_datetime.date()

        await db.delete(booking)
        await db.commit()

        await SlotStateManager.initialize_daily_slots(restaurant_id=restaurant_id, target_date=booking_date, db=db)
        await SlotStateManager._invalidate_cache(restaurant_id, booking_date)
        await SlotStateManager._publish_slot_update(restaurant_id, booking_date)
        await invalidate_slots_cache(restaurant_id, booking_date)

        restaurant = await db.get(Restaurant, restaurant_id)
        if restaurant:
            await publish_booking_update(booking, restaurant, deleted=True)

        logger.info("Booking deleted", booking_id=booking_id, user_id=current_user.id)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting booking", error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/", response_model=AdminBookingSchema, status_code=status.HTTP_201_CREATED, dependencies=[Depends(validate_csrf_dependency)])
async def create_admin_booking(
    request: Request,
    booking_data: BookingCreateAdmin,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_staff_role),
):
    client_ip = request.client.host if request.client else "unknown"
    logger.info("Admin booking creation started", user_id=current_user.id)

    try:
        restaurant = await db.scalar(
            select(Restaurant).where(
                Restaurant.slug == booking_data.restaurant_slug,
                Restaurant.is_published.is_(True)
            )
        )
        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")

        if not await validate_restaurant_access(restaurant.id, current_user):
            raise HTTPException(status_code=403, detail="Access to restaurant denied")

        await _validate_booking_data(booking_data, restaurant, db)

        total_guests = booking_data.adults + (booking_data.children or 0)
        
        # ВАЖНО: Передаем lock_value из запроса в сервис
        booking_result = await create_booking_with_tables(
            booking_data,
            db,
            is_admin=True,
            user_public_id=None,
            total_guests=total_guests,
            lock_value=booking_data.lock_value  # ← передаем lock_value из запроса
        )

        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking_result.id)
            .options(selectinload(Booking.table), selectinload(Booking.restaurant), selectinload(Booking.user_public))
        )
        booking = result.scalar_one()

        # Обновляем слоты в публичной части
        from app.services.slot_broadcast import broadcast_slots_update
        await broadcast_slots_update(restaurant_id=restaurant.id, target_date=booking_data.date)

        # Публикуем обновление
        await publish_booking_update(booking, restaurant)

        # Публикация в Redis
        event_data = {
            "type": "booking_created",
            "booking": AdminBookingSchema.from_orm(booking).dict(),
            "restaurant_slug": restaurant.slug,
            "timestamp": datetime.utcnow().isoformat()
        }
        await RedisService.call("publish", "booking_updates", json_dumps_custom(event_data), for_write=True)
        logger.debug("Booking creation event published to Redis", booking_id=booking.id)

        logger.info("Admin booking created", booking_id=booking.id, restaurant_id=restaurant.id)
        return AdminBookingSchema.from_orm(booking)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Admin booking creation error", error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

async def _validate_booking_data(booking_data: BookingCreateAdmin, restaurant: Restaurant, db: AsyncSession):
    is_valid_name, name_error = validate_person_name(booking_data.name)
    if not is_valid_name:
        raise HTTPException(status_code=400, detail=name_error)

    is_valid_phone, phone_normalized = validate_phone_number(booking_data.phone)
    if not is_valid_phone:
        raise HTTPException(status_code=400, detail=phone_normalized)
    booking_data.phone = phone_normalized

    moscow_now = get_moscow_now()
    if booking_data.date < moscow_now.date():
        raise HTTPException(status_code=400, detail="Cannot book past dates")

    from app.api.v1.public.bookings import validate_booking_limits
    await validate_booking_limits(restaurant.id, booking_data.phone, db)

    if booking_data.table_id:
        table = await db.get(Table, booking_data.table_id)
        if not table or table.restaurant_id != restaurant.id or not table.is_active:
            raise HTTPException(status_code=400, detail="Invalid table")
        total_guests = booking_data.adults + (booking_data.children or 0)
        if not table.can_accommodate(total_guests):
            raise HTTPException(status_code=400, detail="Table capacity does not match guest count")
        
@router.get("/{booking_id}/history", dependencies=[Depends(NoRateLimit)])
async def get_booking_history(
    request: Request,
    booking_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_staff_role),
):
    """Получить историю изменений статуса бронирования"""
    try:
        # Проверяем доступ к бронированию
        result = await db.execute(
            select(Booking).where(Booking.id == booking_id)
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if not await validate_restaurant_access(booking.restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access denied")

        # Получаем историю изменений
        from sqlalchemy import text
        query = text("""
            SELECT 
                id,
                old_status,
                new_status,
                changed_by_user_id,
                reason,
                changed_at
            FROM booking_history
            WHERE booking_id = :booking_id
            ORDER BY changed_at DESC
        """)
        
        result = await db.execute(query, {"booking_id": booking_id})
        history = []
        for row in result:
            history.append({
                "id": row[0],
                "old_status": row[1],
                "new_status": row[2],
                "changed_by_user_id": row[3],
                "reason": row[4],
                "changed_at": row[5].isoformat() if row[5] else None
            })
        
        return {"booking_id": booking_id, "history": history}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching booking history", booking_id=booking_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch booking history")


@router.get("/{booking_id}/suitable-tables")
async def get_booking_suitable_tables(
    request: Request,
    booking_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_staff_role),
):
    """Получить подходящие столы для конкретной брони"""
    client_ip = request.client.host if request.client else "unknown"

    try:
        result = await db.execute(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(selectinload(Booking.restaurant))
        )
        booking = result.scalar_one_or_none()
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if not await validate_restaurant_access(booking.restaurant_id, current_user):
            raise HTTPException(status_code=403, detail="Access to booking denied")

        from app.services.booking_service import get_suitable_tables_for_booking
        tables_payload = await get_suitable_tables_for_booking(booking_id, db)
        
        suitable_tables = tables_payload.get("suitable_tables", [])
        return {
            "booking_id": booking_id,
            **tables_payload,
            "total_count": len(suitable_tables)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting suitable tables", booking_id=booking_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")