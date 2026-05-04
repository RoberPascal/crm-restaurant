# app/core/rate_limiter.py
"""
Простой rate limiter на базе Redis для публичных эндпоинтов.
Использует sliding window counter через INCR + EXPIRE.
"""
from fastapi import Request, HTTPException, status
from app.services.redis_service import RedisService
import structlog

logger = structlog.get_logger(__name__)


async def check_rate_limit(
    request: Request,
    max_requests: int = 30,
    window_seconds: int = 60,
    prefix: str = "rl"
):
    """
    Проверяет rate limit по IP.
    max_requests — макс. запросов за window_seconds.
    """
    # Получаем IP клиента
    client_ip = "unknown"
    if request.client:
        client_ip = request.client.host
    
    # Проверяем forwarded headers (за reverse proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    
    key = f"{prefix}:{client_ip}"
    
    try:
        # Атомарный INCR + условный EXPIRE
        current = await RedisService.call("incr", key, for_write=True)
        if current is None:
            # Redis недоступен — пропускаем (fail open)
            return
        
        if current == 1:
            # Первый запрос — ставим TTL
            await RedisService.call("expire", key, window_seconds, for_write=True)
        
        if current > max_requests:
            logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                current=current,
                limit=max_requests,
                window=window_seconds
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов. Попробуйте позже."
            )
    except HTTPException:
        raise
    except Exception as e:
        # Redis ошибка — fail open, не блокируем пользователя
        logger.warning("Rate limiter error (fail open)", error=str(e))


async def public_rate_limit(request: Request):
    """Rate limit для публичных эндпоинтов: 30 запросов в минуту"""
    await check_rate_limit(request, max_requests=30, window_seconds=60, prefix="rl:pub")


async def public_write_rate_limit(request: Request):
    """Rate limit для POST/PATCH/DELETE: 10 запросов в минуту"""
    await check_rate_limit(request, max_requests=10, window_seconds=60, prefix="rl:pub:write")
