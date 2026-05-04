# app/websocket/slot_state_ws.py
import asyncio
import json
import uuid
import re
from datetime import date, datetime
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.db.models.restaurant import Restaurant
from app.services.redis_service import RedisService
from app.services.slot_generator import get_available_slots_for_frontend
from app.services.slot_state_manager import SlotStateManager
import structlog

logger = structlog.get_logger(__name__)


async def _fetch_slots(restaurant_id: int, restaurant_slug: str, date_obj: date, total_guests=None):
    """Fetch slots using a short-lived DB session to avoid pool exhaustion."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
        restaurant = result.scalar_one_or_none()
        if not restaurant:
            return None
        return await get_available_slots_for_frontend(
            restaurant=restaurant,
            target_date=date_obj,
            db=db,
            total_guests=total_guests,
        )


async def handle_slot_state_websocket(
    websocket: WebSocket,
    restaurant_slug: str,
    date_str: str,
):
    pubsub = None
    action_task = None
    # Получаем начальное количество гостей из query параметров (если есть)
    query_guests = websocket.query_params.get("guests")
    client_total_guests: int | None = None
    if query_guests and query_guests.isdigit():
        val = int(query_guests)
        if 1 <= val <= 20:
            client_total_guests = val

    active_lock_key = None
    active_lock_value = None

    try:
        # Валидация даты
        try:
            date_obj = date.fromisoformat(date_str)
        except ValueError:
            await websocket.send_json({"type": "error", "message": "Invalid date format"})
            return

        # Short-lived session ONLY for initial restaurant lookup
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Restaurant).where(Restaurant.slug == restaurant_slug))
            restaurant = result.scalar_one_or_none()
            if not restaurant:
                await websocket.send_json({"type": "error", "message": "Restaurant not found"})
                return
            restaurant_id = restaurant.id

        # Отправляем начальное состояние
        initial_msg = {
            "type": "connection_status",
            "connected": True,
            "date": date_str,
        }
        
        if client_total_guests:
            initial_msg["total_guests"] = client_total_guests
            # Сразу отправляем начальные слоты
            fresh_slots = await _fetch_slots(restaurant_id, restaurant_slug, date_obj, total_guests=client_total_guests)
            await websocket.send_json({
                "type": "initial_slots",
                "slots": fresh_slots or [],
                "date": date_str,
            })
        else:
            initial_msg["message"] = "Send {action: 'request_initial_slots', total_guests: N}"
            
        await websocket.send_json(initial_msg)

        # Подписка на Redis
        redis_conn = await RedisService.ensure_connection()
        if redis_conn:
            pubsub = redis_conn.pubsub()
            channel = f"slot_updates:{restaurant_id}:{date_str}"
            await pubsub.subscribe(channel)
            logger.info("WS subscribed", channel=channel)

        # Обработчик действий клиента
        async def handle_client_actions():
            nonlocal client_total_guests, active_lock_key, active_lock_value
            try:
                while True:
                    data = await websocket.receive_text()
                    try:
                        msg = json.loads(data)
                    except json.JSONDecodeError:
                        await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                        continue

                    action = msg.get("action")
                    
                    # Ping/pong для keepalive
                    if action == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue
                    
                    if action == "lock_slot":
                        time_str = msg.get("time", "")
                        total_guests = msg.get("total_guests")
                        end_time = msg.get("end_time")

                        # ИСПРАВЛЕНИЕ: запоминаем total_guests для последующих Redis-broadcast
                        if isinstance(total_guests, int) and 1 <= total_guests <= 20:
                            client_total_guests = total_guests

                        if not time_str or not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
                            await websocket.send_json({"type": "error", "message": "Invalid time format"})
                            continue
                        if not isinstance(total_guests, int) or not (1 <= total_guests <= 20):
                            await websocket.send_json({"type": "error", "message": "Invalid total_guests"})
                            continue

                        # Short-lived session for slot availability check
                        check_slots = await _fetch_slots(restaurant_id, restaurant_slug, date_obj, total_guests=total_guests)
                        slot_available = any(
                            slot.get("time") == time_str and slot.get("available", False)
                            for slot in (check_slots or [])
                        )

                        if not slot_available:
                            await websocket.send_json({"type": "error", "message": "Not available"})
                            continue

                        # Блокировка в Redis — ЕДИНЫЙ формат ключа (без total_guests)
                        redis_key = f"slot_lock:{restaurant_id}:{date_str}:{time_str}"
                        lock_value = str(uuid.uuid4())

                        locked = await RedisService.call(
                            "set",
                            redis_key,
                            lock_value,
                            ex=120,
                            nx=True,
                            for_write=True,
                        )

                        if locked is None:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Сервис блокировок временно недоступен, попробуйте позже"
                            })
                            logger.error(
                                "Slot lock failed due to Redis unavailability",
                                restaurant_slug=restaurant_slug,
                                time=time_str,
                                total_guests=total_guests,
                            )
                            continue

                        if locked:
                            active_lock_key = redis_key
                            active_lock_value = lock_value
                            await websocket.send_json({
                                "type": "slot_locked",
                                "time": time_str,
                                "lock_value": lock_value,
                                "end_time": end_time
                            })
                            logger.info(
                                "Slot locked successfully",
                                restaurant_slug=restaurant_slug,
                                time=time_str,
                                lock_value=lock_value,
                                total_guests=total_guests,
                            )
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Slot already locked"
                            })
                            logger.warning(
                                "Slot already locked",
                                restaurant_slug=restaurant_slug,
                                time=time_str,
                                total_guests=total_guests,
                            )

                    elif action == "unlock_slot":
                        time_str = msg.get("time", "")
                        lock_value = msg.get("lock_value")
                        total_guests = msg.get("total_guests")

                        if not time_str or not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
                            continue

                        redis_key = f"slot_lock:{restaurant_id}:{date_str}:{time_str}"

                        current_lock = await RedisService.call(
                            "get",
                            redis_key,
                        )

                        if current_lock and current_lock == lock_value:
                            await RedisService.call(
                                "delete",
                                redis_key,
                                for_write=True,
                            )
                            active_lock_key = None
                            active_lock_value = None
                            await websocket.send_json({
                                "type": "slot_unlocked",
                                "time": time_str
                            })
                            logger.info(
                                "Slot unlocked successfully",
                                restaurant_slug=restaurant_slug,
                                time=time_str,
                                total_guests=total_guests,
                            )
                        else:
                            logger.warning(
                                "Slot unlock failed - lock mismatch or not found",
                                restaurant_slug=restaurant_slug,
                                time=time_str,
                                expected_lock=lock_value,
                                actual_lock=current_lock,
                            )

                    elif action == "request_initial_slots":
                        # ИСПРАВЛЕНИЕ: запоминаем total_guests для последующих Redis-broadcast
                        req_guests = msg.get("total_guests")
                        if isinstance(req_guests, int) and 1 <= req_guests <= 20:
                            client_total_guests = req_guests
                        # Short-lived session for fresh slots
                        fresh_slots = await _fetch_slots(restaurant_id, restaurant_slug, date_obj, total_guests=client_total_guests)
                        await websocket.send_json({
                            "type": "initial_slots",
                            "slots": fresh_slots or [],
                            "date": date_str,
                        })

            except WebSocketDisconnect:
                logger.info("Client WebSocket disconnected", restaurant_slug=restaurant_slug)
            except Exception as e:
                logger.error("Client action error", error=str(e), restaurant_slug=restaurant_slug, exc_info=True)
                try:
                    await websocket.send_json({
                        "type": "error", 
                        "message": "Internal server error"
                    })
                except:
                    pass

        # Запускаем обработчик действий
        action_task = asyncio.create_task(handle_client_actions())

        # Основной цикл: слушаем Redis
        if pubsub:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    # ИСПРАВЛЕНИЕ: Проверяем состояние WebSocket перед отправкой
                    # чтобы избежать ошибки "websocket.send after websocket.close"
                    if websocket.client_state != WebSocketState.CONNECTED:
                        logger.info("WebSocket disconnected, stopping Redis listener", restaurant_slug=restaurant_slug)
                        break

                    payload = json.loads(message["data"])
                    if payload.get("action") == "slots_refresh":
                        # Если количество гостей у клиента еще не определено - игнорируем общее обновление,
                        # так как мы не знаем, какие именно столы ему показывать.
                        if client_total_guests is None:
                            continue
                            
                        fresh_slots = await _fetch_slots(restaurant_id, restaurant_slug, date_obj, total_guests=client_total_guests)
                        await websocket.send_json({
                            "type": "slots_updated",
                            "slots": fresh_slots or [],
                            "date": date_str,
                        })
                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected during Redis listen", restaurant_slug=restaurant_slug)
                    break
                except Exception as e:
                    # ИСПРАВЛЕНИЕ: Проверяем, не закрыт ли WS после ошибки
                    if "close" in str(e).lower() or "disconnect" in str(e).lower():
                        logger.info("WebSocket closed, stopping Redis listener", restaurant_slug=restaurant_slug)
                        break
                    logger.error("Redis message error", error=str(e))
        else:
            await action_task

    except WebSocketDisconnect:
        logger.info("Slot WS disconnected", restaurant_slug=restaurant_slug, date=date_str)
    except Exception as e:
        logger.error("Slot WS error", error=str(e), restaurant_slug=restaurant_slug, date=date_str, exc_info=True)
    finally:
        # Cancel action_task to prevent resource leak
        if action_task:
            action_task.cancel()
            try:
                await action_task
            except asyncio.CancelledError:
                pass # Task was cancelled, expected behavior
            except Exception as e:
                logger.error("Error awaiting cancelled action_task", error=str(e))

        if pubsub:
            try:
                await pubsub.unsubscribe()
                await pubsub.close()
            except Exception as e:
                logger.debug("Error closing pubsub", error=str(e))
        
        # Автоматическая разблокировка при разрыве соединения
        if active_lock_key and active_lock_value:
            try:
                # Проверяем, наш ли это еще замок (мог смениться другим клиентом по TTL)
                val = await RedisService.call("get", active_lock_key)
                if val == active_lock_value:
                    await RedisService.call("delete", active_lock_key, for_write=True)
                    logger.info("Auto-unlocked slot on disconnect", key=active_lock_key)
            except Exception as e:
                logger.error("Auto-unlock failed", error=str(e))