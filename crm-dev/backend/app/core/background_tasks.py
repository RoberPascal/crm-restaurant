# app/core/background_tasks.py
from datetime import datetime, timedelta, date
from datetime import timezone as dt_timezone
from typing import List, Optional
import asyncio
import gc
import threading
from app.db.session import AsyncSessionLocal
from app.services.slot_state_manager import SlotStateManager
from app.db.models.restaurant import Restaurant
from sqlalchemy import select, delete
import structlog

logger = structlog.get_logger(__name__)

# Импортируем settings и утилиты
from app.core.config import settings
from app.core.time_utils import get_current_time, get_local_timezone, get_next_slot_initialization_time, local_to_utc

# === Graceful shutdown ===
_shutdown_event = asyncio.Event()

def set_shutdown_event():
    """Вызывается при завершении приложения"""
    _shutdown_event.set()

# === Потокобезопасная статистика (без утечек!) ===
_stats_lock = threading.Lock()
_daily_stats = {
    "total": 0,
    "success": 0,
    "failed": 0,
    "timeout": 0,
    "last_run": None,
    "last_duration": None,
    "consecutive_errors": 0,
}

def update_daily_stats(success: Optional[bool] = None, timeout: bool = False, duration: Optional[float] = None):
    with _stats_lock:
        _daily_stats["total"] += 1
        if success is True:
            _daily_stats["success"] += 1
            _daily_stats["consecutive_errors"] = 0
        elif success is False:
            _daily_stats["failed"] += 1
            _daily_stats["consecutive_errors"] += 1
        if timeout:
            _daily_stats["timeout"] += 1
        if duration is not None:
            _daily_stats["last_duration"] = round(duration, 2)
        _daily_stats["last_run"] = datetime.utcnow().isoformat()

def get_daily_slots_stats() -> dict:
    with _stats_lock:
        data = _daily_stats.copy()
        total = data["total"]
        data["success_rate"] = round(data["success"] / total * 100, 1) if total > 0 else 0.0
        return data


async def initialize_single_restaurant(restaurant: Restaurant, target_date: date) -> bool:
    """Инициализация слотов для одного ресторана с таймаутом и статистикой"""
    start_time = datetime.utcnow()

    try:
        timeout = settings.BACKGROUND_TASK_TIMEOUT or 30.0
        success = await asyncio.wait_for(
            _initialize_restaurant_safe(restaurant, target_date),
            timeout=timeout
        )

        duration = (datetime.utcnow() - start_time).total_seconds()
        update_daily_stats(success=success, duration=duration)

        if success:
            logger.debug(
                "Slots initialized",
                restaurant_id=restaurant.id,
                slug=restaurant.slug,
                date=target_date.isoformat(),
                duration=f"{duration:.2f}s"
            )
        else:
            logger.warning(
                "Slots init failed (returned False)",
                restaurant_id=restaurant.id,
                slug=restaurant.slug,
                date=target_date.isoformat()
            )
        return success

    except asyncio.TimeoutError:
        duration = (datetime.utcnow() - start_time).total_seconds()
        update_daily_stats(success=False, timeout=True, duration=duration)
        logger.error(
            "Restaurant init TIMEOUT",
            restaurant_id=restaurant.id,
            slug=restaurant.slug,
            timeout=timeout,
            duration=f"{duration:.2f}s"
        )
        return False

    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        update_daily_stats(success=False, duration=duration)
        logger.error(
            "Restaurant init EXCEPTION",
            restaurant_id=restaurant.id,
            slug=restaurant.slug,
            error=str(e),
            error_type=type(e).__name__,
            duration=f"{duration:.2f}s",
            exc_info=True
        )
        return False


async def _initialize_restaurant_safe(restaurant: Restaurant, target_date: date) -> bool:
    """Безопасная инициализация с собственной сессией"""
    async with AsyncSessionLocal() as db:
        try:
            from app.db.models.slot import TimeSlot
            existing = await db.execute(
                select(TimeSlot.id)
                .where(TimeSlot.restaurant_id == restaurant.id, TimeSlot.date == target_date)
                .limit(1)
            )
            if existing.scalar_one_or_none():
                logger.debug("Slots already exist", restaurant_id=restaurant.id, date=target_date.isoformat())
                return True

            await SlotStateManager.initialize_daily_slots(
                restaurant_id=restaurant.id,
                target_date=target_date,
                db=db
            )
            await db.commit()
            return True

        except Exception as e:
            await db.rollback()
            logger.error(
                "DB error during init",
                restaurant_id=restaurant.id,
                error=str(e),
                exc_info=True
            )
            return False


def _is_restaurant_open_on_date(restaurant: Restaurant, target_date: date) -> bool:
    try:
        if not restaurant.schedule:
            return True

        day = target_date.weekday()
        schedule_item = next((s for s in restaurant.schedule if s.get("day") == day), None)
        if not schedule_item or not schedule_item.get("time_slots"):
            return False
        return True
    except Exception as e:
        logger.error("Schedule check failed", restaurant_id=restaurant.id, error=str(e))
        return True  # fallback


