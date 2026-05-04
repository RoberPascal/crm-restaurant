"""
Main FastAPI application module.
"""
from contextlib import asynccontextmanager
import asyncio
import time
from typing import List, Optional

from fastapi import FastAPI, WebSocket, Query, status, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.websockets import WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from sqlalchemy import text, select
from app.core.config import settings
from app.core.security import (
    decode_access_token,
    verify_ws_origin,
    validate_restaurant_slug,
    validate_date_format,
)
from app.core.task_monitor import task_monitor
from app.core.background_tasks import daily_slot_initialization
from app.db.session import async_engine
from app.db.base import Base
from app.services.redis_service import RedisService

# Импорт моделей (для создания таблиц)
from app.db.models.enums import StatusEnum, CapacityEnum, SlotStatus
from app.db.models.user_public import UserPublic
from app.db.models.user import User
from app.db.models.restaurant import Restaurant
from app.db.models.table import Table
from app.db.models.slot import TimeSlot
from app.db.models.booking import Booking

# Импорт маршрутов
from app.api.v1.admin import auth, restaurants, tables, bookings, users
from app.api.v1.public import slots_router, public_bookings_router, tables_public
from app.api.v1.public.users import router as public_users_router
from app.api.v1.public.restaurant import router as public_restaurant_router

# Импорт сервисов
from app.core.sync_service import sync_restaurants_from_strapi, periodic_sync
from app.websocket.table_manager import handle_table_websocket
from app.websocket.booking_ws import handle_crm_booking_websocket, redis_booking_listener
from app.websocket.slot_state_ws import handle_slot_state_websocket
from app.services.booking_lifecycle import start_booking_lifecycle_service, stop_booking_lifecycle_service

# Middleware
from app.middleware.cookie_auth import CookieAuthMiddleware
from app.middleware.security import SecurityHeadersMiddleware, RateLimitMiddleware, RequestLoggingMiddleware
from app.middleware.error_logging import ErrorLoggingMiddleware

logger = structlog.get_logger(__name__)


