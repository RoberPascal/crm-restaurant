# app/api/v1/admin/auth.py
from fastapi import APIRouter, Depends, HTTPException, Header, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import timedelta
from app.db.session import get_async_db
from app.db.models.user import User, RoleEnum
from app.schemas.auth import Token, UserResponse
from app.core.security import (
    create_access_token, 
    create_csrf_token, 
    verify_password,
    hash_password,
    validate_csrf_dependency,
    sanitize_input,
    constant_time_compare,
    check_rate_limit,
    get_security_headers,
)
from app.core.config import settings
from .deps import get_current_user_from_cookie
import structlog
import time
import asyncio
import hmac
from typing import Dict, Any

logger = structlog.get_logger(__name__)
router = APIRouter()

# Константы для rate limiting
LOGIN_RATE_LIMIT = 5  # попыток в минуту
CSRF_RATE_LIMIT = 60  # запросов в минуту

@router.options("/csrf", include_in_schema=False)
async def options_csrf(request: Request, response: Response):
    """OPTIONS endpoint для CORS preflight запросов"""
    client_ip = request.client.host if request.client else "unknown"
    origin = request.headers.get("origin")
    
    logger.info("OPTIONS /csrf called", client_ip=client_ip, origin=origin)
    
    # Устанавливаем CORS headers напрямую в response
    if origin and origin in settings.safe_cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-WebApp-Source, Authorization, User-Agent, X-CSRF-Token, Cookie, Accept, Origin"
    response.headers["Access-Control-Max-Age"] = "86400"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    
    # Security headers
    for k, v in get_security_headers().items():
        response.headers[k] = v
    
    response.status_code = 200
    logger.info("OPTIONS /csrf response prepared", status=200)
    
    return {"status": "ok"}

@router.get("/csrf", dependencies=[])
async def get_csrf_token(
    request: Request,
    response: Response,
):
    client_ip = request.client.host if request.client else "unknown"

    logger.info("CSRF endpoint HIT", client_ip=client_ip, origin=request.headers.get("origin"))

    # Rate limit
    if not check_rate_limit(f"csrf:{client_ip}", CSRF_RATE_LIMIT, 60):
        raise HTTPException(status_code=429, detail="Too many requests")

    # Генерируем токен
    csrf_token = create_csrf_token()

    # Ставим куку
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=not settings.is_development,
        samesite=settings.SAME_SITE_COOKIE.lower(),
        path="/",
        max_age=settings.CSRF_TOKEN_EXPIRE_MINUTES * 60,
        domain=settings.COOKIE_DOMAIN if settings.COOKIE_DOMAIN else None,
    )

    # НИКАКИХ РУЧНЫХ CORS-ЗАГОЛОВКОВ — пусть CORSMiddleware делает свою работу
    # Только security headers
    for k, v in get_security_headers().items():
        response.headers[k] = v

    logger.info("CSRF token issued", client_ip=client_ip, token_preview=csrf_token[:8])

    return {"csrf_token": csrf_token}

@router.options("/login", include_in_schema=False)
async def options_login(request: Request, response: Response):
    """OPTIONS endpoint для CORS preflight на login"""
    client_ip = request.client.host if request.client else "unknown"
    origin = request.headers.get("origin")
    
    logger.info("OPTIONS /login called", client_ip=client_ip, origin=origin)
    
    # Устанавливаем CORS headers напрямую в response
    if origin and origin in settings.safe_cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-WebApp-Source, Authorization, User-Agent, X-CSRF-Token, Cookie, Accept, Origin"
    response.headers["Access-Control-Max-Age"] = "86400"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    
    # Security headers
    for k, v in get_security_headers().items():
        response.headers[k] = v
    
    response.status_code = 200
    logger.info("OPTIONS /login response prepared", status=200)
    
    return {"status": "ok"}

