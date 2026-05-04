# app/core/security.py
from datetime import datetime, timedelta
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import BaseModel
import secrets
import hmac
import hashlib
import structlog
from typing import Optional, List, Dict, Any
from fastapi import Request, HTTPException, status, Header
import re
import time
import asyncio
import bcrypt
import json
from urllib.parse import parse_qsl, unquote

logger = structlog.get_logger(__name__)

class TokenPayload(BaseModel):
    sub: str  # User ID
    role: Optional[str] = None
    scope: Optional[str] = None
    exp: float
    iat: Optional[float] = None
    nbf: Optional[float] = None
    iss: Optional[str] = None
    aud: Optional[str] = None

class SecurityError(Exception):
    """Базовое исключение для ошибок безопасности"""
    pass

class InvalidTokenError(SecurityError):
    pass

class CSRFError(SecurityError):
    pass

class RateLimitError(SecurityError):
    pass

# Импортируем settings после определения классов
from app.core.config import settings

# ========== WEBAPP SOURCE VALIDATION ==========

class WebAppSourceValidation:
    """Безопасная валидация источника запроса с поддержкой CORS preflight"""
    
    ALLOWED_USER_AGENTS = [
        "Mozilla", "Chrome", "Safari", "Firefox", "Edge", "PostmanRuntime", "python-requests"
    ]
    
    def __init__(self):
        self._cache = {}
    
    async def validate(self, request: Request, x_webapp_source: str = None) -> bool:
        client_ip = request.client.host if request.client else "unknown"
        
        # Пропускаем проверку для запросов OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            logger.debug("Skipping validation for OPTIONS request", client_ip=client_ip)
            return None
        
        # Проверка X-WebApp-Source
        if not x_webapp_source:
            x_webapp_source = (
                request.headers.get("X-WebApp-Source") or 
                request.headers.get("x-webapp-source")
            )
        
        if x_webapp_source != "webapp":
            logger.warning("Invalid X-WebApp-Source header", 
                         source=x_webapp_source, 
                         client_ip=client_ip)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source header"
            )
        
        # Проверка User-Agent
        user_agent = request.headers.get("user-agent", "")
        if not any(ua in user_agent for ua in self.ALLOWED_USER_AGENTS):
            logger.warning("Suspicious User-Agent", 
                         user_agent=user_agent[:100],
                         client_ip=client_ip)
            if not settings.is_development:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
        
        # Проверка Origin/Referer (строго в production)
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        
        if settings.is_production:
            allowed = False
            if origin:
                allowed = any(origin.startswith(allowed_origin) for allowed_origin in settings.safe_cors_origins)
            elif referer:
                allowed = any(referer.startswith(allowed_origin) for allowed_origin in settings.safe_cors_origins)
            
            if not allowed:
                logger.warning("Invalid origin/referer", 
                             origin=origin, 
                             referer=referer, 
                             client_ip=client_ip)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Origin not allowed"
                )
        
        logger.debug("WebApp source validated successfully", client_ip=client_ip)
        return True

webapp_validator = WebAppSourceValidation()

# ========== SECURITY UTILITIES ==========

def constant_time_compare(val1: str, val2: str) -> bool:
    """Сравнение строк с постоянным временем выполнения для защиты от timing attacks"""
    return hmac.compare_digest(val1.encode('utf-8'), val2.encode('utf-8'))

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    scope: Optional[str] = None
) -> str:
    """Создание JWT токена с улучшенной безопасностью"""
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + (expires_delta or settings.access_token_expire)
    
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "iss": "crm-backend",
        "aud": "crm-admin",
        "jti": secrets.token_urlsafe(32),  # Уникальный идентификатор токена
        "version": "1.0"  # Версия для будущих миграций
    })
    
    if scope:
        to_encode["scope"] = scope
        
    try:
        token = jwt.encode(
            to_encode, 
            settings.SECRET_KEY.get_secret_value(), 
            algorithm=settings.ALGORITHM
        )
        logger.debug("Access token created", 
                    sub=to_encode.get("sub"), 
                    scope=scope,
                    expires_in=expire.isoformat())
        return token
    except Exception as e:
        logger.error("Token creation failed", error=str(e))
        raise SecurityError("Token creation failed")

def create_ws_token(user_id: int) -> str:
    """Создание токена для WebSocket соединений"""
    return create_access_token(
        {"sub": str(user_id)},
        expires_delta=timedelta(minutes=settings.WS_TOKEN_EXPIRE_MINUTES),
        scope="ws"
    )