class ApplicationInitializer:
    """Класс для инициализации приложения и управления жизненным циклом."""
    
    def __init__(self):
        self.background_tasks: List[asyncio.Task] = []
    
    async def initialize_database(self):
        """Инициализация базы данных."""
        try:
            async with async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
            
            # Логируем конфигурацию пула
            engine_options = settings.database_engine_options
            logger.info(
                "Database connection pool configured",
                pool_size=engine_options["pool_size"],
                max_overflow=engine_options["max_overflow"],
                pool_recycle=engine_options["pool_recycle"],
                environment=settings.ENVIRONMENT
            )
        except Exception as e:
            logger.error("Database initialization failed", error=str(e))
            if settings.is_production:
                raise
    
    async def initialize_redis_with_retry(self, max_retries: int = 3):
        """Инициализация Redis с механизмом повторных попыток."""
        for attempt in range(max_retries):
            try:
                await RedisService.init_redis()
                logger.info("Redis connected successfully")
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error("Redis connection failed after all retries", error=str(e))
                    RedisService.redis = None
                    if settings.is_production:
                        raise
                else:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Redis connection attempt {attempt + 1} failed, retrying in {wait_time}s",
                        error=str(e)
                    )
                    await asyncio.sleep(wait_time)
    
    async def clear_redis_locks(self):
        """Очистка Redis блокировок при запуске."""
        if not RedisService.redis:
            return
            
        try:
            slot_lock_keys = await RedisService.call("keys", "slot_lock:*")
            table_lock_keys = await RedisService.call("keys", "table_lock:*")
            
            if slot_lock_keys:
                await RedisService.call("delete", *slot_lock_keys, for_write=True)
                logger.info(f"Cleared {len(slot_lock_keys)} slot locks from Redis")
            
            if table_lock_keys:
                await RedisService.call("delete", *table_lock_keys, for_write=True)
                logger.info(f"Cleared {len(table_lock_keys)} table locks from Redis")
                
        except Exception as e:
            logger.warning("Failed to clear Redis locks", error=str(e))
    
    async def initialize_initial_slots(self, days: int = None):
        """Инициализация слотов на первые N дней при запуске приложения."""
        from app.db.session import AsyncSessionLocal
        from app.db.models.restaurant import Restaurant
        from app.services.slot_state_manager import SlotStateManager
        from sqlalchemy import select
        from datetime import date, timedelta
        
        if days is None:
            days = getattr(settings, 'INITIAL_SLOT_DAYS', 60)
        
        async with AsyncSessionLocal() as db:
            try:
                # Получаем все рестораны
                result = await db.execute(select(Restaurant))
                restaurants = result.scalars().all()
                
                if not restaurants:
                    logger.warning("No restaurants found for slot initialization")
                    return
                
                today = date.today()
                total_initialized = 0
                
                for restaurant in restaurants:
                    logger.info(
                        "Initializing slots for restaurant", 
                        slug=restaurant.slug, 
                        id=restaurant.id,
                        schedule=restaurant.schedule,
                        max_booking_days=restaurant.max_booking_days,
                        slot_interval=restaurant.slot_interval_minutes,
                        last_booking_time=restaurant.last_booking_time
                    )
                    
                    for day_offset in range(days):
                        target_date = today + timedelta(days=day_offset)
                        
                        # Проверяем, есть ли уже слоты для этой даты
                        from app.db.models.slot import TimeSlot
                        existing_slots = await db.execute(
                            select(TimeSlot.id).where(
                                TimeSlot.restaurant_id == restaurant.id,
                                TimeSlot.date == target_date
                            ).limit(1)
                        )
                        
                        if not existing_slots.scalar_one_or_none():
                            # Инициализируем слоты только если их еще нет
                            logger.info(
                                "Creating slots for restaurant", 
                                slug=restaurant.slug, 
                                date=target_date
                            )
                            await SlotStateManager.initialize_daily_slots(
                                restaurant_id=restaurant.id,
                                target_date=target_date,
                                db=db
                            )
                            total_initialized += 1
                            logger.debug(
                                "Initialized slots for restaurant", 
                                slug=restaurant.slug, 
                                date=target_date
                            )
                        else:
                            logger.debug(
                                "Slots already exist for restaurant", 
                                slug=restaurant.slug, 
                                date=target_date
                            )
                    
                    # Выносим коммит за пределы внутреннего цикла для уменьшения блокировок
                    await db.commit()
                
                logger.info(
                    "Slot initialization completed", 
                    total_days=total_initialized, 
                    restaurant_count=len(restaurants)
                )
                
            except Exception as e:
                logger.error("Initial slot initialization failed", error=str(e), exc_info=True)
                await db.rollback()
                # Не поднимаем исключение выше, чтобы приложение могло запуститься
                if settings.is_production:
                    logger.error("Slot initialization failed in production, continuing...")
    
    async def perform_initial_sync(self):
        """Выполнение первоначальной синхронизации с Strapi."""
        try:
            logger.info("Performing initial Strapi sync...")
            result = await sync_restaurants_from_strapi()
            if result.get("success"):
                logger.info(
                    "Initial Strapi sync completed",
                    restaurants=result.get("total_restaurants", 0),
                    tables_created=result.get("tables_created", 0),
                )
            else:
                logger.warning("Initial Strapi sync returned failure", error=result.get("error"))
        except Exception as e:
            logger.error("Initial Strapi sync failed, continuing without data", error=str(e))
            # Продолжаем без данных от Strapi
    
    async def ensure_admin_user(self):
        """Создание администратора при первом запуске (автоинициализация после drop DB)."""
        from app.db.session import AsyncSessionLocal
        from app.db.models.user import User
        import secrets
        from pathlib import Path
        
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(select(User).limit(1))
                if result.scalar_one_or_none():
                    return  # Пользователи уже есть
                
                username = "admin"
                password = secrets.token_urlsafe(12)
                
                admin_user = User(
                    username=username,
                    hashed_password=User.hash_password(password),
                    role="admin",
                    is_active=True,
                )
                db.add(admin_user)
                await db.commit()
                
                # Сохраняем учётные данные
                credentials_file = Path("admin-credentials.txt")
                with open(credentials_file, "w", encoding="utf-8") as f:
                    f.write(f"Логин: {username}\n")
                    f.write(f"Пароль: {password}\n")
                    f.write(f"\n⚠️ СОХРАНИТЕ ЭТИ ДАННЫЕ! Пароль больше не будет показан.\n")
                
                logger.info(
                    "Admin user auto-created at startup",
                    username=username,
                    credentials_file=str(credentials_file.absolute()),
                )
            except Exception as e:
                logger.error("Failed to auto-create admin user", error=str(e))
    
    async def run_migrations(self):
        """Запуск миграций БД при старте."""
        from app.db.session import AsyncSessionLocal
        from pathlib import Path
        import importlib.util
        
        migrations_dir = Path(__file__).parent / "db" / "migrations"
        if not migrations_dir.exists():
            return
            
        migration_files = sorted(
            f for f in migrations_dir.iterdir()
            if f.name.endswith('.py') and not f.name.startswith('__')
        )
        
        async with AsyncSessionLocal() as db:
            for migration_file in migration_files:
                try:
                    spec = importlib.util.spec_from_file_location(
                        migration_file.stem, str(migration_file)
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, 'upgrade'):
                        await module.upgrade(db)
                        logger.debug("Migration applied", migration=migration_file.name)
                except Exception as e:
                    # Миграции идемпотентны (IF NOT EXISTS), ошибки ожидаемы
                    logger.debug("Migration skipped or already applied", 
                                migration=migration_file.name, note=str(e)[:100])
    
    async def safe_task_wrapper(self, task_func, task_name: str):
        """Обертка для безопасного выполнения фоновых задач."""
        try:
            await task_func()
        except asyncio.CancelledError:
            logger.info(f"Background task {task_name} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Background task {task_name} failed", error=str(e), exc_info=True)
            # Здесь можно добавить логику перезапуска при необходимости
            if not settings.is_production:
                # В development перезапускаем задачи после ошибок
                await asyncio.sleep(10)
                logger.info(f"Restarting background task {task_name}")
                asyncio.create_task(self.safe_task_wrapper(task_func, task_name))
    
    async def start_background_tasks(self):
        """Запуск фоновых задач."""
        if not RedisService.redis:
            logger.warning("Skipping background tasks – Redis unavailable")
            return
            
        try:
            logger.info("Starting background services...")
            
            # УБИРАЕМ циклический импорт - task_monitor уже импортирован выше
            # from app.core.task_monitor import task_monitor
            
            tasks_config = [
                (periodic_sync, "strapi_sync"),
                (redis_booking_listener, "redis_listener"),
                (daily_slot_initialization, "daily_slots"),
                (task_monitor.start_monitoring, "task_monitor"),
                (start_booking_lifecycle_service, "booking_lifecycle"),
            ]
            
            for task_func, task_name in tasks_config:
                task = asyncio.create_task(
                    self.safe_task_wrapper(task_func, task_name), 
                    name=task_name
                )
                self.background_tasks.append(task)
                
            logger.info(f"Started {len(self.background_tasks)} background tasks")
            
        except Exception as e:
            logger.error("Failed to start background tasks", error=str(e))
    
    async def shutdown_background_tasks(self):
        """Завершение фоновых задач."""
        if not self.background_tasks:
            return
            
        logger.info(f"Shutting down {len(self.background_tasks)} background tasks...")
        shutdown_timeout = getattr(settings, 'BACKGROUND_TASK_TIMEOUT', 30.0)
        
        # Останавливаем мониторинг и lifecycle сервис
        task_monitor.stop_monitoring()
        await stop_booking_lifecycle_service()
        
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=shutdown_timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"Task {task.get_name()} shutdown timeout")
                except Exception as e:
                    logger.error(f"Error cancelling task {task.get_name()}", error=str(e))
        
        self.background_tasks.clear()
    
    async def startup(self):
        """Запуск приложения."""
        logger.info("Application startup initiated")
        
        await self.initialize_database()
        await self.run_migrations()
        await self.ensure_admin_user()
        await self.initialize_redis_with_retry()
        await self.clear_redis_locks()
        await self.perform_initial_sync()
        await self.initialize_initial_slots()
        
        # Rate limiting
        if settings.RATE_LIMIT_PER_MINUTE == 0:
            logger.info("Rate limiting disabled (RATE_LIMIT_PER_MINUTE=0)")
        
        await self.start_background_tasks()
        logger.info("Application startup completed")
    
    async def shutdown(self):
        """Завершение работы приложения."""
        logger.info("Application shutdown initiated")
        
        await self.shutdown_background_tasks()
        
        # Закрытие Redis
        if RedisService.redis:
            try:
                await RedisService.close_redis()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error("Error closing Redis connection", error=str(e))
        
        logger.info("Application shutdown completed")


