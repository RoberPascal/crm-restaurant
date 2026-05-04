# app/api/v1/public/bookings.py
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import Response
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, date
from typing import Optional
from app.db.session import get_async_db
from app.db.models.booking import Booking, StatusEnum
from app.db.models.restaurant import Restaurant
from app.db.models.user_public import UserPublic
from app.schemas.booking import BookingCreatePublic, BookingPublicResponse
from app.services.booking_service import create_booking_with_tables, publish_booking_cancelled, publish_booking_delay_notification
from app.services.redis_service import RedisService
from app.services.slot_state_manager import SlotStateManager
from app.core.security import validate_restaurant_slug
from app.core.time_utils import get_moscow_now, to_moscow_time
from app.core.rate_limiter import public_rate_limit, public_write_rate_limit
from sqlalchemy.exc import IntegrityError
import structlog
import re

logger = structlog.get_logger(__name__)
router = APIRouter()


async def NoRateLimit():
    """Заглушка для обратной совместимости"""
    return None


async def validate_booking_limits(restaurant_id: int, client_phone: str, db: AsyncSession) -> None:
    """Лимит 3 активных брони на сегодня по номеру телефона"""
    today = get_moscow_now().date()

    count = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.restaurant_id == restaurant_id,
            Booking.phone == client_phone,
            func.date(Booking.start_datetime) == today,
            Booking.status.in_([StatusEnum.pending, StatusEnum.confirmed, StatusEnum.assigned])
        )
    )

    if count >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily booking limit exceeded (max 3 per day)"
        )


async def ensure_single_booking_per_day(user_public_id: int, booking_date: date, db: AsyncSession) -> None:
    """Гарантирует, что у пользователя только одна активная бронь на выбранную дату."""
    if not user_public_id:
        return

    active_statuses = StatusEnum.get_active_statuses()
    existing = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.user_public_id == user_public_id,
            func.date(Booking.start_datetime) == booking_date,
            Booking.status.in_(active_statuses),
        )
    )

    if existing and existing > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="У вас уже есть активная бронь на эту дату",
        )


async def ensure_single_booking_created_today(
    telegram_user_id: Optional[int], db: AsyncSession
) -> None:
    """Запрещает создавать больше одной активной брони за текущий день."""
    if not telegram_user_id:
        return

    today = get_moscow_now().date()
    count = await db.scalar(
        select(func.count(Booking.id))
        .join(UserPublic, Booking.user_public_id == UserPublic.id)
        .where(
            UserPublic.telegram_user_id == telegram_user_id,
            func.date(Booking.created_at) == today,
            Booking.status.in_(StatusEnum.get_active_statuses()),
        )
    )

    if count and count > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Сегодня вы уже создавали бронь. Отмените текущую, чтобы оформить новую.",
        )


def sanitize_phone_number(phone: str) -> str:
    cleaned = re.sub(r'[^\d+]', '', phone)
    if cleaned.startswith('8'):
        cleaned = '+7' + cleaned[1:]
    elif cleaned.startswith('7'):
        cleaned = '+' + cleaned
    if not re.match(r'^\+7\d{10}$', cleaned):
        raise HTTPException(status_code=400, detail="Invalid phone number format")
    return cleaned


@router.options("/", include_in_schema=False)
async def options_bookings(request: Request):
    from app.core.config import settings
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and origin in settings.safe_cors_origins else None
    headers = {
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-WebApp-Source",
        "Access-Control-Max-Age": "86400",
    }
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
        headers["Access-Control-Allow-Credentials"] = "true"
    else:
        headers["Access-Control-Allow-Origin"] = "*"
    return Response(status_code=200, headers=headers)