def create_csrf_token(user_id: Optional[int] = None) -> str:
    """Создание CSRF токена с временной меткой и подписью"""
    timestamp = str(int(time.time()))
    user_id_str = str(user_id) if user_id else "anonymous"
    random_part = secrets.token_urlsafe(64)
    message = f"{timestamp}:{user_id_str}:{random_part}"
    signature = hmac.new(
        settings.SECRET_KEY.get_secret_value().encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{message}:{signature}"

def verify_csrf_token(token: str, user_id: Optional[int] = None, max_age: int = None) -> bool:
    """Верификация CSRF токена с защитой от timing attacks"""
    if max_age is None:
        max_age = settings.CSRF_TOKEN_EXPIRE_MINUTES * 60
    
    start_time = time.perf_counter()
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return False
            
        timestamp_str, token_user_id, random_part, signature = parts
        
        try:
            timestamp = int(timestamp_str)
            if time.time() - timestamp > max_age:
                logger.debug("CSRF token expired", timestamp=timestamp)
                return False
        except ValueError:
            return False
            
        if user_id is not None and int(token_user_id) != user_id:
            logger.debug("CSRF token user_id mismatch", 
                        expected=user_id, 
                        actual=token_user_id)
            return False
            
        message = f"{timestamp_str}:{token_user_id}:{random_part}"
        expected_signature = hmac.new(
            settings.SECRET_KEY.get_secret_value().encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        result = constant_time_compare(signature, expected_signature)
        # constant_time_compare already provides timing attack protection
        # No need for additional sleep that blocks the event loop
        
        if not result:
            logger.debug("CSRF token signature invalid")
            
        return result
        
    except Exception as e:
        logger.warning("CSRF token verification failed", error=str(e))
        return False

async def validate_csrf_dependency(request: Request) -> bool:
    """Валидация CSRF токена для защищенных методов"""
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return True
    
    if settings.is_development:
        logger.debug("CSRF validation skipped in development mode")
        return True
    
    client_ip = request.client.host if request.client else "unknown"
    csrf_header = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")
    csrf_cookie = request.cookies.get("csrf_token")
    
    if not csrf_header or not csrf_cookie:
        logger.warning(
            "CSRF tokens missing", 
            client_ip=client_ip,
            has_header=bool(csrf_header),
            has_cookie=bool(csrf_cookie),
            path=request.url.path
        )
        raise HTTPException(status_code=403, detail="CSRF token required")
    
    # Проверяем, что токены совпадают (защита от подмены)
    if not constant_time_compare(csrf_header, csrf_cookie):
        logger.warning(
            "CSRF token mismatch", 
            client_ip=client_ip,
            path=request.url.path
        )
        raise HTTPException(status_code=403, detail="CSRF token invalid")
    
    # Получаем user_id для проверки подписи токена
    user_id = None
    if hasattr(request.state, "user") and request.state.user:
        user_id = request.state.user.id
    else:
        # Пытаемся получить user_id из токена доступа
        access_token = request.cookies.get("access_token")
        if access_token:
            try:
                payload = decode_access_token(access_token)
                if payload and payload.sub:
                    user_id = int(payload.sub)
            except Exception as e:
                logger.debug("Could not extract user_id from token", error=str(e))
    
    # Проверяем подпись CSRF токена
    if not verify_csrf_token(csrf_cookie, user_id=user_id):
        logger.warning(
            "CSRF token signature invalid", 
            client_ip=client_ip, 
            user_id=user_id,
            path=request.url.path
        )
        raise HTTPException(status_code=403, detail="CSRF token invalid")
    
    return True

def decode_access_token(token: str) -> Optional[TokenPayload]:
    """Декодирование и валидация JWT токена"""
    if not token or not isinstance(token, str):
        logger.warning("Empty or invalid token provided")
        return None
        
    if len(token.split(".")) != 3:
        logger.warning("Invalid token format")
        return None
        
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            audience="crm-admin",
            issuer="crm-backend",
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "require_aud": True,
                "require_iss": True,
            }
        )
        
        # Дополнительная валидация payload
        if not payload.get("sub"):
            logger.warning("Token missing subject (sub)")
            return None
            
        return TokenPayload(**payload)
        
    except ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except JWTError as e:
        logger.warning("JWT validation failed", error=str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error during token decoding", error=str(e))
        return None

def verify_ws_origin(origin: str) -> bool:
    if settings.is_development:
        return True

    if not origin:
        logger.warning("WebSocket connection without origin header")
        return False

    allowed = settings.safe_cors_origins
    if "*" in allowed:
        return True

    return any(origin == allowed_origin or origin.startswith(allowed_origin + "/") for allowed_origin in allowed)

def validate_restaurant_slug(slug: str) -> bool:
    """Валидация slug ресторана"""
    if not slug or len(slug) > 50:
        return False
    return bool(re.match(r'^[a-zA-Z0-9\-_]+$', slug))

def validate_date_format(date: str) -> bool:
    """Валидация формата даты YYYY-MM-DD"""
    if not date or len(date) != 10:
        return False
    try:
        datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def sanitize_input(input_str: str, max_length: int = 255) -> str:
    """Безопасная санитизация пользовательского ввода"""
    if not input_str:
        return ""
    sanitized = input_str[:max_length]
    # Удаляем потенциально опасные символы
    sanitized = re.sub(r'[<>"\'&]', '', sanitized)
    return sanitized.strip()

def hash_password(password: str) -> str:
    """Хэширование пароля с bcrypt"""
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters long")
    
    # Дополнительная проверка на слишком длинные пароли
    if len(password) > 128:
        raise ValueError("Password too long")
    
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля с защитой от timing attacks.
    bcrypt already has constant-time comparison built in.
    Use asyncio.to_thread() when calling from async context to avoid blocking.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error("Password verification error", error=str(e))
        return False


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    """Async wrapper for verify_password — runs bcrypt in a thread to avoid blocking event loop."""
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)

