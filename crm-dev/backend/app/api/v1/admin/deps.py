# app/api/v1/admin/deps.py
from fastapi import Depends, HTTPException, status, Cookie, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_async_db
from app.db.models.user import User, RoleEnum
from app.core.security import decode_access_token, constant_time_compare
from app.core.config import settings
import structlog
import hmac

logger = structlog.get_logger(__name__)

async def NoRateLimit():
    """Заглушка для отключения лимитов"""
    return None

async def get_current_user_from_cookie(
    request: Request,
    access_token: str = Cookie(None, alias="access_token"),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """
    Зависимость для получения текущего пользователя из cookie.
    Использует уже проверенного пользователя из middleware, если доступен.
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # Если пользователь уже проверен в middleware, используем его
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user
    
    # Fallback: проверяем токен напрямую (для случаев когда middleware не сработал)
    if not access_token:
        logger.warning("No access_token in cookie", client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    # Извлекаем токен (не санитизируем, так как JWT содержит специальные символы)
    token = access_token.strip()
    if token.startswith("Bearer "):
        token = token[7:].strip()
    
    # Базовая валидация токена
    if not token or len(token) < 10:
        logger.warning("Invalid token format", client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format"
        )

    try:
        # Декодирование токена
        payload = decode_access_token(token)
        if not payload:
            logger.warning("Invalid token payload", client_ip=client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        # Проверка user_id
        user_id = payload.sub
        if not user_id or not str(user_id).isdigit():
            logger.warning("Invalid user ID in token", user_id=user_id, client_ip=client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

        # Поиск пользователя
        result = await db.execute(
            select(User).where(
                User.id == int(user_id),
                User.is_active.is_(True)
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning("User not found or inactive", user_id=user_id, client_ip=client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )

        logger.debug("User authenticated", user_id=user.id, role=user.role, client_ip=client_ip)
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Authentication error", 
            error=str(e), 
            client_ip=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

async def verify_csrf_token(request: Request):
    """
    Зависимость для проверки CSRF токена.
    Пропускает безопасные методы.
    УСТАРЕВШАЯ ФУНКЦИЯ - используйте validate_csrf_dependency
    """
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return

    client_ip = request.client.host if request.client else "unknown"
    
    token_header = request.headers.get("X-CSRF-Token")
    token_cookie = request.cookies.get("csrf_token")

    if not token_header or not token_cookie:
        logger.warning(
            "CSRF tokens missing", 
            header=bool(token_header), 
            cookie=bool(token_cookie),
            client_ip=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token required"
        )

    # Постоянное время сравнения
    if not constant_time_compare(token_header, token_cookie):
        logger.warning("CSRF token mismatch", client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token invalid"
        )

# УСТАРЕЛО - использовать validate_csrf_dependency напрямую из security.py

async def require_admin_role(user: User = Depends(get_current_user_from_cookie)) -> User:
    """Зависимость для проверки роли администратора"""
    if user.role != RoleEnum.admin:
        logger.warning("Admin role required", user_role=user.role, user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required"
        )
    return user

async def require_operator_role(user: User = Depends(get_current_user_from_cookie)) -> User:
    """Зависимость для проверки роли оператора или администратора"""
    if user.role not in [RoleEnum.admin, RoleEnum.operator]:
        logger.warning("Operator role required", user_role=user.role, user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator access required"
        )
    return user

async def require_staff_role(user: User = Depends(get_current_user_from_cookie)) -> User:
    """Все staff — admin, operator, waiter. Для доступа к бронированиям."""
    if user.role not in [RoleEnum.admin, RoleEnum.operator, RoleEnum.waiter]:
        logger.warning("Staff role required", user_role=user.role, user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff access required"
        )
    return user

async def validate_restaurant_access(restaurant_id: int, user: User) -> bool:
    """Проверка доступа пользователя к ресторану."""
    # Админы имеют доступ ко всем ресторанам
    if user.role == RoleEnum.admin:
        return True
    
    # Обычные пользователи - только к своим ресторанам
    user_restaurant_ids = [r.id for r in user.restaurants]
    return restaurant_id in user_restaurant_ids