# Инициализатор приложения
app_initializer = ApplicationInitializer()


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    await app_initializer.startup()
    try:
        yield
    finally:
        await app_initializer.shutdown()


def _validate_time_format(time_str: str) -> bool:
    """Валидация формата времени HH:MM."""
    try:
        if len(time_str) != 5 or time_str[2] != ":":
            return False
        h, m = time_str.split(":")
        hi, mi = int(h), int(m)
        return 0 <= hi <= 23 and 0 <= mi <= 59
    except (ValueError, TypeError):
        return False


def _validate_date_not_in_past(date_str: str, allow_past: bool = False) -> bool:
    """Проверка что дата не в прошлом (с опцией разрешения)."""
    if allow_past:
        return True
        
    from datetime import date
    try:
        year, month, day = map(int, date_str.split('-'))
        target_date = date(year, month, day)
        return target_date >= date.today()
    except (ValueError, TypeError, Exception):
        return False


async def _validate_websocket_parameters(
    websocket: WebSocket, 
    restaurant_slug: str, 
    date: str, 
    time: str = None,
    allow_past_dates: bool = False  # ← НОВЫЙ ПАРАМЕТР
) -> None:
    """Validate WebSocket parameters and raise HTTPException on failure."""
    
    if not restaurant_slug or not date:
        raise HTTPException(status_code=403, detail="Missing required parameters")
    
    if not validate_restaurant_slug(restaurant_slug):
        raise HTTPException(status_code=403, detail="Invalid restaurant slug")
    
    if not validate_date_format(date):
        raise HTTPException(status_code=403, detail="Invalid date format")
    
    # ← ИЗМЕНЕНИЕ: используем allow_past_dates
    if not _validate_date_not_in_past(date, allow_past_dates):
        raise HTTPException(status_code=403, detail="Date cannot be in the past")
    
    if time is not None and not _validate_time_format(time):
        raise HTTPException(status_code=403, detail="Invalid time format")
    
    origin = websocket.headers.get("origin")
    if not verify_ws_origin(origin):
        raise HTTPException(status_code=403, detail="Origin not allowed")

