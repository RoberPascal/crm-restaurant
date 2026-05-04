# app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from app.core.config import settings
import structlog
import asyncio

logger = structlog.get_logger(__name__)


# === Общая функция для connect_args ===
def get_connect_args(db_url: str):
    """Получение аргументов подключения в зависимости от типа БД"""
    if db_url.startswith("sqlite"):
        return {"check_same_thread": False, "timeout": 30}
    return {}


# === СИНХРОННЫЙ ДВИЖОК ДЛЯ СКРИПТОВ И МИГРАЦИЙ ===
sync_db_url = settings.DATABASE_URL.get_secret_value()

# Принудительно используем psycopg2 для синхронных операций
if sync_db_url.startswith("postgresql+asyncpg://"):
    sync_db_url = sync_db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
elif sync_db_url.startswith("postgres+asyncpg://"):
    sync_db_url = sync_db_url.replace("postgres+asyncpg://", "postgresql+psycopg2://")
elif sync_db_url.startswith("postgresql://"):
    sync_db_url = sync_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
elif sync_db_url.startswith("postgres://"):
    sync_db_url = sync_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
# Для SQLite оставляем как есть
elif sync_db_url.startswith("sqlite://"):
    pass
else:
    # Если вдруг другой формат - добавляем psycopg2
    if not sync_db_url.startswith("postgresql+psycopg2://"):
        sync_db_url = "postgresql+psycopg2://" + sync_db_url.lstrip("postgresql://").lstrip("postgres://")

sync_connect_args = get_connect_args(sync_db_url)

sync_engine_kwargs = {
    "echo": settings.DB_ECHO,
    "future": True,
    "connect_args": sync_connect_args,
}

# Настройки пула для PostgreSQL
if not sync_db_url.startswith("sqlite"):
    sync_engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_size": settings.DB_POOL_SIZE,
    })

# Создаём синхронный движок
sync_engine = create_engine(sync_db_url, **sync_engine_kwargs)

# Сессия для скриптов (init_admin.py, Alembic)
SyncScriptSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=sync_engine,
    class_=Session,
)

# Для обратной совместимости
SyncSessionLocal = SyncScriptSessionLocal


# === АСИНХРОННЫЙ ДВИЖОК (для FastAPI) ===
async_db_url = settings.database_url  # Это уже строка, не SecretStr

# Приводим к async-драйверам
if async_db_url.startswith("sqlite://"):
    async_db_url = async_db_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
elif async_db_url.startswith("postgresql://") or async_db_url.startswith("postgres://"):
    async_db_url = async_db_url.replace("postgresql://", "postgresql+asyncpg://", 1).replace("postgres://", "postgresql+asyncpg://", 1)

async_engine_kwargs = {
    "echo": settings.DB_ECHO,
    "future": True,
}

async_connect_args = get_connect_args(async_db_url)

# Настройки для разных типов БД
if "sqlite" in async_db_url:
    async_engine = create_async_engine(
        async_db_url,
        connect_args=async_connect_args,
        **async_engine_kwargs,
    )
else:
    # Используем настройки из конфига (включая динамическое масштабирование пула)
    engine_options = settings.database_engine_options
    async_engine = create_async_engine(
        async_db_url,
        pool_pre_ping=True,
        pool_recycle=engine_options["pool_recycle"],
        pool_size=engine_options["pool_size"],
        max_overflow=engine_options["max_overflow"],
        pool_timeout=settings.DB_POOL_TIMEOUT,  # Use configurable timeout
        connect_args=async_connect_args,
        **async_engine_kwargs,
    )

AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# === ГЕНЕРАТОРЫ СЕССИЙ ===
def get_db() -> Session:
    """
    Генератор синхронной сессии для зависимостей FastAPI.
    Используется для legacy кода или синхронных операций.
    """
    db = SyncSessionLocal()
    try:
        yield db
        logger.debug("Sync database session completed successfully")
    except Exception as e:
        logger.error("Database session error", error=str(e))
        db.rollback()
        raise
    finally:
        db.close()


