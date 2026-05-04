# app/websocket/booking_ws.py
import asyncio
import json
from datetime import date, datetime
from typing import Dict, List
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.db.models.restaurant import Restaurant
from app.services.redis_service import RedisService
from app.services.slot_broadcast import broadcast_slots_update
import structlog
from sqlalchemy import select
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import redis.asyncio as redis

logger = structlog.get_logger(__name__)

# Активные CRM-соединения: {restaurant_slug: [WebSocket]}
crm_connections: Dict[str, List[WebSocket]] = {}


class BookingWebsocketManager:
    @staticmethod
    async def connect(websocket: WebSocket, restaurant_slug: str):
        crm_connections.setdefault(restaurant_slug, []).append(websocket)
        logger.info("CRM WebSocket connected", restaurant_slug=restaurant_slug, total=len(crm_connections[restaurant_slug]))

    @staticmethod
    def disconnect(websocket: WebSocket, restaurant_slug: str):
        if restaurant_slug in crm_connections:
            if websocket in crm_connections[restaurant_slug]:
                crm_connections[restaurant_slug].remove(websocket)
            if not crm_connections[restaurant_slug]:
                del crm_connections[restaurant_slug]
        logger.info("CRM WebSocket disconnected", restaurant_slug=restaurant_slug)

    @staticmethod
    async def notify_booking_confirmed(restaurant_slug: str, booking_time: str, booking_id: int, booking_date: date):
        """
        Уведомление CRM о подтверждении брони.
        Теперь принимает booking_date — обязательно!
        """
        message = {
            "type": "booking_confirmed",
            "time": booking_time,
            "booking_id": booking_id,
            "booking_date": booking_date.isoformat() if booking_date else None,
            "timestamp": datetime.utcnow().isoformat()
        }
        await BookingWebsocketManager.broadcast_to_restaurant(restaurant_slug, message)

        # Публикация в публичный канал slot_updates
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Restaurant.id).where(Restaurant.slug == restaurant_slug))
                restaurant_id = result.scalar_one()
                if restaurant_id:
                    await broadcast_slots_update(restaurant_id, booking_date)
        except Exception as e:
            logger.error("Failed to publish slot update after booking confirm", error=str(e), restaurant_slug=restaurant_slug)

    @staticmethod
    async def broadcast_to_restaurant(restaurant_slug: str, message: dict):
        if restaurant_slug not in crm_connections:
            return

        message_str = json.dumps(message, ensure_ascii=False, default=str)
        disconnected = []

        for ws in list(crm_connections[restaurant_slug]):
            try:
                await ws.send_text(message_str)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            BookingWebsocketManager.disconnect(ws, restaurant_slug)


# Фоновая задача: пересылка booking_updates → CRM WebSocket
# With automatic reconnection on Redis disconnects
async def redis_booking_listener():
    if not RedisService.redis:
        logger.error("Redis not initialized — booking listener stopped")
        return

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(redis.RedisError),
    )
    async def connect_and_subscribe():
        redis_conn = await RedisService.ensure_connection()
        if not redis_conn:
            raise Exception("Redis unavailable for booking pubsub")
        pubsub = redis_conn.pubsub()
        await pubsub.subscribe("booking_updates")
        return pubsub

    while True:
        pubsub = None
        try:
            pubsub = await connect_and_subscribe()
            logger.info("Subscribed to booking_updates channel")

            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    slug = data.get("restaurant_slug")
                    if not slug:
                        continue

                    # Пересылаем ВСЁ: created, update, deleted
                    if slug in crm_connections:
                        await BookingWebsocketManager.broadcast_to_restaurant(slug, data)

                except json.JSONDecodeError:
                    logger.warning("Invalid JSON in booking_updates", data=message.get("data"))
                except Exception as e:
                    logger.error("Error processing booking_updates message", error=str(e), exc_info=True)

        except Exception as e:
            logger.error("Redis booking listener disconnected, reconnecting in 5s...", error=str(e), exc_info=True)
            await asyncio.sleep(5)
        finally:
            try:
                if pubsub:
                    await pubsub.unsubscribe("booking_updates")
                    await pubsub.close()
            except:
                pass


# Обработчик подключения CRM
async def handle_crm_booking_websocket(websocket: WebSocket, restaurant_slug: str, user_id: int):
    try:
        async with AsyncSessionLocal() as db:
            restaurant = (await db.execute(
                select(Restaurant).where(Restaurant.slug == restaurant_slug)
            )).scalar_one_or_none()
            if not restaurant:
                await websocket.close(code=4004, reason="Restaurant not found")
                return

        await BookingWebsocketManager.connect(websocket, restaurant_slug)
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "restaurant_slug": restaurant_slug,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }, ensure_ascii=False))

        logger.info("CRM WebSocket established", restaurant_slug=restaurant_slug, user_id=user_id)

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data.strip() in {"ping", "pong"}:
                    await websocket.send_text("pong" if data.strip() == "ping" else "ping")
            except asyncio.TimeoutError:
                try:
                    await websocket.send_text('{"type":"ping"}')
                except:
                    break
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning("Error in CRM WS loop", error=str(e))
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Unexpected error in CRM WS", error=str(e), exc_info=True)
    finally:
        BookingWebsocketManager.disconnect(websocket, restaurant_slug)
        logger.info("CRM WebSocket closed", restaurant_slug=restaurant_slug)