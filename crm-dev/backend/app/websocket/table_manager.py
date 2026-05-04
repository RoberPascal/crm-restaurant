# app/websocket/table_manager.py
import asyncio
import json
import uuid
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from app.db.session import AsyncSessionLocal
from app.db.models.restaurant import Restaurant
from app.db.models.booking import Booking, StatusEnum
from app.db.models.table import Table
from app.services.redis_service import RedisService
import structlog
import re

logger = structlog.get_logger(__name__)

active_table_connections: dict = {}


async def get_available_tables(
    restaurant_id: int,
    date_obj: datetime.date,
    time_obj: datetime.time,
    total_guests: int,
    db: AsyncSession
):
    """
    Получить доступные столы по количеству гостей (seats_min/seats_max), без категорий.
    """
    # Получаем активные столы, подходящие по вместимости
    tables_result = await db.execute(
        select(Table).where(
            Table.restaurant_id == restaurant_id,
            Table.is_active.is_(True),
            Table.seats_min <= total_guests,
            Table.seats_max >= total_guests,
        )
    )
    all_tables = tables_result.scalars().all()
    table_ids = [t.id for t in all_tables]

    if not table_ids:
        return []

    # Получаем ресторан для определения времени закрытия
    restaurant_result = await db.execute(
        select(Restaurant).where(Restaurant.id == restaurant_id)
    )
    restaurant = restaurant_result.scalar_one_or_none()
    if not restaurant:
        return []
    
    # Получаем время закрытия
    from app.services.slot_state_manager import SlotStateManager
    from datetime import datetime as dt
    closing_time_dt = SlotStateManager._get_closing_time(restaurant, date_obj)
    slot_dt = dt.combine(date_obj, time_obj)
    
    # Получаем все активные брони на эту дату
    active_statuses = [
        StatusEnum.pending,
        StatusEnum.pending_review,
        StatusEnum.confirmed,
        StatusEnum.assigned,
        StatusEnum.arrived
    ]
    
    # ИСПРАВЛЕНО: Booking.date не существует - используем start_datetime
    from datetime import timedelta as td
    start_of_day = dt.combine(date_obj, dt.min.time())
    end_of_day = start_of_day + td(days=1)
    
    bookings_result = await db.execute(
        select(Booking).where(
            Booking.restaurant_id == restaurant_id,
            Booking.start_datetime >= start_of_day,
            Booking.start_datetime < end_of_day,
            Booking.status.in_(active_statuses),
            Booking.table_id.in_(table_ids) if table_ids else False
        )
    )
    all_bookings = bookings_result.scalars().all()
    
    # Стол забронирован, если он занят в этот слот
    booked_table_ids = set()
    for b in all_bookings:
        if not b.table_id:
            continue
        b_start_dt = b.start_datetime if b.start_datetime else None
        b_end_dt = b.end_datetime if b.end_datetime else closing_time_dt
        if b_start_dt and b_start_dt <= slot_dt < (b_end_dt or closing_time_dt):
            booked_table_ids.add(b.table_id)

    # Возвращаем только свободные
    return [
        {
            "id": t.id,
            "number": t.number,
            "location_mark": t.location_mark,
            "seats_min": t.seats_min,
            "seats_max": t.seats_max
        }
        for t in all_tables
        if t.id not in booked_table_ids
    ]


