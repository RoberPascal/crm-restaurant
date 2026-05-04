# app/middleware/security.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from app.core.config import settings
import structlog
import time

logger = structlog.get_logger(__name__)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware для установки security headers.
    Защищает от XSS, clickjacking, MIME sniffing и других атак.
    """
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Security headers
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }
        
        # Content Security Policy
        if settings.ENABLE_CSP and not settings.is_development:
            csp_policy = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "connect-src 'self' ws: wss:; "
                "font-src 'self'; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "frame-ancestors 'none'; "
                "block-all-mixed-content; "
                "upgrade-insecure-requests;"
            )
            headers["Content-Security-Policy"] = csp_policy
        
        # HSTS для production
        if settings.ENABLE_HSTS and settings.is_production:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Добавляем headers к ответу
        for header, value in headers.items():
            response.headers[header] = value
            
        return response

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-based rate limiting middleware.
    Корректно работает с несколькими Uvicorn workers (общий счётчик через Redis).
    Если Redis недоступен — пропускает запросы (fail-open).
    """
    
    async def dispatch(self, request: Request, call_next):
        if settings.RATE_LIMIT_PER_MINUTE <= 0:
            return await call_next(request)
            
        client_ip = request.client.host if request.client else "unknown"
        
        # Пробуем Redis-based rate limiting
        try:
            from app.services.redis_service import RedisService
            redis_client = RedisService.redis
            
            if redis_client:
                current_minute = int(time.time() / 60)
                rate_key = f"ratelimit:{client_ip}:{current_minute}"
                
                # INCR + EXPIRE атомарно через pipeline
                pipe = redis_client.pipeline()
                pipe.incr(rate_key)
                pipe.expire(rate_key, 120)  # TTL 2 минуты
                results = await pipe.execute()
                
                request_count = results[0]
                
                if request_count > settings.RATE_LIMIT_PER_MINUTE:
                    logger.warning("Rate limit exceeded", client_ip=client_ip, count=request_count)
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests", "retry_after": 60}
                    )
            # Если Redis не подключен — пропускаем (fail-open)
        except Exception as e:
            # При ошибке Redis — пропускаем запрос, не блокируем пользователя
            logger.debug("Rate limit check skipped (Redis unavailable)", error=str(e))
        
        return await call_next(request)

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования запросов и ответов.
    ОПТИМИЗАЦИЯ: Убрано двойное логирование (было: started + completed, стало: только completed).
    """
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            
            # Логируем только завершённые запросы (>200ms или ошибки)
            if duration > 0.2 or response.status_code >= 400:
                logger.info(
                    "Request completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration=f"{duration:.3f}s",
                    client_ip=client_ip
                )
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration=f"{duration:.3f}s",
                client_ip=client_ip
            )
            raise