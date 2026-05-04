# app/core/sync_service.py
import asyncio
import aiohttp
from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.db.session import AsyncSessionLocal
from app.db.models.restaurant import Restaurant
from app.db.models.table import Table
from app.db.models.slot import TimeSlot
from app.core.config import settings
from app.services.slot_generator import invalidate_slots_cache
from app.core.time_utils import get_local_today
from datetime import date, timedelta
import structlog
from typing import Iterable, Optional, Dict, Any
import time

logger = structlog.get_logger(__name__)

DAY_MAP = {"ПН": 0, "ВТ": 1, "СР": 2, "ЧТ": 3, "ПТ": 4, "СБ": 5, "ВС": 6}


async def _reinitialize_future_slots(db: AsyncSession, restaurant: Restaurant, days_ahead: int = 60):
    """Пересоздать слоты на будущие даты после изменения столов ресторана."""
    from app.services.slot_state_manager import SlotStateManager
    from app.services.slot_generator import invalidate_slots_cache
    from app.core.time_utils import get_local_today
    from app.db.models.enums import SlotStatus
    from sqlalchemy import func
    
    today = get_local_today()
    
    # === ИСПРАВЛЕНИЕ: Запоминаем закрытые дни (все слоты UNAVAILABLE) перед удалением ===
    closed_days_result = await db.execute(
        select(TimeSlot.date).where(
            TimeSlot.restaurant_id == restaurant.id,
            TimeSlot.date >= today,
            TimeSlot.status == SlotStatus.UNAVAILABLE
        ).group_by(TimeSlot.date)
    )
    # Получаем даты, где есть UNAVAILABLE слоты
    candidate_closed_dates = {row[0] for row in closed_days_result.all()}
    
    # Проверяем, что ВСЕ слоты на эту дату UNAVAILABLE (а не только часть)
    closed_dates = set()
    for d in candidate_closed_dates:
        all_slots_result = await db.execute(
            select(func.count()).select_from(TimeSlot).where(
                TimeSlot.restaurant_id == restaurant.id,
                TimeSlot.date == d,
                TimeSlot.status != SlotStatus.UNAVAILABLE
            )
        )
        non_unavailable_count = all_slots_result.scalar()
        if non_unavailable_count == 0:
            closed_dates.add(d)
    
    if closed_dates:
        logger.info(
            "Preserving closed days during reinitialize",
            restaurant_id=restaurant.id,
            closed_dates=[d.isoformat() for d in sorted(closed_dates)]
        )
    
    # Удаляем существующие слоты на будущие даты
    await db.execute(
        delete(TimeSlot).where(
            TimeSlot.restaurant_id == restaurant.id,
            TimeSlot.date >= today
        )
    )
    await db.flush()
    
    # Создаем новые слоты с актуальными данными столов
    for day_offset in range(days_ahead):
        target_date = today + timedelta(days=day_offset)
        try:
            await SlotStateManager.initialize_daily_slots(restaurant.id, target_date, db)
        except Exception as e:
            logger.warning(
                "Failed to reinitialize slots for date",
                restaurant_id=restaurant.id,
                date=target_date.isoformat(),
                error=str(e)
            )
    
    await db.flush()
    
    # === ИСПРАВЛЕНИЕ: Восстанавливаем закрытые дни ===
    if closed_dates:
        # Получаем все активные столы для заполнения booked_tables
        tables_result = await db.execute(
            select(Table.id).where(
                Table.restaurant_id == restaurant.id,
                Table.is_active.is_(True)
            )
        )
        all_table_ids = [row[0] for row in tables_result.all()]
        
        for closed_date in closed_dates:
            await db.execute(
                update(TimeSlot).where(
                    TimeSlot.restaurant_id == restaurant.id,
                    TimeSlot.date == closed_date
                ).values(
                    status=SlotStatus.UNAVAILABLE,
                    booked_tables=all_table_ids,
                    available_table_count=0,
                    total_table_count=len(all_table_ids)
                )
            )
            await invalidate_slots_cache(restaurant.id, closed_date)
        
        await db.flush()
        logger.info(
            "Closed days restored after reinitialize",
            restaurant_id=restaurant.id,
            restored_dates=[d.isoformat() for d in sorted(closed_dates)]
        )