def _extract_auth_token(token: str, authorization: str) -> Optional[str]:
    """Извлечение токена авторизации из различных источников."""
    if token:
        return token
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]
    return None


async def _safe_close_websocket(websocket: WebSocket, code: int = 1000, reason: str = None):
    """Безопасное закрытие WebSocket соединения."""
    try:
        await websocket.close(code=code, reason=reason)
    except Exception as e:
        logger.debug("Error closing WebSocket", error=str(e))


# Метрики (опционально - можно раскомментировать при установке prometheus-client)
"""
try:
    from prometheus_client import Counter, Histogram, Gauge
    
    # WebSocket метрики
    ws_connections = Counter('websocket_connections_total', 
        'Total WebSocket connections', ['endpoint', 'status'])
    ws_messages = Counter('websocket_messages_total',
        'Total WebSocket messages', ['endpoint', 'direction'])
    ws_errors = Counter('websocket_errors_total',
        'WebSocket errors', ['endpoint', 'error_type'])
    
    # Фоновые задачи метрики
    background_errors = Counter('background_task_errors_total',
        'Background task errors', ['task_name'])
    background_task_duration = Histogram('background_task_duration_seconds',
        'Background task duration', ['task_name'])
    
    # Health метрики
    service_health = Gauge('service_health_status',
        'Service health status', ['component'])
    
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("Prometheus client not available, metrics disabled")
"""


# УДАЛЕНО: options_interceptor_asgi — CORSMiddleware уже обрабатывает все OPTIONS запросы.