async def handle_table_websocket(websocket: WebSocket, restaurant_slug: str, date: str, time: str):
    key = f"{restaurant_slug}:{date}:{time[:5]}"

    try:
        # ПРИМЕЧАНИЕ: accept() уже вызван в main.py перед вызовом handle_table_websocket
        active_table_connections.setdefault(key, []).append(websocket)

        # Short-lived session for initial restaurant lookup only
        async with AsyncSessionLocal() as db:
            restaurant_result = await db.execute(
                select(Restaurant).where(Restaurant.slug == restaurant_slug)
            )
            restaurant = restaurant_result.scalar_one_or_none()
            if not restaurant:
                await websocket.close(1008)
                return
            restaurant_id = restaurant.id

        time_norm = time[:5]
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            time_obj = datetime.strptime(time_norm, "%H:%M").time()
        except ValueError:
            await websocket.send_text(json.dumps({"type": "error", "message": "Invalid date/time"}))
            return

        # НЕ отправляем initial_tables с hardcoded guests — ждём request_tables от клиента
        await websocket.send_text(json.dumps({
            "type": "ready",
            "message": "Send {action: 'request_tables', total_guests: N}"
        }))

        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)

                if msg.get("action") == "request_tables":
                    req_guests = msg.get("total_guests")
                    if not isinstance(req_guests, int) or not (1 <= req_guests <= 20):
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Invalid total_guests (must be 1–20)"
                        }))
                        continue
                    # Short-lived session per DB operation
                    async with AsyncSessionLocal() as db:
                        tables = await get_available_tables(restaurant_id, date_obj, time_obj, req_guests, db)
                    await websocket.send_text(json.dumps({"type": "initial_tables", "tables": tables}))

                elif msg.get("action") == "lock_table":
                    table_id = msg.get('table_id')
                    if not isinstance(table_id, int) or table_id <= 0:
                        await websocket.send_text(json.dumps({"type": "error", "message": "Invalid table_id"}))
                        continue

                    # Short-lived session for table check + booking check
                    async with AsyncSessionLocal() as db:
                        # Проверить, что стол свободен и подходит
                        table = await db.get(Table, table_id)
                        if not table or table.restaurant_id != restaurant_id or not table.is_active:
                            await websocket.send_text(json.dumps({"type": "error", "message": "Table not found"}))
                            continue

                        # Проверить, не забронирован ли (полная проверка пересечения времени)
                        from datetime import timedelta as td
                        check_start = datetime.combine(date_obj, time_obj)
                        check_end = check_start + td(hours=2)  # Проверяем окно 2 часа
                        booking = await db.scalar(
                            select(Booking.id).where(
                                Booking.restaurant_id == restaurant_id,
                                Booking.table_id == table_id,
                                Booking.status.in_([StatusEnum.pending, StatusEnum.confirmed, StatusEnum.assigned]),
                                # Проверка перекрытия: existing.start < check_end AND existing.end > check_start
                                Booking.start_datetime < check_end,
                                or_(
                                    Booking.end_datetime > check_start,
                                    and_(Booking.end_datetime.is_(None), Booking.start_datetime >= check_start)
                                )
                            )
                        )
                    if booking:
                        await websocket.send_text(json.dumps({"type": "error", "message": "Table already booked"}))
                        continue

                    lock_value = str(uuid.uuid4())
                    redis_key = f"table_lock:{restaurant_id}:{date}:{time_norm}:{table_id}"
                    locked = await RedisService.call("set", redis_key, lock_value, ex=120, nx=True, for_write=True)

                    if not locked:
                        await websocket.send_text(json.dumps({"type": "error", "message": "Table already locked"}))
                        continue

                    await websocket.send_text(json.dumps({
                        "type": "table_locked",
                        "table_id": table_id,
                        "lock_value": lock_value
                    }))

                elif msg.get("action") == "unlock_table":
                    table_id = msg.get('table_id')
                    expected_lock = msg.get('lock_value')
                    if not isinstance(table_id, int) or table_id <= 0:
                        continue
                    redis_key = f"table_lock:{restaurant_id}:{date}:{time_norm}:{table_id}"
                    # Verify ownership before deleting
                    current_lock = await RedisService.call("get", redis_key)
                    if current_lock and current_lock == expected_lock:
                        await RedisService.call("delete", redis_key, for_write=True)
                        await websocket.send_text(json.dumps({"type": "table_unlocked", "table_id": table_id}))
                    elif not current_lock:
                        # Lock already expired — treat as unlocked
                        await websocket.send_text(json.dumps({"type": "table_unlocked", "table_id": table_id}))
                    else:
                        logger.warning("Table unlock denied — lock ownership mismatch",
                                       table_id=table_id, expected=expected_lock, actual=current_lock)

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error("Table WS error", error=str(e))
                break

    except Exception as e:
        logger.error("Table WS setup error", error=str(e))
    finally:
        if key in active_table_connections and websocket in active_table_connections[key]:
            active_table_connections[key].remove(websocket)
            if not active_table_connections[key]:
                del active_table_connections[key]
        