# Статистика синхронизации
class SyncStats:
    def __init__(self):
        self.last_sync: Optional[float] = None
        self.last_duration: Optional[float] = None
        self.success_count = 0
        self.error_count = 0
        self.total_restaurants_synced = 0
        self.total_tables_synced = 0
        self.consecutive_errors = 0
        
    def to_dict(self):
        return {
            "last_sync": self.last_sync,
            "last_duration": self.last_duration,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "total_restaurants_synced": self.total_restaurants_synced,
            "total_tables_synced": self.total_tables_synced,
            "consecutive_errors": self.consecutive_errors,
            "success_rate": (
                self.success_count / (self.success_count + self.error_count) * 100 
                if (self.success_count + self.error_count) > 0 else 0
            )
        }

sync_stats = SyncStats()

async def fetch_restaurants_from_strapi() -> dict:
    """Получение данных из Strapi с улучшенной обработкой ошибок."""
    url = f"{str(settings.STRAPI_PUBLIC_URL).rstrip('/')}/api/restaurants"
    headers = {"Authorization": f"Bearer {settings.STRAPI_API_TOKEN.get_secret_value()}"}
    params = {"populate": "*"}
    
    # Конфигурируемый таймаут
    timeout_seconds = getattr(settings, 'STRAPI_TIMEOUT', 30)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            start_time = time.time()
            async with session.get(url, headers=headers, params=params) as resp:
                text = await resp.text()
                duration = time.time() - start_time
                
                if resp.status != 200:
                    logger.error(
                        "Strapi request failed", 
                        status=resp.status, 
                        duration_seconds=round(duration, 2),
                        body=text[:500]
                    )
                    raise RuntimeError(f"Strapi returned status {resp.status}")
                
                logger.debug(
                    "Strapi request successful",
                    status=resp.status,
                    duration_seconds=round(duration, 2),
                    content_length=len(text)
                )
                return await resp.json()
                
        except asyncio.TimeoutError:
            logger.error("Strapi request timeout", timeout_seconds=timeout_seconds)
            raise RuntimeError(f"Strapi request timeout after {timeout_seconds}s")
        except aiohttp.ClientError as e:
            logger.error("Strapi connection error", error=str(e))
            raise RuntimeError(f"Strapi connection error: {str(e)}")
        except Exception as e:
            logger.error("Strapi request error", error=str(e))
            raise


def _normalize_schedule(schedule_items: Iterable[dict]) -> list:
    """Нормализация расписания (чистая функция, без БД)."""
    out = []
    for s in schedule_items or []:
        day_name = (s.get("dayName") or "").upper()
        open_time = (s.get("open") or "")[:5]
        close_time = (s.get("close") or "")[:5]
        if not (day_name and open_time and close_time):
            continue
            
        # Валидация времени
        if not _is_valid_time(open_time) or not _is_valid_time(close_time):
            logger.warning("Invalid time in schedule", day=day_name, open=open_time, close=close_time)
            continue
            
        out.append({
            "day": DAY_MAP.get(day_name, 0),
            "open": open_time,
            "close": close_time,
            "time_slots": []  # Добавляем пустые слоты для совместимости
        })
    return out


def _is_valid_time(time_str: str) -> bool:
    """Проверка валидности времени в формате HH:MM"""
    try:
        if len(time_str) != 5 or time_str[2] != ":":
            return False
        hours, minutes = map(int, time_str.split(":"))
        return 0 <= hours <= 23 and 0 <= minutes <= 59
    except (ValueError, TypeError):
        return False