def create_application() -> FastAPI:
    """Фабрика для создания приложения FastAPI."""
    app = FastAPI(
        lifespan=app_lifespan,
        title="Booking CRM API",
        description="Secure Booking CRM System",
        version="1.0.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    )
    
    _setup_exception_handlers(app)
    _setup_middleware(app)
    _setup_routers(app)
    _setup_websocket_handlers(app)
    _setup_health_endpoints(app)
    
    return app


def _setup_exception_handlers(app: FastAPI):
    """Настройка обработчиков исключений."""
    
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        client_ip = request.client.host if request.client else "unknown"
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            client_ip=client_ip,
            exc_info=not settings.is_production
        )
        
        if settings.is_production:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": str(exc)},
            )


# УДАЛЕНО: OptionsMiddleware — CORSMiddleware уже обрабатывает все OPTIONS запросы.


def _setup_middleware(app: FastAPI):
    """Настройка middleware (порядок важен!)."""
    
    # ОПТИМИЗАЦИЯ: Убран OptionsMiddleware — CORSMiddleware уже обрабатывает OPTIONS.
    # Было 3 обработчика OPTIONS (ASGI interceptor + OptionsMiddleware + CORSMiddleware),
    # теперь только один — CORSMiddleware.
    
    # 1. TrustedHost
    if settings.TRUSTED_HOSTS:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.safe_trusted_hosts,
        )
    
    # 2. Error logging
    app.add_middleware(ErrorLoggingMiddleware)
    
    # 3. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.safe_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=[
            "Authorization", "Content-Type", "X-Requested-With",
            "X-WebApp-Source", "x-webapp-source", "X-Telegram-Init-Data",          
            "X-CSRF-Token", "x-csrf-token", "Accept", "Origin", "Cache-Control", "Cookie",                    
        ],
        expose_headers=["Content-Length", "X-Total-Count"],
        max_age=86400,
    )
    
    # 4. GZip
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # 5. Security middleware
    app.add_middleware(CookieAuthMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)


def _setup_routers(app: FastAPI):
    """Настройка маршрутов API."""
    
    # Admin routes
    app.include_router(auth.router, prefix="/api/v1/admin/auth", tags=["Auth"])
    app.include_router(restaurants.router, prefix="/api/v1/admin/restaurants", tags=["Restaurants"])
    app.include_router(tables.router, prefix="/api/v1/admin/tables", tags=["Tables"])
    app.include_router(bookings.router, prefix="/api/v1/admin/bookings", tags=["Bookings"])
    app.include_router(users.router, prefix="/api/v1/admin", tags=["Users"])
    
    # Новый роутер мониторинга
    try:
        from app.api.v1.admin.monitoring import router as monitoring_router
        app.include_router(monitoring_router, prefix="/api/v1/admin", tags=["Monitoring"])
    except ImportError:
        logger.warning("Monitoring router not available")
    
    # Public routes
    app.include_router(slots_router, prefix="/api/v1/public/slots", tags=["Public Slots"])
    app.include_router(public_bookings_router, prefix="/api/v1/public/bookings", tags=["Public Bookings"])
    app.include_router(tables_public, prefix="/api/v1/public/tables", tags=["Public Tables"])
    app.include_router(public_users_router, prefix="/api/v1/public", tags=["Public Users"])
    app.include_router(public_restaurant_router, prefix="/api/v1/public/restaurant", tags=["Public Restaurant"])


