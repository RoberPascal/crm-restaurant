"""
Конфигурация публичного Telegram бота
"""
from pydantic_settings import BaseSettings
from pydantic import SecretStr
import os


class Settings(BaseSettings):
    """Настройки бота"""
    
    # Telegram
    TELEGRAM_BOT_TOKEN: SecretStr
    TELEGRAM_WEBHOOK_URL: str = ""
    TELEGRAM_WEBHOOK_PATH: str = "/webhook"  # Должен совпадать с URL
    TELEGRAM_WEBHOOK_SECRET: str = ""  # secret_token для верификации webhook
    TELEGRAM_WEBAPP_URL: str = ""  # Ссылка на веб-приложение (кнопка в /start)
    TELEGRAM_WEBAPP_TEXT: str = "Открыть приложение"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_BOOKING_CHANNEL: str = "booking_updates"
    
    # Database - используем PostgreSQL компоненты
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
    REMINDER_BEFORE_BOOKING_HOURS: int = 24  # За сколько часов напоминать
    REMINDER_BEFORE_BOOKING_MINUTES: int = 60  # За сколько минут напоминать
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()