async def _get_restaurants_for_initialization() -> List[Restaurant]:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Restaurant).where(Restaurant.is_published.is_(True)))
            restaurants = result.scalars().all()
            logger.debug(f"Found {len(restaurants)} published restaurants")
            return restaurants
    except Exception as e:
        logger.error("Failed to load restaurants", error=str(e))
        return []


async def _wait_until_next_execution(next_execution_local: datetime) -> bool:
    """Ожидание до следующего запуска — БЕЗ утечек!"""
    try:
        wait_seconds = (local_to_utc(next_execution_local) - datetime.now(dt_timezone.utc)).total_seconds()
        if wait_seconds <= 0:
            return True

        logger.info(
            "Next slot initialization scheduled",
            at=next_execution_local.isoformat(),
            in_seconds=int(wait_seconds)
        )

        await asyncio.wait_for(_shutdown_event.wait(), timeout=max(wait_seconds, 0))
        return not _shutdown_event.is_set()

    except asyncio.TimeoutError:
        return not _shutdown_event.is_set()
    except Exception as e:
        logger.error("Wait error in background task", error=str(e), exc_info=True)
        return True


async def daily_slot_initialization():
    """Основной цикл инициализации слотов — 100% без утечек"""
    logger.info("Daily slot initialization service STARTED")

    # Первый запуск через минуту после старта
    await asyncio.sleep(60)

    while not _shutdown_event.is_set():
        cycle_start = datetime.utcnow()

        try:
            next_run = await _calculate_next_execution_time()
            if not await _wait_until_next_execution(next_run):
                break

            target_date = (get_current_time() + timedelta(days=1)).date()
            logger.info("Starting daily initialization", date=target_date.isoformat())

            restaurants = await _get_restaurants_for_initialization()
            if not restaurants:
                logger.warning("No restaurants to initialize")
                update_daily_stats(success=False)
                continue

            open_restaurants = [r for r in restaurants if _is_restaurant_open_on_date(r, target_date)]
            logger.info("Restaurants to initialize", open=len(open_restaurants), closed=len(restaurants) - len(open_restaurants))

            if not open_restaurants:
                update_daily_stats(success=False)
                continue

            max_concurrent = getattr(settings, "MAX_CONCURRENT_RESTAURANT_INIT", 5)
            semaphore = asyncio.Semaphore(max_concurrent)

            async def bounded_init(r):
                async with semaphore:
                    return await initialize_single_restaurant(r, target_date)

            # Без return_exceptions=True — исключения не висят в памяти
            results = await asyncio.gather(*(bounded_init(r) for r in open_restaurants))

            success = sum(1 for r in results if r)
            failed = len(results) - success
            duration = (datetime.utcnow() - cycle_start).total_seconds()

            update_daily_stats(success=bool(success), duration=duration)

            logger.info(
                "Daily initialization completed",
                date=target_date.isoformat(),
                success=success,
                failed=failed,
                duration=f"{duration:.2f}s",
                success_rate=f"{(success/len(open_restaurants)*100):.1f}%" if open_restaurants else "0%"
            )

        except Exception as e:
            duration = (datetime.utcnow() - cycle_start).total_seconds()
            update_daily_stats(success=False, duration=duration)
            logger.error("Daily initialization cycle crashed", error=str(e), exc_info=True)
            # Ждём 5 минут перед повтором
            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=300)
            except asyncio.TimeoutError:
                pass

        finally:
            # Принудительно помогаем GC
            gc.collect()

    logger.info("Daily slot initialization service STOPPED")


async def _calculate_next_execution_time() -> datetime:
    return get_next_slot_initialization_time()


async def manual_slot_initialization(days_ahead: int = 1) -> dict:
    target_date = (get_current_time() + timedelta(days=days_ahead)).date()
    restaurants = await _get_restaurants_for_initialization()

    if not restaurants:
        return {"success": False, "error": "No restaurants found"}

    results = await asyncio.gather(*(initialize_single_restaurant(r, target_date) for r in restaurants))
    success = sum(1 for r in results if r)
    total = len(results)

    return {
        "success": True,
        "target_date": target_date.isoformat(),
        "total": total,
        "success_count": success,
        "failed": total - success,
        "success_rate": f"{(success/total*100):.1f}%" if total else "0%",
        "timestamp": datetime.utcnow().isoformat()
    }


async def force_slot_cleanup(days_old: int = 30) -> dict:
    try:
        from app.db.models.slot import TimeSlot
        cutoff = get_current_time().date() - timedelta(days=days_old)

        async with AsyncSessionLocal() as db:
            result = await db.execute(delete(TimeSlot).where(TimeSlot.date < cutoff))
            await db.commit()

            logger.info("Old slots cleaned", deleted=result.rowcount, cutoff=cutoff.isoformat())
            return {
                "success": True,
                "deleted_count": result.rowcount,
                "cutoff_date": cutoff.isoformat(),
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error("Slot cleanup failed", error=str(e), exc_info=True)
        return {"success": False, "error": str(e)}