async def get_async_db() -> AsyncSession:
    """
    Генератор асинхронной сессии для зависимостей FastAPI.
    Рекомендуется для использования в новом коде.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            logger.debug("Async database session completed successfully")
        except Exception as e:
            logger.error("Async database session error", error=str(e))
            await session.rollback()
            raise


# === УТИЛИТЫ ДЛЯ РАБОТЫ С БД ===
async def execute_in_transaction(db: AsyncSession, operation, *args, **kwargs):
    """
    Безопасное выполнение операции в транзакции.
    """
    try:
        result = await operation(db, *args, **kwargs)
        await db.commit()
        return result
    except Exception as e:
        await db.rollback()
        logger.error("Transaction failed", error=str(e))
        raise


async def health_check_db() -> dict:
    """
    Проверка здоровья подключения к БД.
    Возвращает статус и метрики пула.
    """
    start_time = asyncio.get_event_loop().time()
    
    try:
        async with async_engine.connect() as conn:
            # Простой запрос для проверки соединения
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
            
            # Получаем метрики пула (только для PostgreSQL)
            pool_metrics = {}
            if hasattr(async_engine.pool, 'checkedin') and hasattr(async_engine.pool, 'checkedout'):
                checked_in = async_engine.pool.checkedin()
                checked_out = async_engine.pool.checkedout()
                pool_size = async_engine.pool.size()
                overflow = async_engine.pool.overflow()
                
                pool_metrics = {
                    "connections_checkedin": checked_in,
                    "connections_checkedout": checked_out,
                    "pool_size": pool_size,
                    "overflow_size": overflow,
                    "total_checked_out": checked_out,
                    "available_connections": pool_size - checked_out,
                    "utilization_percent": round((checked_out / pool_size * 100) if pool_size > 0 else 0, 2),
                }
            
            duration = asyncio.get_event_loop().time() - start_time
            
            # Предупреждение если используется больше 80% пула
            status = "healthy"
            if pool_metrics and pool_metrics["utilization_percent"] > 80:
                logger.warning(
                    "Database connection pool utilization high",
                    utilization_percent=pool_metrics["utilization_percent"],
                    checked_out=pool_metrics.get("connections_checkedout"),
                    pool_size=pool_metrics.get("pool_size")
                )
                status = "warning"
            
            return {
                "status": status,
                "response_time": round(duration * 1000, 2),  # ms
                "database_type": "postgresql" if "postgresql" in async_db_url else "sqlite",
                "pool_metrics": pool_metrics,
            }
            
    except Exception as e:
        duration = asyncio.get_event_loop().time() - start_time
        logger.error("Database health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e),
            "response_time": round(duration * 1000, 2),
            "database_type": "postgresql" if "postgresql" in async_db_url else "sqlite",
        }


async def check_db_connection():
    """Проверка подключения к БД при старте приложения"""
    try:
        health = await health_check_db()
        if health["status"] == "healthy":
            logger.info(
                "✅ Database connection successful",
                db_type=health["database_type"],
                response_time_ms=health["response_time"]
            )
        else:
            logger.error(
                "❌ Database connection failed",
                error=health.get("error"),
                response_time_ms=health["response_time"]
            )
            raise ConnectionError(f"Database connection failed: {health.get('error')}")
    except Exception as e:
        logger.error("❌ Database connection check failed", error=str(e))
        raise


# === CONTEXT MANAGERS ===
class DatabaseContext:
    """Контекстный менеджер для работы с БД"""
    
    def __init__(self, async_session: bool = True):
        self.async_session = async_session
        self.session = None
    
    async def __aenter__(self):
        if self.async_session:
            self.session = AsyncSessionLocal()
        else:
            self.session = SyncSessionLocal()
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            if exc_type is not None:
                if self.async_session:
                    await self.session.rollback()
                else:
                    self.session.rollback()
            
            if self.async_session:
                await self.session.close()
            else:
                self.session.close()


# === МЕТРИКИ И МОНИТОРИНГ ===
class DatabaseMetrics:
    """Сбор метрик работы с БД"""
    
    def __init__(self):
        self.query_count = 0
        self.error_count = 0
        self.total_duration = 0.0
    
    def record_query(self, duration: float, success: bool = True):
        """Запись метрик запроса"""
        self.query_count += 1
        self.total_duration += duration
        if not success:
            self.error_count += 1
    
    def get_metrics(self) -> dict:
        """Получение текущих метрик"""
        avg_duration = self.total_duration / self.query_count if self.query_count > 0 else 0
        error_rate = (self.error_count / self.query_count * 100) if self.query_count > 0 else 0
        
        return {
            "total_queries": self.query_count,
            "error_count": self.error_count,
            "error_rate_percent": round(error_rate, 2),
            "average_duration_ms": round(avg_duration * 1000, 2),
            "total_duration_ms": round(self.total_duration * 1000, 2),
        }


# Глобальный экземпляр для метрик
db_metrics = DatabaseMetrics()


# Экспорт основных компонентов
__all__ = [
    'sync_engine',
    'async_engine', 
    'SyncSessionLocal',
    'AsyncSessionLocal',
    'get_db',
    'get_async_db',
    'health_check_db',
    'check_db_connection',
    'DatabaseContext',
    'db_metrics',
    'execute_in_transaction',
]