def _setup_websocket_handlers(app: FastAPI):
    """Настройка WebSocket обработчиков."""

    @app.websocket("/ws/public/slots/{restaurant_slug}/{date}")
    async def ws_slots(
            websocket: WebSocket,
            restaurant_slug: str,
            date: str,
    ):
        client_ip = websocket.client.host if websocket.client else "unknown"
        logger.info(
            "Public slots WS connection attempt",
            restaurant_slug=restaurant_slug,
            date=date,
            client_ip=client_ip,
            origin=websocket.headers.get("origin")
        )

        try:
            # ← ИЗМЕНЕНИЕ: разрешаем прошедшие даты для WebSocket
            await _validate_websocket_parameters(
                websocket=websocket,
                restaurant_slug=restaurant_slug,
                date=date,
                allow_past_dates=True  # ← ВАЖНО!
            )

            # Accept the connection
            await websocket.accept()
            logger.info("Public slots WS CONNECTED!", restaurant_slug=restaurant_slug, date=date)

            # Set WebSocket options
            websocket_max_size = getattr(settings, 'WEBSOCKET_MAX_SIZE', 16 * 1024)
            websocket._max_message_size = websocket_max_size

            # Handle the WebSocket connection
            await handle_slot_state_websocket(
                websocket=websocket,
                restaurant_slug=restaurant_slug,
                date_str=date,
            )

        except HTTPException as e:
            logger.warning(
                "Public slots WS rejected",
                restaurant_slug=restaurant_slug,
                date=date,
                reason=e.detail
            )
            await _safe_close_websocket(websocket, status.WS_1008_POLICY_VIOLATION, e.detail)
        except WebSocketDisconnect:
            logger.info("Public slots WS disconnected", restaurant_slug=restaurant_slug, date=date)
        except Exception as e:
            logger.error("Public slots WS error", error=str(e), exc_info=True)
            await _safe_close_websocket(websocket, status.WS_1011_INTERNAL_ERROR)

    @app.websocket("/ws/public/tables/{restaurant_slug}/{date}/{time}")
    async def ws_tables(
            websocket: WebSocket,
            restaurant_slug: str,
            date: str,
            time: str,
    ):
        """WebSocket для публичных столов."""
        client_ip = websocket.client.host if websocket.client else "unknown"

        try:
            # ← ИЗМЕНЕНИЕ: разрешаем прошедшие даты
            await _validate_websocket_parameters(
                websocket=websocket,
                restaurant_slug=restaurant_slug,
                date=date,
                time=time,
                allow_past_dates=True  # ← ВАЖНО!
            )

            await websocket.accept()
            websocket_max_size = getattr(settings, 'WEBSOCKET_MAX_SIZE', 16 * 1024)
            websocket._max_message_size = websocket_max_size

            logger.info(
                "Public tables WS connected",
                restaurant_slug=restaurant_slug,
                date=date,
                time=time,
                client_ip=client_ip
            )

            await handle_table_websocket(websocket, restaurant_slug, date, time)

        except HTTPException as e:
            logger.warning(
                "Public tables WS rejected",
                restaurant_slug=restaurant_slug,
                date=date,
                time=time,
                reason=e.detail
            )
            await _safe_close_websocket(websocket, status.WS_1008_POLICY_VIOLATION, e.detail)
        except WebSocketDisconnect:
            logger.info(
                "Public tables WS disconnected",
                restaurant_slug=restaurant_slug,
                date=date,
                time=time,
                client_ip=client_ip
            )
        except Exception as e:
            logger.error(
                "Public tables WS error",
                error=str(e),
                restaurant_slug=restaurant_slug,
                date=date,
                time=time,
                client_ip=client_ip
            )
            await _safe_close_websocket(websocket, status.WS_1011_INTERNAL_ERROR)
    
    @app.websocket("/ws/crm/bookings/{restaurant_slug}")
    async def ws_crm(
        websocket: WebSocket,
        restaurant_slug: str,
        token: str = Query(None),
        authorization: str = Header(None),
    ):
        """WebSocket для CRM бронирований."""
        client_ip = websocket.client.host if websocket.client else "unknown"
        
        # Метрики
        # if PROMETHEUS_AVAILABLE:
        #     ws_connections.labels(endpoint='crm_bookings', status='attempt').inc()
        
        try:
            # Валидация slug
            if not restaurant_slug or not validate_restaurant_slug(restaurant_slug):
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION, 
                    reason="Invalid restaurant slug"
                )
                return
            
            # Извлечение и валидация токена
            auth_token = _extract_auth_token(token, authorization)
            if not auth_token:
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION, 
                    reason="Authentication token required"
                )
                return
            
            payload = decode_access_token(auth_token)
            if not payload or payload.scope != "ws" or not payload.sub:
                await websocket.close(
                    code=status.WS_1008_POLICY_VIOLATION, 
                    reason="Invalid or insufficient token"
                )
                return
            
            user_id = payload.sub
            await websocket.accept()
            websocket_max_size = getattr(settings, 'WEBSOCKET_MAX_SIZE', 16 * 1024)
            websocket._max_message_size = websocket_max_size
            
            # if PROMETHEUS_AVAILABLE:
            #     ws_connections.labels(endpoint='crm_bookings', status='connected').inc()
            
            logger.info(
                "CRM WS authenticated", 
                user_id=user_id, 
                restaurant_slug=restaurant_slug, 
                client_ip=client_ip
            )
            
            await handle_crm_booking_websocket(websocket, restaurant_slug, user_id)
            
        except asyncio.TimeoutError:
            logger.warning(
                "CRM WS connection timeout", 
                restaurant_slug=restaurant_slug, 
                client_ip=client_ip
            )
            # if PROMETHEUS_AVAILABLE:
            #     ws_errors.labels(endpoint='crm_bookings', error_type='timeout').inc()
            await _safe_close_websocket(websocket, status.WS_1008_POLICY_VIOLATION, "Connection timeout")
        except WebSocketDisconnect:
            logger.info(
                "CRM WS disconnected normally", 
                restaurant_slug=restaurant_slug, 
                client_ip=client_ip
            )
        except Exception as e:
            logger.error(
                "CRM WS connection failed", 
                error=str(e), 
                restaurant_slug=restaurant_slug, 
                client_ip=client_ip
            )
            # if PROMETHEUS_AVAILABLE:
            #     ws_errors.labels(endpoint='crm_bookings', error_type=type(e).__name__).inc()
            await _safe_close_websocket(websocket, status.WS_1011_INTERNAL_ERROR)
        # finally:
        #     if PROMETHEUS_AVAILABLE:
        #         ws_connections.labels(endpoint='crm_bookings', status='disconnected').inc()