@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(validate_csrf_dependency)]
)
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_async_db),
):
    """Аутентификация пользователя с защитой от brute-force атак"""
    client_ip = request.client.host if request.client else "unknown"
    
    # Rate limiting для логина
    rate_limit_key = f"login:{client_ip}:{form_data.username}"
    if not check_rate_limit(rate_limit_key, LOGIN_RATE_LIMIT, 60):
        logger.warning("Login rate limit exceeded", 
                      username=form_data.username, 
                      client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts"
        )
    
    # Санитизация ввода
    sanitized_username = sanitize_input(form_data.username)
    
    logger.info("Login attempt", 
                username=sanitized_username, 
                client_ip=client_ip)

    start_time = time.perf_counter()
    
    try:
        # Поиск пользователя
        result = await db.execute(select(User).where(User.username == sanitized_username))
        user = result.scalars().first()
        
        # Проверка пароля с постоянным временем выполнения (в thread pool чтобы не блокировать loop)
        password_valid = False
        user_active = False
        
        if user:
            password_valid = await asyncio.to_thread(user.verify_password, form_data.password)
            user_active = user.is_active
        
        # Выравнивание времени выполнения для защиты от timing attacks (non-blocking)
        elapsed = time.perf_counter() - start_time
        await asyncio.sleep(max(0.5 - elapsed, 0))
        
        if not user or not password_valid or not user_active:
            logger.warning(
                "Login failed",
                username=sanitized_username,
                client_ip=client_ip,
                user_exists=bool(user),
                user_active=user_active,
                password_valid=password_valid
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Создание access token
        access_token = create_access_token(
            data={"sub": str(user.id), "role": user.role},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            scope="access"
        )
        
        # Создание CSRF токена
        csrf_token = create_csrf_token(user.id)

        # Настройка cookies
        secure = settings.SECURE_COOKIES
        cookie_kwargs = {
            "httponly": True,
            "secure": secure,
            "samesite": settings.SAME_SITE_COOKIE,
            "max_age": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "path": "/",
        }

        if settings.COOKIE_DOMAIN:
            cookie_kwargs["domain"] = settings.COOKIE_DOMAIN

        # Устанавливаем access_token cookie
        response.set_cookie(
            key="access_token",
            value=access_token,
            **cookie_kwargs
        )
        
        # Устанавливаем CSRF token cookie
        csrf_cookie_kwargs = cookie_kwargs.copy()
        csrf_cookie_kwargs["httponly"] = False  # Доступен из JavaScript
        
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            **csrf_cookie_kwargs
        )

        # Добавляем security headers
        security_headers = get_security_headers()
        for key, value in security_headers.items():
            response.headers[key] = value

        logger.info(
            "Login successful",
            user_id=user.id,
            username=user.username,
            role=user.role,
            client_ip=client_ip
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "csrf_token": csrf_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "is_active": user.is_active
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Login error",
            error=str(e),
            username=sanitized_username,
            client_ip=client_ip,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.options("/me", include_in_schema=False)
async def options_me(request: Request):
    """OPTIONS endpoint для CORS preflight на /me"""
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and origin in settings.safe_cors_origins else None
    
    headers = {
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-WebApp-Source, Authorization, User-Agent, X-CSRF-Token, Cookie",
        "Access-Control-Max-Age": "86400",
        "Access-Control-Allow-Credentials": "true",
        **get_security_headers()
    }
    
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
        headers["Vary"] = "Origin"
    
    return Response(status_code=200, headers=headers)

@router.get("/me", response_model=UserResponse)
async def read_users_me(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Получение информации о текущем пользователе"""
    client_ip = request.client.host if request.client else "unknown"
    
    logger.debug("User info requested", 
                user_id=current_user.id, 
                username=current_user.username,
                client_ip=client_ip)
    
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at
    )

@router.options("/logout", include_in_schema=False)
async def options_logout(request: Request):
    """OPTIONS endpoint для CORS preflight на /logout"""
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and origin in settings.safe_cors_origins else None
    
    headers = {
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-WebApp-Source, Authorization, User-Agent, X-CSRF-Token, Cookie",
        "Access-Control-Max-Age": "86400",
        "Access-Control-Allow-Credentials": "true",
        **get_security_headers()
    }
    
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
        headers["Vary"] = "Origin"
    
    return Response(status_code=200, headers=headers)

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Выход из системы с очисткой cookies"""
    client_ip = request.client.host if request.client else "unknown"
    
    delete_kwargs = {
        "path": "/",
    }
    if settings.COOKIE_DOMAIN:
        delete_kwargs["domain"] = settings.COOKIE_DOMAIN

    # Удаляем cookies
    response.delete_cookie("access_token", **delete_kwargs)
    response.delete_cookie("csrf_token", **delete_kwargs)
    
    # Добавляем security headers
    security_headers = get_security_headers()
    for key, value in security_headers.items():
        response.headers[key] = value
    
    logger.info("User logged out", 
                user_id=current_user.id, 
                username=current_user.username,
                client_ip=client_ip)
    
    return {"detail": "Logged out successfully"}

@router.options("/ws-token", include_in_schema=False)
async def options_ws_token(request: Request):
    """OPTIONS endpoint для CORS preflight на /ws-token"""
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and origin in settings.safe_cors_origins else None
    
    headers = {
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-WebApp-Source, Authorization, User-Agent, X-CSRF-Token, Cookie",
        "Access-Control-Max-Age": "86400",
        "Access-Control-Allow-Credentials": "true",
        **get_security_headers()
    }
    
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
        headers["Vary"] = "Origin"
    
    return Response(status_code=200, headers=headers)

@router.get("/ws-token")
async def get_websocket_token(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Генерация токена для WebSocket соединений"""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        ws_token = create_access_token(
            data={"sub": str(current_user.id), "role": current_user.role},
            expires_delta=timedelta(minutes=settings.WS_TOKEN_EXPIRE_MINUTES),
            scope="ws"
        )
        
        logger.debug("WebSocket token generated", 
                    user_id=current_user.id, 
                    username=current_user.username,
                    client_ip=client_ip)
        
        return {
            "access_token": ws_token,
            "token_type": "bearer",
            "expires_in": settings.WS_TOKEN_EXPIRE_MINUTES * 60
        }
    except Exception as e:
        logger.error(
            "WebSocket token generation failed", 
            error=str(e), 
            user_id=current_user.id,
            username=current_user.username,
            client_ip=client_ip,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate WebSocket token"
        )

@router.options("/refresh", include_in_schema=False)
async def options_refresh(request: Request):
    """OPTIONS endpoint для CORS preflight на /refresh"""
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and origin in settings.safe_cors_origins else None
    
    headers = {
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-WebApp-Source, Authorization, User-Agent, X-CSRF-Token, Cookie",
        "Access-Control-Max-Age": "86400",
        "Access-Control-Allow-Credentials": "true",
        **get_security_headers()
    }
    
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
        headers["Vary"] = "Origin"
    
    return Response(status_code=200, headers=headers)

@router.post("/refresh", dependencies=[Depends(validate_csrf_dependency)])
async def refresh_token(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Обновление access token с проверкой CSRF"""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        # Создаем новый токен
        new_access_token = create_access_token(
            data={"sub": str(current_user.id), "role": current_user.role},
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            scope="access"
        )
        new_csrf_token = create_csrf_token(current_user.id)

        # Настройка cookies
        secure = settings.SECURE_COOKIES
        cookie_kwargs = {
            "httponly": True,
            "secure": secure,
            "samesite": settings.SAME_SITE_COOKIE,
            "max_age": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "path": "/",
        }
        if settings.COOKIE_DOMAIN:
            cookie_kwargs["domain"] = settings.COOKIE_DOMAIN

        # Обновляем cookies
        response.set_cookie(
            key="access_token",
            value=new_access_token,
            **cookie_kwargs
        )
        
        csrf_cookie_kwargs = cookie_kwargs.copy()
        csrf_cookie_kwargs["httponly"] = False
        
        response.set_cookie(
            key="csrf_token",
            value=new_csrf_token,
            **csrf_cookie_kwargs
        )

        # Добавляем security headers
        security_headers = get_security_headers()
        for key, value in security_headers.items():
            response.headers[key] = value

        logger.debug("Token refreshed", 
                    user_id=current_user.id, 
                    username=current_user.username,
                    client_ip=client_ip)
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "csrf_token": new_csrf_token
        }
        
    except Exception as e:
        logger.error(
            "Token refresh failed",
            error=str(e),
            user_id=current_user.id,
            username=current_user.username,
            client_ip=client_ip,
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not refresh token"
        )

@router.options("/renew-csrf", include_in_schema=False)
async def options_renew_csrf(request: Request):
    """OPTIONS endpoint для CORS preflight на /renew-csrf"""
    origin = request.headers.get("origin")
    allowed_origin = origin if origin and origin in settings.safe_cors_origins else None
    
    headers = {
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-WebApp-Source, Authorization, User-Agent, X-CSRF-Token, Cookie",
        "Access-Control-Max-Age": "86400",
        "Access-Control-Allow-Credentials": "true",
        **get_security_headers()
    }
    
    if allowed_origin:
        headers["Access-Control-Allow-Origin"] = allowed_origin
        headers["Vary"] = "Origin"
    
    return Response(status_code=200, headers=headers)

@router.get("/renew-csrf")
async def renew_csrf_token(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Обновление CSRF токена для аутентифицированного пользователя"""
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        csrf_token = create_csrf_token(current_user.id)
        secure = settings.SECURE_COOKIES
        
        cookie_kwargs = {
            "httponly": False,
            "secure": secure,
            "samesite": settings.SAME_SITE_COOKIE,
            "max_age": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "path": "/",
        }
        if settings.COOKIE_DOMAIN:
            cookie_kwargs["domain"] = settings.COOKIE_DOMAIN
        
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            **cookie_kwargs
        )
        
        # Добавляем security headers
        security_headers = get_security_headers()
        for key, value in security_headers.items():
            response.headers[key] = value
        
        logger.debug("CSRF token renewed", 
                    user_id=current_user.id, 
                    username=current_user.username,
                    client_ip=client_ip)
        
        return {"csrf_token": csrf_token}
        
    except Exception as e:
        logger.error("CSRF token renewal failed", 
                    error=str(e),
                    user_id=current_user.id,
                    client_ip=client_ip,
                    exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not renew CSRF token"
        )