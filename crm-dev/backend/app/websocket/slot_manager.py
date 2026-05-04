# app/websocket/slot_manager.py
import asyncio
import json
import uuid
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.db.models.restaurant import Restaurant
from app.services.redis_service import RedisService
from app.services.slot_generator import get_available_slots_for_frontend
import structlog
import re

logger = structlog.get_logger(__name__)

active_connections: dict = {}


async def broadcast(restaurant_slug: str, date: str, db: AsyncSession):
    key = f"{restaurant_slug}:{date}"
    if key not in active_connections:
        return

    result = await db.execute(
        select(Restaurant).where(Restaurant.slug == restaurant_slug)
    )
    restaurant = result.scalar_one_or_none()
    if not restaurant:
        return

    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return

    # NB: broadcast больше не вызывается автоматически — только по запросу
    # Это упрощает логику и избегает ошибки с отсутствующим total_guests


async def handle_slot_websocket(websocket: WebSocket, restaurant_slug: str, date: str):
    key = f"{restaurant_slug}:{date}"

    try:
        active_connections.setdefault(key, []).append(websocket)

        # Short-lived session for initial restaurant lookup only
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Restaurant).where(Restaurant.slug == restaurant_slug)
            )
            restaurant = result.scalar_one_or_none()
            if not restaurant:
                await websocket.send_text(json.dumps({"type": "error", "message": "Restaurant not found"}))
                await websocket.close(1008)
                return
            restaurant_id = restaurant.id

        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            await websocket.send_text(json.dumps({"type": "error", "message": "Invalid date format"}))
            await websocket.close(1008)
            return

        # НЕ отправляем initial_slots автоматически
        await websocket.send_text(json.dumps({
            "type": "ready",
            "message": "Send {action: 'request_initial_slots', total_guests: N}"
        }))

        while True:
            try:
                data = await websocket.receive_text()
                logger.info("WebSocket message received", data=data, restaurant_slug=restaurant_slug, date=date)

                msg = json.loads(data)
                action = msg.get("action")

                if action == "request_initial_slots":
                    total_guests = msg.get("total_guests")
                    if not isinstance(total_guests, int) or not (1 <= total_guests <= 20):
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Invalid total_guests (must be 1–20)"
                        }))
                        continue

                    try:
                        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
                        # Short-lived session per DB operation
                        async with AsyncSessionLocal() as db:
                            result = await db.execute(
                                select(Restaurant).where(Restaurant.id == restaurant_id)
                            )
                            restaurant = result.scalar_one_or_none()
                            if not restaurant:
                                await websocket.send_text(json.dumps({"type": "error", "message": "Restaurant not found"}))
                                continue
                            slots = await get_available_slots_for_frontend(
                                restaurant=restaurant,
                                target_date=date_obj,
                                db=db,
                                total_guests=total_guests
                            )
                        await websocket.send_text(json.dumps({
                            "type": "initial_slots",
                            "slots": slots
                        }))
                    except Exception as e:
                        logger.error("Failed to generate initial slots", error=str(e))
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Failed to load slots"
                        }))

                elif action == "lock_slot":
                    time_str = msg.get('time', '')
                    total_guests = msg.get('total_guests')
                    
                    if not time_str or not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
                        await websocket.send_text(json.dumps({"type": "error", "message": "Invalid time format"}))
                        continue

                    if not isinstance(total_guests, int) or not (1 <= total_guests <= 20):
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Invalid total_guests (must be 1–20)"
                        }))
                        continue

                    try:
                        time_obj = datetime.strptime(time_str, "%H:%M").time()
                        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
                    except ValueError:
                        await websocket.send_text(json.dumps({"type": "error", "message": "Invalid time format"}))
                        continue

                    # Short-lived session for availability check
                    slot_available = False
                    try:
                        async with AsyncSessionLocal() as db:
                            result = await db.execute(
                                select(Restaurant).where(Restaurant.id == restaurant_id)
                            )
                            restaurant = result.scalar_one_or_none()
                            if restaurant:
                                slots = await get_available_slots_for_frontend(
                                    restaurant=restaurant,
                                    target_date=date_obj,
                                    db=db,
                                    total_guests=total_guests
                                )
                                for slot in slots:
                                    if slot.get("time") == time_str and slot.get("available", False):
                                        slot_available = True
                                        break
                        
                        if not slot_available:
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "message": "Not available"
                            }))
                            continue
                    except Exception as e:
                        logger.error("Failed to check slot availability", error=str(e))
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Failed to check availability"
                        }))
                        continue

                    # Redis key без total_guests — блокируем слот как единое целое
                    redis_key = f"slot_lock:{restaurant_id}:{date}:{time_str}"

                    lock_value = str(uuid.uuid4())
                    locked = await RedisService.call("set", redis_key, lock_value, ex=120, nx=True, for_write=True)
                    if not locked:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Slot already locked"
                        }))
                        continue
                    logger.info("Slot locked in Redis (atomic)", 
                              key=redis_key, 
                              lock_value=lock_value,
                              total_guests=total_guests)

                    await websocket.send_text(json.dumps({
                        "type": "slot_locked",
                        "time": time_str,
                        "lock_value": lock_value
                    }))

                elif action == "unlock_slot":
                    time_str = msg.get('time', '')
                    lock_value_to_check = msg.get('lock_value')

                    if not time_str or not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
                        await websocket.send_text(json.dumps({"type": "error", "message": "Invalid time format"}))
                        continue

                    redis_key = f"slot_lock:{restaurant_id}:{date}:{time_str}"

                    if lock_value_to_check:
                        existing_lock = await RedisService.call("get", redis_key)
                        if existing_lock == lock_value_to_check:
                            await RedisService.call("delete", redis_key, for_write=True)
                            logger.info("Slot unlocked in Redis", key=redis_key)
                        else:
                            logger.warning("Unlock attempt with invalid lock value",
                                         key=redis_key,
                                         expected=lock_value_to_check,
                                         actual=existing_lock)
                    else:
                        # Unlock без проверки владельца — только с предупреждением
                        logger.warning("Slot unlocked without ownership verification",
                                     key=redis_key, client=str(websocket.client))
                        await RedisService.call("delete", redis_key, for_write=True)
                        logger.info("Slot unlocked in Redis (no lock_value check)", key=redis_key)

                    await websocket.send_text(json.dumps({"type": "slot_unlocked", "time": time_str}))

                elif action == "booking_confirmed":
                    time_slot = msg.get("time")
                    if time_slot:
                        await websocket.send_text(json.dumps({
                            "type": "slot_unlocked",
                            "time": time_slot,
                            "reason": "booking_confirmed"
                        }))

                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Unknown action"
                    }))

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
            except Exception as e:
                logger.error("Slot WS error", error=str(e))
                break

    except Exception as e:
        logger.error("Slot WS setup error", error=str(e))
    finally:
        if key in active_connections and websocket in active_connections[key]:
            active_connections[key].remove(websocket)
            if not active_connections[key]:
                del active_connections[key]