async def get_or_create_user_from_telegram(telegram_data: dict, db: AsyncSession) -> Optional[UserPublic]:
    telegram_user_id = telegram_data.get("id")
    if not telegram_user_id:
        return None

    result = await db.execute(select(UserPublic).where(UserPublic.telegram_user_id == telegram_user_id))
    user = result.scalar_one_or_none()
    if user:
        return user

    # Handle race condition: another request may create the user concurrently
    try:
        async with db.begin_nested():
            user = UserPublic(
                telegram_user_id=telegram_user_id,
                username=telegram_data.get("username"),
                first_name=telegram_data.get("first_name"),
                last_name=telegram_data.get("last_name"),
            )
            db.add(user)
            await db.flush()
        logger.info("Created new Telegram user", user_id=user.id, telegram_id=telegram_user_id)
        return user
    except IntegrityError:
        # Another request already created this user — fetch it
        await db.rollback()
        result = await db.execute(select(UserPublic).where(UserPublic.telegram_user_id == telegram_user_id))
        return result.scalar_one_or_none()


@router.post(
    "/",
    response_model=BookingPublicResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(public_write_rate_limit)]
)
async def create_booking(
    request: Request,
    booking: BookingCreatePublic,
    db: AsyncSession = Depends(get_async_db)
):
    client_ip = request.client.host if request.client else "unknown"

    try:
        # === ВАЛИДАЦИЯ ===
        if not validate_restaurant_slug(booking.restaurant_slug):
            raise HTTPException(status_code=400, detail="Invalid restaurant slug")

        booking.phone = sanitize_phone_number(booking.phone)

        if not (2 <= len(booking.name.strip()) <= 50):
            raise HTTPException(status_code=400, detail="Invalid client name length")

        total_guests = booking.adults + booking.children
        if total_guests < 1:
            raise HTTPException(status_code=400, detail="At least one guest required")

        # === ИДЕМПОТЕНТНОСТЬ ===
        if booking.idempotency_key:
            redis_exists = await RedisService.call("exists", f"idempotency:{booking.idempotency_key}")
            if redis_exists:
                raise HTTPException(status_code=409, detail="Duplicate booking")
            elif redis_exists is None:
                exists = await db.scalar(select(1).where(Booking.idempotency_key == booking.idempotency_key))
                if exists:
                    raise HTTPException(status_code=409, detail="Duplicate booking")

        # === РЕСТОРАН ===
        restaurant = await db.scalar(
            select(Restaurant).where(
                Restaurant.slug == booking.restaurant_slug,
                Restaurant.is_published.is_(True)
            )
        )
        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")

        # === ВРЕМЯ БРОНИРОВАНИЯ ===
        moscow_now = get_moscow_now()
        if booking.date < moscow_now.date():
            raise HTTPException(status_code=400, detail="Cannot book past dates")

        # === ЛИМИТЫ ПО ТЕЛЕФОНУ ===
        await validate_booking_limits(restaurant.id, booking.phone, db)

        # === ПОЛЬЗОВАТЕЛЬ ИЗ ТЕЛЕГРАМА ===
        user_public = None
        telegram_user = booking.telegram_user
        if not telegram_user:
            from app.core.security import get_telegram_user_from_request
            telegram_user = get_telegram_user_from_request(request)

        telegram_user_id = telegram_user.get("id") if telegram_user else None

        if telegram_user_id:
            user_public = await get_or_create_user_from_telegram(telegram_user, db)
        if user_public and booking.profile_update:
            upd = booking.profile_update
            if upd.phone is not None: user_public.phone = upd.phone
            if upd.first_name is not None: user_public.first_name = upd.first_name
            if upd.last_name is not None: user_public.last_name = upd.last_name
            if upd.allergies is not None: user_public.allergies = upd.allergies
            user_public.updated_at = datetime.utcnow()
            await db.commit()

        if user_public:
            await ensure_single_booking_per_day(user_public.id, booking.date, db)
            await ensure_single_booking_created_today(
                user_public.telegram_user_id, db
            )
        elif telegram_user_id:
            await ensure_single_booking_created_today(telegram_user_id, db)


        # === СОЗДАНИЕ БРОНИ ===
        created = await create_booking_with_tables(
            booking_data=booking,
            db=db,
            is_admin=False,
            user_public_id=user_public.id if user_public else None,
            total_guests=total_guests,
            lock_value=booking.lock_value  # если поле добавлено в схему
        )

        if created.status != StatusEnum.confirmed:
            created.status = StatusEnum.confirmed
            await db.commit()
            await db.refresh(created)

        # Сохраняем idempotency key
        if booking.idempotency_key:
            await RedisService.call("setex", f"idempotency:{booking.idempotency_key}", 3600, str(created.id), for_write=True)

        # Рассылаем обновление слотов
        from app.services.slot_broadcast import broadcast_slots_update
        await broadcast_slots_update(restaurant_id=restaurant.id, target_date=booking.date)

        logger.info("Public booking created", booking_id=created.id, restaurant=booking.restaurant_slug)
        return BookingPublicResponse.from_orm(created)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Public booking creation failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/me", response_model=list[BookingPublicResponse])
