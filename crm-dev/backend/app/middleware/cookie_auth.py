# app/middleware/cookie_auth.py
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from app.core.security import decode_access_token, sanitize_input
from app.core.config import settings
from app.db.session import get_async_db
from app.db.models.user import User
from sqlalchemy import select
import structlog
from typing import Set, Pattern, Callable
import re

logger = structlog.get_logger(__name__)

class CookieAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._public_paths = self._compile_public_paths()
        # ОПТИМИЗАЦИЯ: In-memory кэш пользователей (TTL = 60с, макс 100 записей)
        self._user_cache: dict = {}  # {user_id: (user, timestamp)}
        self._cache_ttl = 60  # секунд
        self._cache_max_size = 100

    def _compile_public_paths(self) -> Set[Pattern]:
        public_patterns = [
            r"^/api/v1/public/.*",
            r"^/api/v1/admin/auth/.*",  # Все auth endpoints доступны (включая OPTIONS)
            r"^/ws/.*",
            r"^/health$",
            r"^/docs$",
            r"^/redoc$", 
            r"^/openapi\.json$",
            r"^/favicon\.ico$",
            r"^/favicon\.png$",
            r"^/_next/.*",
            r"^/login$",
            r"^/$",
        ]
        return {re.compile(pattern) for pattern in public_patterns}

    def _is_public_path(self, path: str) -> bool:
        return any(pattern.match(path) for pattern in self._public_paths)

    async def _get_user_from_token(self, token: str, db) -> User:
        try:
            payload = decode_access_token(token)
            if not payload:
                return None
                
            if payload.scope != "access":
                logger.warning("Invalid token scope", scope=payload.scope)
                return None
                
            user_id = payload.sub
            if not user_id or not user_id.isdigit():
                logger.warning("Invalid user ID in token", user_id=user_id)
                return None

            # ОПТИМИЗАЦИЯ: Проверяем кэш перед SQL запросом
            import time as time_module
            now = time_module.time()
            cache_entry = self._user_cache.get(int(user_id))
            if cache_entry:
                cached_user, cached_at = cache_entry
                if now - cached_at < self._cache_ttl:
                    logger.debug("User from cache", user_id=user_id)
                    return cached_user
                else:
                    del self._user_cache[int(user_id)]

            result = await db.execute(
                select(User).where(
                    User.id == int(user_id),
                    User.is_active.is_(True)
                )
            )
            user = result.scalar_one_or_none()
            
            if user:
                # Сохраняем в кэш
                if len(self._user_cache) >= self._cache_max_size:
                    # Очищаем устаревшие записи
                    self._user_cache = {
                        k: v for k, v in self._user_cache.items() 
                        if now - v[1] < self._cache_ttl
                    }
                self._user_cache[int(user_id)] = (user, now)
                logger.debug("User authenticated", user_id=user_id, role=user.role)
                return user
            return None
            
        except Exception as e:
            logger.debug("Token validation failed", error=str(e))
            return None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        safe_path = sanitize_input(path)

        # Публичные пути — сразу пропускаем
        if self._is_public_path(path):
            logger.debug("Public path accessed", path=safe_path, ip=client_ip)
            return await call_next(request)

        # OPTIONS для CORS
        if request.method == "OPTIONS":
            return await call_next(request)

        # Требуем токен
        request.state.user = None
        request.state.is_authenticated = False

        token_cookie = request.cookies.get("access_token")
        if not token_cookie:
            return await self._handle_unauthorized(request, call_next, safe_path, "Missing authentication token")

        token = token_cookie.strip()
        if token.startswith("Bearer "):
            token = token[7:].strip()
            
        if not token or len(token) < 10:
            return await self._handle_unauthorized(request, call_next, safe_path, "Invalid token format")

        try:
            async for db in get_async_db():
                user = await self._get_user_from_token(token, db)
                if not user:
                    return await self._handle_unauthorized(request, call_next, safe_path, "Invalid or expired token")

                request.state.user = user
                request.state.is_authenticated = True
                request.state.user_id = user.id

                response = await call_next(request)
                if hasattr(response, "headers"):
                    response.headers["X-Authenticated-User"] = str(user.id)
                return response

        except Exception as e:
            logger.error("Auth middleware error", error=str(e), path=safe_path, ip=client_ip)
            if settings.is_production:
                return JSONResponse(
                    status_code=500, 
                    content={"detail": "Authentication service error"}
                )
            else:
                return JSONResponse(
                    status_code=500, 
                    content={"detail": f"Authentication error: {str(e)}"}
                )

    async def _handle_unauthorized(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        path: str,
        detail: str
    ):
        client_ip = request.client.host if request.client else "unknown"
        logger.warning("Unauthorized access attempt", path=path, detail=detail, ip=client_ip)
        
        # Если путь публичный — пропускаем (на всякий случай)
        if self._is_public_path(path):
            return await call_next(request)
            
        if path.startswith("/api/v1/admin/"):
            if settings.is_production:
                detail = "Authentication required"
                
            return JSONResponse(
                status_code=401,
                content={"detail": detail, "code": "UNAUTHORIZED"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Для всех остальных — пытаемся обработать как публичный
        return await call_next(request)