async def sync_tables_for_restaurant(db: AsyncSession, restaurant: Restaurant, strapi_tables: list) -> Dict[str, int]:
    """Синхронизация столов ресторана с обработкой дубликатов номеров."""
    stats = {"created": 0, "updated": 0, "removed": 0, "skipped": 0, "duplicates": 0}
    
    # Получаем существующие таблицы по strapi_id И по номеру+ресторану
    result = await db.execute(
        select(Table).where(Table.restaurant_id == restaurant.id)
    )
    existing_tables = result.scalars().all()
    
    # Создаем мапы для быстрого поиска
    existing_by_strapi_id = {t.strapi_id: t for t in existing_tables if t.strapi_id is not None}
    existing_by_number = {t.number: t for t in existing_tables}
    
    strapi_ids = set()
    processed_numbers = set()  # Для отслеживания дубликатов в текущей синхронизации

    for item in strapi_tables or []:
        strapi_id = item.get("id")
        if not strapi_id:
            stats["skipped"] += 1
            continue

        strapi_ids.add(strapi_id)

        number = str(item.get("number") or "")
        seats_min = int(item.get("seats_min") or 1)
        seats_max = int(item.get("seats_max") or seats_min)
        is_active = bool(item.get("is_active", True))
        location_mark = item.get("location_mark")
        table_type = item.get("type")

        # Валидация данных
        if seats_min < 1 or seats_max < seats_min:
            logger.warning(
                "Invalid table seats configuration",
                restaurant_slug=restaurant.slug,
                strapi_id=strapi_id,
                seats_min=seats_min,
                seats_max=seats_max
            )
            stats["skipped"] += 1
            continue

        # Проверяем дубликаты номеров в текущей синхронизации
        if number in processed_numbers:
            logger.warning(
                "Duplicate table number in current sync",
                restaurant_slug=restaurant.slug,
                number=number,
                strapi_id=strapi_id
            )
            stats["duplicates"] += 1
            continue

        processed_numbers.add(number)

        # Ищем существующий стол по strapi_id ИЛИ по номеру
        existing_table = None
        if strapi_id in existing_by_strapi_id:
            existing_table = existing_by_strapi_id[strapi_id]
        elif number in existing_by_number:
            existing_table = existing_by_number[number]
            logger.info(
                "Table found by number (strapi_id mismatch)",
                restaurant_slug=restaurant.slug,
                number=number,
                old_strapi_id=existing_table.strapi_id,
                new_strapi_id=strapi_id
            )

        if existing_table:
            # Обновляем существующий стол
            changed = (
                existing_table.number != number
                or existing_table.seats_min != seats_min
                or existing_table.seats_max != seats_max
                or existing_table.is_active != is_active
                or existing_table.location_mark != location_mark
                or existing_table.type != table_type
                or existing_table.strapi_id != strapi_id
            )
            
            if changed:
                existing_table.number = number
                existing_table.seats_min = seats_min
                existing_table.seats_max = seats_max
                existing_table.is_active = is_active
                existing_table.location_mark = location_mark
                existing_table.type = table_type
                existing_table.strapi_id = strapi_id
                stats["updated"] += 1
                logger.debug(
                    "Table updated",
                    restaurant_slug=restaurant.slug,
                    table_id=existing_table.id,
                    number=number
                )
        else:
            # Создаем новый стол с проверкой уникальности (используем SAVEPOINT)
            try:
                async with db.begin_nested():
                    table = Table(
                        strapi_id=strapi_id,
                        restaurant_id=restaurant.id,
                        number=number,
                        seats_min=seats_min,
                        seats_max=seats_max,
                        is_active=is_active,
                        location_mark=location_mark,
                        type=table_type,
                    )
                    db.add(table)
                    await db.flush()  # Пытаемся сохранить сразу для проверки ограничений
                stats["created"] += 1
                logger.debug(
                    "Table created",
                    restaurant_slug=restaurant.slug,
                    strapi_id=strapi_id,
                    number=number
                )
                
                # Обновляем мапы
                existing_by_strapi_id[strapi_id] = table
                existing_by_number[number] = table
                
            except IntegrityError as e:
                # begin_nested() rollback is automatic — only the savepoint is rolled back,
                # the outer transaction is preserved
                logger.error(
                    "Duplicate table number violation",
                    restaurant_slug=restaurant.slug,
                    number=number,
                    strapi_id=strapi_id,
                    error=str(e)
                )
                stats["duplicates"] += 1
                continue

    # Удаление / деактивация таблиц, которых нет в Strapi
    # GUARD: Если Strapi вернул 0 столов — это скорее всего проблема с populate,
    # а не реальное удаление всех столов. Пропускаем soft-delete.
    if not strapi_ids:
        if existing_tables:
            logger.warning(
                "Strapi returned 0 tables for restaurant — skipping table soft-delete to avoid mass deactivation",
                restaurant_slug=restaurant.slug,
                existing_tables_count=len(existing_tables),
            )
        return stats

    tables_to_remove = []
    for table in existing_tables:
        if table.strapi_id is not None and table.strapi_id not in strapi_ids:
            tables_to_remove.append(table.strapi_id)

    if tables_to_remove:
        if settings.STRAPI_SOFT_DELETE:
            result = await db.execute(
                update(Table)
                .where(Table.strapi_id.in_(tables_to_remove))
                .values(is_active=False)
            )
            stats["removed"] = result.rowcount
            logger.debug(
                "Tables soft-deleted",
                restaurant_slug=restaurant.slug,
                count=stats["removed"]
            )
        else:
            result = await db.execute(
                delete(Table).where(Table.strapi_id.in_(tables_to_remove))
            )
            stats["removed"] = result.rowcount
            logger.debug(
                "Tables hard-deleted", 
                restaurant_slug=restaurant.slug,
                count=stats["removed"]
            )

    return stats


