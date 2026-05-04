import asyncio
import sys
import os

# Добавляем корень проекта в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.services.redis_service import RedisService


async def clear_redis_cache():
    try:
        # Инициализация соединения с Redis
        connected = await RedisService.init_redis()

        if not connected or not RedisService.redis:
            print("❌ Redis is not available or connection failed")
            return

        # Очищаем весь кэш
        await RedisService.redis.flushall()
        print("✅ Redis cache cleared successfully!")

        # Закрываем соединение
        await RedisService.close_redis()

    except Exception as e:
        print(f"❌ Error clearing cache: {e}")


if __name__ == "__main__":
    asyncio.run(clear_redis_cache())