# ========== RATE LIMITING UTILITIES ==========

class RateLimiter:
    """Простой in-memory rate limiter (в production используйте Redis)"""
    
    def __init__(self):
        self._attempts = {}
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.time()
    
    def is_rate_limited(self, key: str, max_attempts: int, window_seconds: int) -> bool:
        """Проверка превышения лимита запросов"""
        current_time = time.time()
        
        # Периодическая очистка старых записей
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup_old_entries(current_time - window_seconds)
            self._last_cleanup = current_time
        
        if key not in self._attempts:
            self._attempts[key] = []
        
        # Удаляем старые попытки
        self._attempts[key] = [
            attempt_time for attempt_time in self._attempts[key]
            if current_time - attempt_time < window_seconds
        ]
        
        # Проверяем лимит
        if len(self._attempts[key]) >= max_attempts:
            return True
        
        # Добавляем текущую попытку
        self._attempts[key].append(current_time)
        return False
    
    def _cleanup_old_entries(self, cutoff_time: float):
        """Очистка старых записей"""
        keys_to_delete = []
        for key, attempts in self._attempts.items():
            attempts[:] = [t for t in attempts if t > cutoff_time]
            if not attempts:
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self._attempts[key]

# Глобальный экземпляр rate limiter
rate_limiter = RateLimiter()

def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> bool:
    """Проверка rate limit для ключа"""
    return not rate_limiter.is_rate_limited(key, max_attempts, window_seconds)

# ========== TELEGRAM USER EXTRACTION ==========

def validate_telegram_init_data(init_data: str, bot_token: str) -> Optional[Dict[str, Any]]:
    """
    Валидирует подлинность initData от Telegram WebApp.
    """
    try:
        # Разбираем строку на параметры
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop('hash', None)
        if not received_hash:
            return None

        # Сортируем параметры и формируем строку для хэширования
        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed.items())
        )

        # Генерируем секретный ключ
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode(),
            digestmod=hashlib.sha256
        ).digest()

        # Вычисляем хэш
        computed_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        # Сравниваем хэши безопасно
        if not hmac.compare_digest(computed_hash, received_hash):
            return None

        # Достаём и парсим пользователя
        user_data = parsed.get("user")
        if user_data:
            import json
            return json.loads(unquote(user_data))

        return None

    except Exception as e:
        logger.warning("Telegram initData validation error", error=str(e))
        return None

def get_telegram_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """Извлечение и валидация пользователя Telegram из заголовков"""
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        return None

    bot_token = settings.TELEGRAM_BOT_TOKEN.get_secret_value()
    user = validate_telegram_init_data(init_data, bot_token)
    if user:
        logger.debug("Telegram user validated", user_id=user.get("id"))
    return user

# ========== SECURITY HEADERS UTILITIES ==========

def get_security_headers() -> Dict[str, str]:
    """Генерация security headers для ответов"""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    
    if settings.ENABLE_CSP:
        headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "object-src 'none'; "
            "media-src 'self'; "
            "frame-src 'none'; "
            "base-uri 'self';"
        )
    
    if settings.ENABLE_HSTS and settings.is_production:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    return headers