async def sync_restaurants_from_strapi() -> Dict[str, Any]:
    """Основная функция синхронизации с улучшенной статистикой."""
    start_time = time.time()
    sync_stats.last_sync = start_time
    
    async with AsyncSessionLocal() as db:
        try:
            max_retries = getattr(settings, 'STRAPI_RETRY_ATTEMPTS', 3)
            data = None

            for attempt in range(max_retries):
                try:
                    logger.info(f"Attempting Strapi sync (attempt {attempt + 1}/{max_retries})")
                    data = await fetch_restaurants_from_strapi()
                    break
                except (RuntimeError, asyncio.TimeoutError) as e:
                    if attempt == max_retries - 1:
                        logger.error("All Strapi sync attempts failed")
                        sync_stats.error_count += 1
                        sync_stats.consecutive_errors += 1
                        return {"success": False, "error": str(e)}
                    wait_time = 2 ** attempt
                    logger.warning(f"Strapi sync failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)

            if not data:
                error_msg = "No data received from Strapi after all attempts"
                logger.warning(error_msg)
                sync_stats.error_count += 1
                sync_stats.consecutive_errors += 1
                return {"success": False, "error": error_msg}

            items = data.get("data", [])
            if not items:
                logger.warning("No restaurants from Strapi")
                sync_stats.error_count += 1
                sync_stats.consecutive_errors += 1
                return {"success": False, "error": "No restaurants data"}

            logger.info("Fetched restaurants from Strapi", count=len(items))
            strapi_slugs = set()
            stats = {
                "created": 0, "updated": 0, "deleted": 0, 
                "tables_created": 0, "tables_updated": 0, "tables_removed": 0,
                "tables_duplicates": 0, "tables_skipped": 0
            }

            for item in items:
                slug = item.get("slug")
                name = item.get("name")
                published = item.get("publishedAt") is not None
                if not slug or not name:
                    logger.warning("Skipping restaurant without slug or name", item_id=item.get("id"))
                    continue

                schedule = _normalize_schedule(item.get("scheduleItem", []))
                strapi_tables = item.get("table", [])

                strapi_slugs.add(slug)

                # Асинхронный запрос
                result = await db.execute(select(Restaurant).where(Restaurant.slug == slug))
                restaurant = result.scalars().first()

                if restaurant:
                    # Собираем все поля из Strapi для полной синхронизации
                    strapi_id = item.get("id")
                    # last_booking_time управляется только через админку, не синхронизируется из Strapi
                    max_booking_days = item.get("max_booking_days") or 60
                    slot_interval = item.get("slot_interval_minutes") or 15
                    telegram_chat_id = item.get("telegram_chat_id")
                    
                    # Проверяем изменения в полях (кроме last_booking_time)
                    changed = (
                        restaurant.name != name
                        or restaurant.is_published != published
                        or restaurant.schedule != schedule
                        or restaurant.strapi_id != strapi_id
                        or restaurant.max_booking_days != max_booking_days
                        or restaurant.slot_interval_minutes != slot_interval
                        or restaurant.telegram_chat_id != telegram_chat_id
                    )
                    
                    if changed:
                        # Проверяем критичные изменения, требующие пересоздания слотов
                        critical_change = (
                            restaurant.schedule != schedule
                            or restaurant.max_booking_days != max_booking_days
                            or restaurant.slot_interval_minutes != slot_interval
                        )
                        
                        # Обновляем поля (кроме last_booking_time)
                        restaurant.name = name
                        restaurant.is_published = published
                        restaurant.schedule = schedule
                        restaurant.strapi_id = strapi_id
                        restaurant.max_booking_days = max_booking_days
                        restaurant.slot_interval_minutes = slot_interval
                        restaurant.telegram_chat_id = telegram_chat_id
                        stats["updated"] += 1
                        logger.debug("Restaurant updated", slug=slug, name=name, fields_updated=True)
                        
                        # Пересоздаем слоты при критичных изменениях
                        if critical_change:
                            await db.flush()
                            await _reinitialize_future_slots(db, restaurant)
                            logger.info("Slots reinitialized after critical restaurant changes", restaurant_slug=slug)
                else:
                    # Создаем ресторан с полями из Strapi (last_booking_time остается дефолтным)
                    restaurant = Restaurant(
                        strapi_id=item.get("id"),
                        slug=slug,
                        name=name,
                        is_published=published,
                        schedule=schedule,
                        max_booking_days=item.get("max_booking_days") or 60,
                        slot_interval_minutes=item.get("slot_interval_minutes") or 15,
                        # last_booking_time берется из дефолта модели (22:00)
                        telegram_chat_id=item.get("telegram_chat_id"),
                    )
                    db.add(restaurant)
                    stats["created"] += 1
                    logger.debug("Restaurant created", slug=slug, name=name, all_fields=True)

                await db.flush()

                # Синхронизация таблиц
                table_stats = await sync_tables_for_restaurant(db, restaurant, strapi_tables)
                stats["tables_created"] += table_stats["created"]
                stats["tables_updated"] += table_stats["updated"]
                stats["tables_removed"] += table_stats["removed"]
                stats["tables_duplicates"] += table_stats["duplicates"]
                stats["tables_skipped"] += table_stats["skipped"]
                
                if (table_stats["created"] or table_stats["updated"] or 
                    table_stats["removed"] or table_stats["duplicates"]):
                    logger.info(
                        "Synced tables",
                        restaurant_slug=slug,
                        created=table_stats["created"],
                        updated=table_stats["updated"],
                        removed=table_stats["removed"],
                        duplicates=table_stats["duplicates"],
                        skipped=table_stats["skipped"]
                    )
                    
                    # Пересоздаем слоты на будущие даты после изменения столов
                    if table_stats["created"] or table_stats["removed"]:
                        await _reinitialize_future_slots(db, restaurant)
                        logger.info("Future slots reinitialized after table changes", restaurant_slug=slug)

            # Обработка удалённых ресторанов
            if settings.STRAPI_SOFT_DELETE:
                result = await db.execute(
                    select(Restaurant).where(~Restaurant.slug.in_(strapi_slugs))
                )
                to_unpublish = result.scalars().all()
                for r in to_unpublish:
                    if r.is_published:
                        r.is_published = False
                        stats["deleted"] += 1
                        logger.debug("Restaurant unpublished", slug=r.slug)
            else:
                result = await db.execute(
                    delete(Restaurant).where(~Restaurant.slug.in_(strapi_slugs))
                )
                stats["deleted"] = result.rowcount
                logger.debug("Restaurants hard-deleted", count=stats["deleted"])

            await db.commit()
            
            # Обновление статистики
            duration = time.time() - start_time
            sync_stats.last_duration = duration
            sync_stats.success_count += 1
            sync_stats.consecutive_errors = 0
            sync_stats.total_restaurants_synced += len(strapi_slugs)
            sync_stats.total_tables_synced += (stats["tables_created"] + stats["tables_updated"])

            logger.info(
                "✅ Strapi sync complete - all data synchronized",
                duration_seconds=round(duration, 2),
                restaurants_created=stats["created"],
                restaurants_updated=stats["updated"],
                restaurants_deleted=stats["deleted"],
                tables_created=stats["tables_created"],
                tables_updated=stats["tables_updated"],
                tables_removed=stats["tables_removed"],
                tables_duplicates=stats["tables_duplicates"],
                total_restaurants=len(strapi_slugs),
                sync_mode="full"
            )

            # Инвалидация кэша слотов
            today = get_local_today()
            result = await db.execute(select(Restaurant.id).where(Restaurant.slug.in_(strapi_slugs)))
            cache_invalidated = 0
            for row in result.scalars():
                try:
                    await invalidate_slots_cache(row, today)
                    cache_invalidated += 1
                except Exception as e:
                    logger.warning("Failed to invalidate cache", restaurant_id=row, error=str(e))

            stats["cache_invalidated"] = cache_invalidated
            stats["success"] = True
            stats["duration_seconds"] = round(duration, 2)
            stats["total_restaurants"] = len(strapi_slugs)
            
            return stats

        except Exception as e:
            await db.rollback()
            duration = time.time() - start_time
            logger.error(
                "Strapi sync exception", 
                error=str(e), 
                duration_seconds=round(duration, 2),
                exc_info=True
            )
            sync_stats.error_count += 1
            sync_stats.consecutive_errors += 1
            return {"success": False, "error": str(e), "duration_seconds": round(duration, 2)}


async def periodic_sync():
    """Периодический запуск синхронизации с улучшенным управлением."""
    interval = max(60, int(settings.STRAPI_SYNC_INTERVAL or 300))
    backoff = interval  # Начинаем с нормального интервала
    max_backoff = 3600  # 1 hour maximum backoff
    
    logger.info("Starting periodic Strapi sync", interval_seconds=interval)
    
    while True:
        try:
            result = await sync_restaurants_from_strapi()
            
            if result.get("success"):
                backoff = interval  # На успехе — стандартный интервал
                logger.info(
                    "Periodic sync completed successfully",
                    restaurants=result.get("total_restaurants", 0),
                    tables_created=result.get("tables_created", 0),
                    next_sync_seconds=interval,
                )
            else:
                # Exponential backoff on failure
                backoff = min(backoff * 2, max_backoff)
                logger.warning(
                    "Periodic sync failed, increasing backoff",
                    backoff_seconds=backoff,
                    error=result.get("error")
                )
                
        except Exception as e:
            logger.error("Unexpected error in periodic sync", error=str(e))
            backoff = min(backoff * 2, max_backoff)
        
        # Ждем следующий интервал с проверкой shutdown
        try:
            await asyncio.sleep(backoff)
        except asyncio.CancelledError:
            logger.info("Periodic sync cancelled")
            break


def get_sync_stats() -> Dict[str, Any]:
    """Получение статистики синхронизации для мониторинга."""
    return sync_stats.to_dict()


async def manual_sync() -> Dict[str, Any]:
    """Ручной запуск синхронизации для административных задач."""
    logger.info("Manual Strapi sync requested")
    return await sync_restaurants_from_strapi()