async def get_my_bookings(request: Request, db: AsyncSession = Depends(get_async_db)):
    from app.core.security import get_telegram_user_from_request
    telegram_user = get_telegram_user_from_request(request) or {}
    telegram_id = telegram_user.get("id")
    if not telegram_id:
        return []  # No authenticated Telegram user

    user = await db.scalar(select(UserPublic).where(UserPublic.telegram_user_id == telegram_id))
    if not user:
        return []

    # ИСПРАВЛЕНИЕ: Добавляем загрузку связанных данных ресторана
    result = await db.execute(
        select(Booking)
        .join(Booking.restaurant)  # Явное соединение с рестораном
        .where(Booking.user_public_id == user.id)
        .options(
            selectinload(Booking.restaurant),  # Загружаем данные ресторана
            selectinload(Booking.table)
        )
        .order_by(Booking.start_datetime.desc())
    )
    
    bookings = result.scalars().all()
    
    # Преобразуем в response model с добавлением данных ресторана
    response_bookings = []
    for booking in bookings:
        booking_data = BookingPublicResponse.from_orm(booking)
        
        # Добавляем данные ресторана если они есть
        if booking.restaurant:
            booking_data.restaurant_name = booking.restaurant.name
            booking_data.restaurant_slug = booking.restaurant.slug
            
        response_bookings.append(booking_data)
    
    return response_bookings


