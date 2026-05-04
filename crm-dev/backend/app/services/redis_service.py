# app/services/redis_service.py
import redis.asyncio as aioredis
from redis.asyncio import RedisError
from app.core.config import settings
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from redis.exceptions import ReadOnlyError

logger = structlog.get_logger(__name__)

class RedisService:
    redis = None
    redis_master = None  # Отдельное соединение для записи

    @classmethod
    async def ensure_connection(cls, for_write: bool = False):
        """Ensure Redis connection, with option for master connection for writes"""
        if for_write:
            if cls.redis_master is None:
                await cls.init_redis_master()
            return cls.redis_master
        else:
            if cls.redis is None:
                await cls.init_redis()
            return cls.redis

    @classmethod
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(RedisError),
        before_sleep=lambda rs: logger.info(f"Redis reconnect #{rs.attempt_number}")
    )
    async def init_redis(cls):
        """Initialize read-only Redis connection"""
        if cls.redis:
            return True
        try:
            logger.info("Connecting to Redis (read)", url=settings.REDIS_URL)
            cls.redis = aioredis.from_url(
                settings.REDIS_URL.get_secret_value(),
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS or 10
            )
            await cls.redis.ping()
            logger.info("Redis (read) connected")
            return True
        except RedisError as e:
            logger.error("Redis (read) connection failed (RedisError)", error=str(e))
            cls.redis = None
            raise  # Let tenacity @retry handle RedisError
        except Exception as e:
            logger.error("Redis (read) connection failed", error=str(e))
            cls.redis = None
            return False

    @classmethod
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(RedisError),
        before_sleep=lambda rs: logger.info(f"Redis master reconnect #{rs.attempt_number}")
    )
    async def init_redis_master(cls):
        """Initialize Redis master connection for writes"""
        if cls.redis_master:
            return True
            
        # Используем мастер URL если указан, иначе обычный URL
        redis_url = settings.REDIS_MASTER_URL if settings.REDIS_MASTER_URL else settings.REDIS_URL
        
        try:
            logger.info("Connecting to Redis (master)")
            cls.redis_master = aioredis.from_url(
                redis_url.get_secret_value(),
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS or 10
            )
            await cls.redis_master.ping()
            logger.info("Redis (master) connected")
            return True
        except RedisError as e:
            logger.error("Redis (master) connection failed (RedisError)", error=str(e))
            cls.redis_master = None
            raise  # Let tenacity @retry handle RedisError
        except Exception as e:
            logger.error("Redis (master) connection failed", error=str(e))
            cls.redis_master = None
            return False

    @classmethod
    async def close_redis(cls):
        """Close all Redis connections"""
        for conn_name in ['redis', 'redis_master']:
            conn = getattr(cls, conn_name)
            if conn:
                try:
                    await conn.close()
                    logger.info(f"Redis {conn_name} closed")
                except Exception as e:
                    logger.error(f"Redis {conn_name} close error", error=str(e))
                finally:
                    setattr(cls, conn_name, None)

    @classmethod
    async def call(cls, method_name: str, *args, for_write: bool | None = None, **kwargs):
        """Execute Redis command with proper connection selection"""
        
        # Определяем тип операции (чтение/запись)
        if for_write is None:
            # Автоопределение по имени метода
            write_commands = {'set', 'setex', 'setnx', 'delete', 'expire', 'incr', 'decr', 'hset', 'hdel', 'publish'}
            for_write = method_name.lower() in write_commands

        redis = await cls.ensure_connection(for_write=for_write)
        if not redis:
            logger.error("Redis client unavailable", method=method_name, for_write=for_write)
            return None

        method = getattr(redis, method_name, None)
        if not method:
            logger.error("Redis method missing", method=method_name)
            return None

        try:
            return await method(*args, **kwargs)
        except ReadOnlyError as exc:
            logger.warning("Redis read-only error detected", method=method_name, for_write=for_write)
            
            # Если это была операция записи на реплике, пробуем на мастере
            if not for_write:
                raise
                
            await cls.close_redis()
            await cls.init_redis_master()
            redis = cls.redis_master
            if not redis:
                logger.error("Redis master reconnection failed", method=method_name)
                return None
                
            method = getattr(redis, method_name, None)
            if not method:
                logger.error("Redis method missing after reconnection", method=method_name)
                return None
                
            return await method(*args, **kwargs)
        except Exception as exc:
            logger.error("Redis call failed", method=method_name, for_write=for_write, error=str(exc))
            raise