"""
Конфигурация бота для персонала
"""
from pydantic_settings import BaseSettings
from pydantic import SecretStr
from typing import List


class Settings(BaseSettings):
    """Настройки бота"""
    
    # Telegram - используем существующие переменные
    TELEGRAM_BOT_STAFF_TOKEN: SecretStr
    TELEGRAM_STAFF_CHAT_ID: int
    TELEGRAM_BOT_STAFF_WEBHOOK_URL: str = ""
    TELEGRAM_WEBHOOK_PATH: str = "/webhook/staff"  # Должен совпадать с URL
    TELEGRAM_WEBHOOK_SECRET: str = ""  # secret_token для верификации webhook
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_BOOKING_CHANNEL: str = "booking_updates"
    
    # Database - создаем из компонентов
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str = "app"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: str = "5432"
    
    # Вычисляемый DATABASE_URL
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    
    # Напоминания
    REMINDER_BEFORE_END_MINUTES: int = 30
    REMINDER_CHECK_INTERVAL_SECONDS: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()