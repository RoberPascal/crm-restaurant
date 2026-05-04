# app/services/slot_broadcast.py
from datetime import date
from app.services.redis_service import RedisService
import json
import structlog

logger = structlog.get_logger(__name__)


async def broadcast_slots_update(restaurant_id: int, target_date: date) -> None:
    """
    Уведомляет всех подключённых клиентов (админка + webapp),
    что слоты на указанную дату нужно обновить.
    Вызывается после создания, отмены, изменения брони.
    """
    date_str = target_date.isoformat()
    channel = f"slot_updates:{restaurant_id}:{date_str}"
    payload = json.dumps({"action": "slots_refresh"})

    try:
        published = await RedisService.call("publish", channel, payload, for_write=True)
        if published is None:
            logger.warning("Redis недоступен — broadcast пропущен", restaurant_id=restaurant_id, date=target_date)
            return
        logger.info(
            "Broadcast sent",
            channel=channel,
            subscribers=published,
            restaurant_id=restaurant_id,
            date=date_str,
        )
    except Exception as e:
        logger.error(
            "Failed to broadcast slot update",
            error=str(e),
            channel=channel,
            restaurant_id=restaurant_id,
            date=date_str,
            exc_info=True,
        )