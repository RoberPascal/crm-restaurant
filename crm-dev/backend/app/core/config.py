# app/core/config.py
from pydantic_settings import BaseSettings
from pydantic import AnyUrl, Field, field_validator, SecretStr, ConfigDict
from typing import List, Optional, Union
import os
import json
import re
from datetime import timedelta


class Settings(BaseSettings):
    # Безопасность и окружение
    ENVIRONMENT: str = Field("development", pattern="^(development|staging|production|testing)$")
    LOG_LEVEL: str = Field("info", pattern="^(debug|info|warning|error|critical)$")
    
    # Базы данных
    DATABASE_URL: SecretStr = Field(...)
    REDIS_URL: SecretStr = Field("redis://localhost:6379/0")
    REDIS_MASTER_URL: Optional[SecretStr] = Field(None)
    REDIS_MAX_CONNECTIONS: int = Field(200, ge=1, le=1000)
    
    # JWT и безопасность
    SECRET_KEY: SecretStr = Field(...)
    ALGORITHM: str = Field("HS256", pattern="^(HS256|HS384|HS512)$")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, ge=5, le=1440)
    WS_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=1, le=120)
    
    # Cookie security
    SECURE_COOKIES: bool = Field(
        default_factory=lambda: os.getenv("CRM_ENVIRONMENT", "development") == "production"
    )
    COOKIE_DOMAIN: Optional[str] = Field(None, min_length=1)
    SAME_SITE_COOKIE: str = Field("lax", pattern="^(lax|strict|none)$")
    CSRF_TOKEN_EXPIRE_MINUTES: int = Field(60, ge=5, le=240)
    
    # CORS security
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["*"] if os.getenv("CRM_ENVIRONMENT", "development") == "development" else [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001"
        ]
    )
    
    # Strapi integration
    STRAPI_PUBLIC_URL: AnyUrl = Field(...)
    STRAPI_API_TOKEN: SecretStr = Field(...)
    STRAPI_SYNC_INTERVAL: int = Field(300, ge=60, le=3600)
    STRAPI_SOFT_DELETE: bool = Field(True)

    TELEGRAM_BOT_TOKEN: SecretStr = Field(...)
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = Field(60, ge=0)
    RATE_LIMIT_PER_HOUR: int = Field(1000, ge=0)
    LOGIN_ATTEMPTS_LIMIT: int = Field(5, ge=1, le=20)
    LOGIN_LOCKOUT_MINUTES: int = Field(15, ge=1, le=1440)
    
    # Security headers
    ENABLE_CSP: bool = Field(True)
    ENABLE_HSTS: bool = Field(True)
    
    TRUSTED_HOSTS: List[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"]
    )
    ENABLE_HTTPS_REDIRECT: bool = Field(False)

    # WebSocket settings
    WEBSOCKET_MAX_SIZE: int = Field(16 * 1024, ge=1024, le=1024 * 1024)  # 16KB
    WEBSOCKET_TIMEOUT: int = Field(3600, ge=60, le=86400)
    WEBSOCKET_RATE_LIMIT: int = Field(100, ge=0, le=1000)
    
    # Application performance
    INITIAL_SLOT_DAYS: int = Field(14, ge=1, le=90)
    BACKGROUND_TASK_TIMEOUT: float = Field(30.0, ge=5.0, le=300.0)
    REDIS_RETRY_ATTEMPTS: int = Field(3, ge=1, le=10)
    REDIS_RETRY_DELAY: float = Field(1.0, ge=0.1, le=10.0)
    
    # Database
    DB_POOL_SIZE: int = Field(20, ge=5, le=100)
    DB_MAX_OVERFLOW: int = Field(10, ge=0, le=50)
    DB_POOL_RECYCLE: int = Field(3600, ge=1800, le=7200)
    DB_POOL_TIMEOUT: int = Field(60, ge=30, le=300)  # Connection timeout in seconds
    DB_ECHO: bool = Field(False)
    
    # Background tasks
    SLOT_INITIALIZATION_HOUR: int = Field(2, ge=0, le=23)
    SLOT_CLEANUP_DAYS: int = Field(30, ge=1, le=365)
    HEALTH_CHECK_INTERVAL: int = Field(300, ge=60, le=1800)
    MAX_CONCURRENT_RESTAURANT_INIT: int = Field(5, ge=1, le=50)
    
    # Monitoring
    TASK_MONITOR_INTERVAL: int = Field(600, ge=60, le=3600)
    CACHE_TTL: int = Field(300, ge=60, le=3600)
    CACHE_ENABLED: bool = Field(True)
    
    # Metrics
    ENABLE_METRICS: bool = Field(False)
    METRICS_PORT: int = Field(9090, ge=1024, le=65535)
    ENABLE_REQUEST_LOGGING: bool = Field(True)
    
    # Uploads
    MAX_UPLOAD_SIZE: int = Field(10 * 1024 * 1024, ge=0, le=100 * 1024 * 1024)
    ALLOWED_UPLOAD_TYPES: List[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/gif", "application/pdf"]
    )
    
    # Email
    SMTP_SERVER: Optional[str] = Field(None)
    SMTP_PORT: int = Field(587, ge=1, le=65535)
    SMTP_USERNAME: Optional[str] = Field(None)
    SMTP_PASSWORD: Optional[SecretStr] = Field(None)
    NOTIFICATION_EMAIL: Optional[str] = Field(None)
    ENABLE_EMAIL_NOTIFICATIONS: bool = Field(False)

    # Timezone
    TIMEZONE: str = Field("Europe/Moscow", pattern="^[A-Za-z/_-]+$")

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CRM_",
        case_sensitive=True,
        extra="ignore"
    )

    # ========================
    # ВАЛИДАТОРЫ
    # ========================

    @field_validator("BACKEND_CORS_ORIGINS", "TRUSTED_HOSTS", mode="before")
    @classmethod
    def parse_list_env(cls, v) -> List[str]:
        """Надёжный парсинг списка из .env: поддерживает CSV и JSON, но безопасен для '*'."""
        if v == "*":
            return ["*"]
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            # Только если точно выглядит как JSON-массив
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if x]
                except (json.JSONDecodeError, TypeError):
                    pass
            # Иначе — считаем CSV через запятую
            return [x.strip() for x in v.split(",") if x.strip()]
        elif isinstance(v, list):
            return [str(x).strip() for x in v]
        return v or []

    @field_validator("ALLOWED_UPLOAD_TYPES", mode="before")
    @classmethod
    def parse_upload_types(cls, v) -> List[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        elif isinstance(v, list):
            return v
        return []

    @field_validator("BACKEND_CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: List[str]) -> List[str]:
        is_prod = os.getenv("CRM_ENVIRONMENT") == "production"
        validated = []
        for origin in v:
            if origin == "*":
                if is_prod:
                    raise ValueError("Wildcard CORS origins not allowed in production")
                validated.append(origin)
                continue
            if not re.match(r'^https?://([a-zA-Z0-9\-\.]+)(:\d+)?$', origin):
                raise ValueError(f"Invalid CORS origin format: {origin}")
            validated.append(origin)
        return validated

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: SecretStr) -> SecretStr:
        url = v.get_secret_value()
        is_prod = os.getenv("CRM_ENVIRONMENT", "").lower() == "production"
        if is_prod and url.startswith("sqlite"):
            raise ValueError("SQLite is not allowed in production. Use PostgreSQL.")
        if not url.startswith(("sqlite:///", "sqlite+aiosqlite://", "postgresql://", "postgresql+asyncpg://")):
            raise ValueError("Invalid DATABASE_URL scheme")
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: SecretStr) -> SecretStr:
        key = v.get_secret_value()
        if len(key) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        if len(set(key)) < 20:
            raise ValueError("SECRET_KEY has insufficient entropy")
        weak_patterns = [r"^[a-zA-Z]+$", r"^[0-9]+$", r"^(.)\1+$"]
        for pattern in weak_patterns:
            if re.match(pattern, key):
                raise ValueError("SECRET_KEY is too weak")
        return v

    @field_validator("SMTP_SERVER")
    @classmethod
    def validate_smtp_config(cls, v, info):
        if info.data.get('ENABLE_EMAIL_NOTIFICATIONS') and not v:
            raise ValueError("SMTP_SERVER is required when email notifications are enabled")
        return v

    # ========================
    # СВОЙСТВА
    # ========================

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    @property
    def database_url(self) -> str:
        url = self.DATABASE_URL.get_secret_value()
        if self.is_production and url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://")
        return url

    @property
    def safe_trusted_hosts(self) -> List[str]:
        """Trusted hosts с localhost/127.0.0.1 для внутренних health check'ов."""
        hosts = set(self.TRUSTED_HOSTS) if self.TRUSTED_HOSTS else set()
        # Всегда разрешаем localhost для Docker HEALTHCHECK и внутренних запросов
        hosts.update(["localhost", "127.0.0.1"])
        return list(hosts)

    @property
    def safe_cors_origins(self) -> List[str]:
        origins = []
        # localhost только для разработки — в проде не нужен
        if not self.is_production:
            origins.extend([
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3001",
            ])
        else:
            # ИСПРАВЛЕНИЕ: Всегда включаем продакшен-домены для CORS
            origins.extend([
                "https://crm.pticasinicafamily.ru",
                "https://pticasinicafamily.ru",
                "https://www.pticasinicafamily.ru",
                "https://server.pticasinicafamily.ru",
            ])
        if self.BACKEND_CORS_ORIGINS and self.BACKEND_CORS_ORIGINS != ["*"]:
            # Добавляем из env, избегая дубликатов
            for origin in self.BACKEND_CORS_ORIGINS:
                if origin not in origins:
                    origins.append(origin)
        return origins

    @property
    def access_token_expire(self) -> timedelta:
        return timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)

    @property
    def csrf_token_expire(self) -> timedelta:
        return timedelta(minutes=self.CSRF_TOKEN_EXPIRE_MINUTES)

    @property
    def database_engine_options(self) -> dict:
        # Увеличиваем пул в продакшене для обработки фоновых задач
        pool_size = self.DB_POOL_SIZE
        max_overflow = self.DB_MAX_OVERFLOW
        
        if self.is_production:
            # В продакшене нужны резервные соединения для фоновых задач
            # Пул 30-40 + overflow 20-30 обычно достаточно для большинства приложений
            pool_size = max(40, self.DB_POOL_SIZE)
            max_overflow = max(20, self.DB_MAX_OVERFLOW)
        
        return {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_recycle": self.DB_POOL_RECYCLE,
            "echo": self.DB_ECHO,
        }

    @property
    def redis_connection_options(self) -> dict:
        return {
            "max_connections": self.REDIS_MAX_CONNECTIONS,
            "retry_attempts": self.REDIS_RETRY_ATTEMPTS,
            "retry_delay": self.REDIS_RETRY_DELAY,
        }

    @property
    def background_task_config(self) -> dict:
        return {
            "slot_initialization_hour": self.SLOT_INITIALIZATION_HOUR,
            "slot_cleanup_days": self.SLOT_CLEANUP_DAYS,
            "health_check_interval": self.HEALTH_CHECK_INTERVAL,
            "strapi_sync_interval": self.STRAPI_SYNC_INTERVAL,
            "restaurant_init_timeout": self.BACKGROUND_TASK_TIMEOUT,
            "max_concurrent_restaurant_init": self.MAX_CONCURRENT_RESTAURANT_INIT,
            "task_monitor_interval": self.TASK_MONITOR_INTERVAL,
        }

    def model_dump_safe(self) -> dict:
        data = self.model_dump()
        sensitive = ['SECRET_KEY', 'DATABASE_URL', 'REDIS_URL', 'STRAPI_API_TOKEN',
                     'TELEGRAM_BOT_TOKEN', 'SMTP_PASSWORD']
        for field in sensitive:
            if field in data and data[field]:
                if isinstance(data[field], SecretStr):
                    data[field] = "***" if data[field].get_secret_value() else None
                else:
                    data[field] = "***" if data[field] else None
        data.update({
            'is_production': self.is_production,
            'is_development': self.is_development,
            'safe_cors_origins': self.safe_cors_origins,
            'database_engine_options': self.database_engine_options,
            'background_task_config': self.background_task_config,
        })
        return data

    def validate_smtp_credentials(self) -> bool:
        if not self.ENABLE_EMAIL_NOTIFICATIONS:
            return True
        required = ['SMTP_SERVER', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'NOTIFICATION_EMAIL']
        for field in required:
            val = getattr(self, field)
            if not val or (isinstance(val, SecretStr) and not val.get_secret_value()):
                return False
        return True


# Создание глобального экземпляра
settings = Settings()

# Финальная валидация SMTP при старте
if settings.ENABLE_EMAIL_NOTIFICATIONS and not settings.validate_smtp_credentials():
    raise ValueError(
        "SMTP configuration is incomplete. "
        "When ENABLE_EMAIL_NOTIFICATIONS is True, "
        "SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, and NOTIFICATION_EMAIL must be set."
    )