@router.patch("/{booking_id}/cancel", response_model=BookingPublicResponse, dependencies=[Depends(public_write_rate_limit)])
async def cancel_my_booking(booking_id: int, request: Request, db: AsyncSession = Depends(get_async_db)):
    client_ip = request.client.host if request.client else "unknown"

    try:
        from app.core.security import get_telegram_user_from_request
        telegram_user = get_telegram_user_from_request(request) or {}
        telegram_id = telegram_user.get("id")
        if not telegram_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        user = await db.scalar(select(UserPublic).where(UserPublic.telegram_user_id == telegram_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        booking = await db.scalar(
            select(Booking)
            .where(Booking.id == booking_id, Booking.user_public_id == user.id)
            .options(selectinload(Booking.restaurant), selectinload(Booking.table))
        )
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # ИСПРАВЛЕНИЕ: Приводим оба времени к naive для сравнения
        booking_datetime = to_moscow_time(booking.start_datetime)
        now_moscow = get_moscow_now()

        # Убедимся, что оба времени либо aware, либо naive
        if booking_datetime.tzinfo is not None and now_moscow.tzinfo is not None:
            # Оба aware - можно сравнивать напрямую
            if booking_datetime < now_moscow:
                raise HTTPException(status_code=400, detail="Cannot cancel past booking")
        else:
            # Приводим к naive для сравнения
            booking_naive = booking_datetime.replace(tzinfo=None) if booking_datetime.tzinfo else booking_datetime
            now_naive = now_moscow.replace(tzinfo=None) if now_moscow.tzinfo else now_moscow
            
            if booking_naive < now_naive:
                raise HTTPException(status_code=400, detail="Cannot cancel past booking")

        if booking.status in [StatusEnum.cancelled, StatusEnum.no_show, StatusEnum.completed]:
            raise HTTPException(status_code=400, detail=f"Already {booking.status.value}")

        old_status = booking.status
        booking.status = StatusEnum.cancelled
        await db.commit()
        await db.refresh(booking)

        # Освобождаем слот
        if old_status in [StatusEnum.assigned, StatusEnum.confirmed]:
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

        from app.services.slot_broadcast import broadcast_slots_update
        await broadcast_slots_update(restaurant_id=booking.restaurant_id, target_date=booking.start_datetime.date())
        
        # Публикуем событие отмены
        restaurant = await db.scalar(select(Restaurant).where(Restaurant.id == booking.restaurant_id))
        if restaurant:
            await publish_booking_cancelled(booking, restaurant, db, cancelled_by="user")

        logger.info("Booking cancelled by user", booking_id=booking_id)
        return BookingPublicResponse.from_orm(booking)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Cancel booking error", error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500)


@router.delete("/{booking_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(public_write_rate_limit)])
async def delete_my_booking(booking_id: int, request: Request, db: AsyncSession = Depends(get_async_db)):
    """Полное удаление брони пользователем без каких-либо ограничений."""
    client_ip = request.client.host if request.client else "unknown"

    try:
        from app.core.security import get_telegram_user_from_request
        telegram_user = get_telegram_user_from_request(request) or {}
        telegram_id = telegram_user.get("id")
        if not telegram_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        user = await db.scalar(select(UserPublic).where(UserPublic.telegram_user_id == telegram_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        booking = await db.scalar(
            select(Booking)
            .where(Booking.id == booking_id, Booking.user_public_id == user.id)
            .options(selectinload(Booking.restaurant), selectinload(Booking.table))
        )
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # Защита: нельзя удалять завершённые, arrived, completed, no_show брони
        if booking.status in [StatusEnum.arrived, StatusEnum.completed, StatusEnum.no_show]:
            raise HTTPException(
                status_code=400,
                detail=f"Нельзя удалить бронь в статусе {booking.status.value}"
            )

        # Освобождаем слот перед удалением
        if booking.status in [StatusEnum.assigned, StatusEnum.confirmed, StatusEnum.pending, StatusEnum.pending_review]:
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
        
        # Публикуем событие отмены перед удалением
        restaurant = await db.scalar(select(Restaurant).where(Restaurant.id == restaurant_id))
        if restaurant:
            await publish_booking_cancelled(booking, restaurant, db, cancelled_by="user")

        # Удаляем бронь из БД
        await db.delete(booking)
        await db.commit()

        # Уведомляем о изменении слотов
        from app.services.slot_broadcast import broadcast_slots_update
        await broadcast_slots_update(restaurant_id=restaurant_id, target_date=booking_date)

        logger.info("Booking deleted by user", booking_id=booking_id, user_id=user.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete booking error", error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500)


@router.post("/{booking_id}/notify-delay", dependencies=[Depends(public_write_rate_limit)])
async def notify_booking_delay(
    booking_id: int, 
    delay_minutes: Optional[int] = None,
    request: Request = None, 
    db: AsyncSession = Depends(get_async_db)
):
    """Уведомить персонал об опоздании на бронирование"""
    try:
        from app.core.security import get_telegram_user_from_request
        telegram_user = get_telegram_user_from_request(request) or {}
        telegram_id = telegram_user.get("id")
        if not telegram_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        user = await db.scalar(select(UserPublic).where(UserPublic.telegram_user_id == telegram_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        booking = await db.scalar(
            select(Booking)
            .where(Booking.id == booking_id, Booking.user_public_id == user.id)
            .options(selectinload(Booking.restaurant))
        )
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if booking.status in [StatusEnum.cancelled, StatusEnum.no_show, StatusEnum.completed]:
            raise HTTPException(status_code=400, detail=f"Cannot notify delay for {booking.status.value} booking")

        # Устанавливаем флаг опоздания
        booking.delay_notified = True
        await db.commit()
        await db.refresh(booking)

        # Публикуем событие опоздания
        restaurant = await db.scalar(select(Restaurant).where(Restaurant.id == booking.restaurant_id))
        if restaurant:
            await publish_booking_delay_notification(booking, restaurant, db, delay_minutes=delay_minutes)

        logger.info("Booking delay notification sent", booking_id=booking_id, delay_minutes=delay_minutes)
        return {"status": "ok", "message": "Уведомление отправлено"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete booking error", error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500)