def _setup_health_endpoints(app: FastAPI):
    """Настройка health check эндпоинтов."""
    
    # УДАЛЕНО: universal_options_handler — CORSMiddleware уже обрабатывает все OPTIONS запросы.
    
    @app.get("/health")
    async def health_check():
        """Комплексная проверка здоровья приложения."""
        health = {
            "status": "healthy",
            "timestamp": time.time(),
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
        }
        checks = {}

        # Проверка базы данных
        try:
            async with async_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = {"status": "healthy"}
        except Exception as e:
            checks["database"] = {"status": "unhealthy", "error": str(e)}
            health["status"] = "degraded"

        # Проверка Redis
        if RedisService.redis:
            try:
                await RedisService.redis.ping()
                checks["redis"] = {"status": "healthy"}
            except Exception as e:
                checks["redis"] = {"status": "unhealthy", "error": str(e)}
                health["status"] = "degraded"
        else:
            checks["redis"] = {"status": "unavailable"}
            health["status"] = "degraded"

        # Проверка фоновых задач
        try:
            from app.core.background_tasks import get_daily_slots_stats
            task_stats = get_daily_slots_stats()
            
            background_tasks_health = "healthy"
            if task_stats.get("failure_count", 0) > task_stats.get("success_count", 0):
                background_tasks_health = "degraded"
                health["status"] = "degraded"
            
            checks["background_tasks"] = {
                "status": background_tasks_health,
                "stats": task_stats
            }
        except Exception as e:
            checks["background_tasks"] = {"status": "unknown", "error": str(e)}
            health["status"] = "degraded"

        health["checks"] = checks
        return health
    
    @app.get("/health/ready")
    async def readiness_probe():
        """Readiness probe для Kubernetes."""
        checks = {}
        
        # Проверка базы данных
        try:
            async with async_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ready"
        except Exception as e:
            checks["database"] = "not_ready"
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "checks": checks}
            )
        
        # Проверка Redis
        if RedisService.redis:
            try:
                await RedisService.redis.ping()
                checks["redis"] = "ready"
            except Exception as e:
                checks["redis"] = "not_ready"
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={"status": "not_ready", "checks": checks}
                )
        else:
            checks["redis"] = "not_ready"
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "not_ready", "checks": checks}
            )
        
        return {"status": "ready", "checks": checks}
    
    @app.get("/health/live")
    async def liveness_probe():
        """Liveness probe для Kubernetes."""
        return {"status": "alive", "timestamp": time.time()}


# Создание экземпляра приложения
_app = create_application()
# OPTIONS обрабатывается CORSMiddleware (единственный обработчик).
app = _app