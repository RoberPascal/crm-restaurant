# 🔴 CRM Booking System — Полный отчёт по оптимизации

**Дата анализа:** 15 февраля 2026  
**Критичность:** ВЫСОКАЯ — сервер падает после 5 заявок и при одновременном использовании 10+ пользователями

---

## ОГЛАВЛЕНИЕ

1. [Критические проблемы Backend (ломают сервер)](#1-критические-проблемы-backend)
2. [Серьёзные проблемы Backend (деградация под нагрузкой)](#2-серьёзные-проблемы-backend)
3. [Проблемы архитектуры Backend](#3-проблемы-архитектуры-backend)
4. [Проблемы Frontend CRM](#4-проблемы-frontend-crm)
5. [Проблемы инфраструктуры и деплоя](#5-проблемы-инфраструктуры-и-деплоя)
6. [План действий (приоритеты)](#6-план-действий)

---

## 1. КРИТИЧЕСКИЕ ПРОБЛЕМЫ BACKEND

### 1.1 🔴 `publish_booking_update()` — синхронная сессия внутри async-контекста (ГЛАВНАЯ ПРИЧИНА ПАДЕНИЙ)

**Файл:** `app/services/booking_service.py`, строки ~870-950  
**Суть проблемы:**  
Функция `publish_booking_update()` создаёт **синхронную** сессию БД (`SyncSessionLocal()`) внутри асинхронного FastAPI-приложения:

```python
from app.db.session import SyncSessionLocal

with SyncSessionLocal() as sync_db:
    sync_booking = sync_db.get(Booking, booking_id)
    # ...
```

Это **блокирует весь event loop** на время SQL-запроса. При 10 одновременных пользователях каждый публикующий запрос замораживает **ВСЕ** остальные соединения (WebSocket, HTTP, background tasks) на 50-200ms. После 5 бронирований event loop деградирует в очередь из блокирующих вызовов.

**Почему это критично:**

- `publish_booking_update()` вызывается при КАЖДОМ создании, обновлении и удалении брони
- Синхронный драйвер `psycopg2` блокирует event loop целиком
- При 10 одновременных клиентах — 10 блокирующих операций в очередь, задержки растут экспоненциально

**Решение:**  
Заменить синхронную сессию на асинхронную. `publish_booking_update()` уже вызывается из async-контекста — нужно передавать существующую `db` сессию или использовать `AsyncSessionLocal`.

```python
# ВМЕСТО SyncSessionLocal:
async with AsyncSessionLocal() as db:
    sync_booking = await db.get(Booking, booking_id)
    # ...
```

---

### 1.2 🔴 Отсутствие `--workers` в Uvicorn (один процесс на весь сервер)

**Файл:** `Dockerfile`, последняя строка  
**Суть проблемы:**

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Uvicorn запускается с **одним worker-процессом**. Один процесс = один event loop = одно ядро CPU. При любой блокирующей операции (см. 1.1) весь сервер встает.

**Решение:**

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--limit-concurrency", "100", "--timeout-keep-alive", "30"]
```

Или лучше — использовать Gunicorn с UvicornWorker:

```dockerfile
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "120", "--graceful-timeout", "30"]
```

**ВАЖНО:** При использовании нескольких worker-ов `RateLimitMiddleware` (in-memory dict) перестанет работать корректно — каждый worker будет иметь свой счётчик. Нужно перенести rate limiting в Redis или убрать.

---

### 1.3 🔴 `get_available_slots_for_frontend()` — O(N×M×K) без кэширования

**Файл:** `app/services/slot_generator.py`  
**Суть проблемы:**  
Каждый вызов этой функции:

1. Делает 3-4 SQL-запроса (closed_slots, all_slots, suitable_tables, bookings)
2. Для **каждого** из ~60 time_slots перебирает **все** бронирования 3 раза (окно, до закрытия, на момент старта)
3. Общая сложность: O(slots × bookings × tables) ≈ O(60 × 50 × 20) = 60,000 операций

Эта функция вызывается:

- При каждом WebSocket `slots_refresh` событии (каждая бронь триггерит broadcast)
- При каждом `lock_slot` через WebSocket
- При каждом `request_initial_slots`
- При каждом HTTP GET `/availability`
- При каждом Redis pubsub message

При 10 пользователях с открытой страницей бронирования — **10 одновременных вызовов** на каждое событие.

**Решение:**  
Кэширование результата в Redis с TTL 5-15 секунд:

```python
async def get_available_slots_for_frontend(restaurant, target_date, db, total_guests=None):
    cache_key = f"slots:{restaurant.id}:{target_date}:{total_guests or 'all'}"

    if RedisService.redis:
        cached = await RedisService.redis.get(cache_key)
        if cached:
            return json.loads(cached)

    # ... текущая логика ...

    if RedisService.redis:
        await RedisService.redis.setex(cache_key, 10, json.dumps(result))

    return result
```

---

### 1.4 🔴 WebSocket `handle_slot_state_websocket` — каскадные пересчёты слотов

**Файл:** `app/websocket/slot_state_ws.py`  
**Суть проблемы:**  
При каждом Redis pubsub event `slots_refresh` функция запускает **полный** пересчёт `get_available_slots_for_frontend()` для КАЖДОГО подключенного клиента:

```python
async for message in pubsub.listen():
    if payload.get("action") == "slots_refresh":
        fresh_slots = await get_available_slots_for_frontend(...)
        await websocket.send_json({...})
```

Если подключено 10 клиентов, одно бронирование триггерит 10 полных пересчётов слотов (каждый за ~50-200ms с SQL). Вместе с пунктом 1.3 это даёт каскад блокировок.

**Решение:**

1. Вычислить слоты ОДИН раз и разослать всем клиентам одинаковый результат
2. Использовать debounce (если за 1 секунду пришло 5 событий — пересчитать один раз)
3. Или: broadcast уже готовый JSON из point-of-change, а не пересчитывать для каждого клиента

---

### 1.5 🔴 Commit внутри цикла в `_complete_ended_bookings()` и `_mark_no_show_bookings()`

**Файл:** `app/services/booking_lifecycle.py`, строки ~115, ~195  
**Суть проблемы:**

```python
for booking in batch:
    booking.status = StatusEnum.completed
    await db.commit()          # ← COMMIT НА КАЖДУЮ БРОНЬ!
    await db.refresh(booking)
    await self._publish_status_change(booking, old_status)
```

Каждая бронь = отдельный commit + refresh + publish_booking_update (с синхронной сессией из 1.1). При 50 бронях lifecycle-сервис делает 50 commits, 50 синхронных SQL-запросов, 50 Redis publish — блокируя event loop на секунды.

**Решение:**  
Batch-commit:

```python
for booking in batch:
    booking.status = StatusEnum.completed
    if booking.table_id:
        booking.table_id = None

await db.commit()  # Один commit на весь батч

# Publish events после commit
for booking in batch:
    await self._publish_status_change(booking, old_status)
```

---

## 2. СЕРЬЁЗНЫЕ ПРОБЛЕМЫ BACKEND

### 2.1 🟠 `SlotStateManager.initialize_daily_slots()` вызывается слишком часто

**Файл:** `app/services/slot_state_manager.py`, `app/services/booking_service.py`  
**Суть проблемы:**  
`initialize_daily_slots()` вызывается при:

- Создании каждой брони (`create_booking_with_tables`)
- Удалении брони (`delete_booking_service`)
- Назначении стола (`assign_table_to_booking`)
- Отмене брони (`cancel_booking`)
- Каждом `release_slot_without_table`
- При каждом `get_available_slots_for_frontend` через `_collect_table_states`

Каждый вызов делает SELECT всех бронирований + UPDATE/INSERT всех слотов. При быстрой последовательности бронирований (5 заявок) это 5× полная реинициализация слотов.

**Решение:**

- Добавить флаг "dirty" и debounce (пересчитывать слоты не чаще раза в 2-3 секунды)
- Или: не вызывать полную реинициализацию при каждом действии — обновлять только затронутые слоты
- `_collect_table_states` (вызываемая из `get_suitable_tables`) НЕ должна вызывать `initialize_daily_slots()` — это делает каждый запрос подбора столов ещё одной полной реинициализацией

---

### 2.2 🟠 `process_booking_success()` — дублирующие AsyncSessionLocal()

**Файл:** `app/services/booking_service.py`, строки ~710-770  
**Суть проблемы:**

```python
if restaurant is None:
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as temp_db:
        result = await temp_db.execute(...)

if not is_admin:
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as new_db:
        await publish_booking_created(booking, restaurant, new_db)
```

Каждый вызов создаёт **новую DB-сессию** из пула. При 10 одновременных бронированиях — 10-20 дополнительных соединений из пула (pool_size=20), что может привести к TimeoutError (все 20 connection из пула заняты + 10 overflow).

**Решение:**  
Передавать существующую сессию `db` во все вспомогательные функции, а не создавать новые.

---

### 2.3 🟠 `RateLimitMiddleware` — in-memory dict без thread safety и с memory leak

**Файл:** `app/middleware/security.py`  
**Суть проблемы:**

```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests = {}  # in-memory dict
```

Проблемы:

1. **Memory leak**: `_cleanup_old_entries()` вызывается только когда `current_minute % 10 == 0`. При HTTP-флуде за 10 минут dict может вырасти до тысяч записей
2. **Не работает с несколькими workers**: Каждый Uvicorn worker имеет свой dict — лимиты не шарятся
3. Нет защиты от concurrent access в async-среде (хотя в CPython GIL защищает, это хрупкий код)

**Решение:**  
Перенести rate limiting в Redis (INCR + EXPIRE) или использовать `slowapi`/`fastapi-limiter`.

---

### 2.4 🟠 Каскад из 6 middleware на BaseHTTPMiddleware

**Файл:** `app/main.py`, `_setup_middleware()`  
**Суть проблемы:**

```python
app.add_middleware(OptionsMiddleware)        # BaseHTTPMiddleware
app.add_middleware(ErrorLoggingMiddleware)   # BaseHTTPMiddleware
app.add_middleware(CORSMiddleware)           # Starlette native
app.add_middleware(GZipMiddleware)           # Starlette native
app.add_middleware(CookieAuthMiddleware)     # BaseHTTPMiddleware
app.add_middleware(SecurityHeadersMiddleware) # BaseHTTPMiddleware
app.add_middleware(RateLimitMiddleware)       # BaseHTTPMiddleware
app.add_middleware(RequestLoggingMiddleware)  # BaseHTTPMiddleware
```

`BaseHTTPMiddleware` в Starlette/FastAPI создаёт **отдельный Task** для каждого запроса и использует `anyio.create_memory_object_stream`. 6 слоёв BaseHTTPMiddleware = 6 дополнительных Task + 6 stream-объектов **на каждый HTTP-запрос**. Это значительный overhead при высокой нагрузке.

**Решение:**

- `OptionsMiddleware` — уже дублирует ASGI-interceptor и универсальный OPTIONS route. Удалить один из трёх (сейчас ТРИ обработчика OPTIONS: ASGI-level, OptionsMiddleware, universal_options_handler)
- `RequestLoggingMiddleware` — при `ENABLE_REQUEST_LOGGING=True` логирует **каждый** запрос дважды (request started + completed). В production это до 100+ логов в секунду
- Объединить `ErrorLoggingMiddleware` + `RequestLoggingMiddleware` в один middleware
- Перевести критичные middleware на чистый ASGI для производительности

---

### 2.5 🟠 `CookieAuthMiddleware` — SQL-запрос на КАЖДЫЙ admin-запрос

**Файл:** `app/middleware/cookie_auth.py`  
**Суть проблемы:**

```python
async for db in get_async_db():
    user = await self._get_user_from_token(token, db)
```

Каждый запрос к `/api/v1/admin/*` делает SELECT из таблицы `users`. При 10 активных CRM-пользователях, обновляющих дашборд каждые 5 секунд — ~120 дополнительных SQL-запросов в минуту только на аутентификацию.

**Решение:**  
Кэшировать пользователя в Redis с TTL = 60-300 сек:

```python
cache_key = f"user:auth:{user_id}"
cached = await RedisService.redis.get(cache_key)
if cached:
    return json.loads(cached)
# ... SELECT из БД ...
await RedisService.redis.setex(cache_key, 120, json.dumps(user_data))
```

---

### 2.6 🟠 `create_booking_with_tables()` — retry на 500+ ошибки блокирует event loop

**Файл:** `app/services/booking_service.py`  
**Суть проблемы:**

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=0.1, max=1),
)
async def create_booking_with_tables(...):
```

При ошибке 500 функция retry-ится до 3 раз с exponential backoff. Каждая попытка делает **полный цикл**: SELECT restaurant, SELECT bookings, initialize_daily_slots, SELECT suitable_tables, INSERT booking, COMMIT, publish — это ~10 SQL-запросов. При 3 retry = 30 SQL-запросов на одну неудачную бронь.

**Решение:**

- Убрать retry или ограничить `stop_after_attempt(2)` с `wait_fixed(0.5)`
- Фиксировать первопричину ошибок (скорее всего связано с 1.1 — deadlock от sync session)

---

### 2.7 🟠 `delete_booking_service()` обращается к устаревшим полям `booking.date` и `booking.time`

**Файл:** `app/services/booking_service.py`, строка ~830  
**Суть проблемы:**

```python
await SlotStateManager.cancel_booking(
    restaurant_id=booking.restaurant_id,
    date=booking.date,         # ← booking.date НЕ СУЩЕСТВУЕТ в модели!
    time=booking.time,         # ← booking.time НЕ СУЩЕСТВУЕТ в модели!
    table_id=booking.table_id,
    db=db
)
```

Модель `Booking` (models/booking.py) имеет только `start_datetime` и `end_datetime`. Полей `date` и `time` нет. Это вызывает `AttributeError` при удалении бронирований, что приводит к 500-ошибке.

**Решение:**

```python
date=booking.start_datetime.date(),
time=booking.start_datetime.time(),
```

---

### 2.8 🟠 Такая же проблема в `table_manager.py` — использование `Booking.date` и `Booking.time`

**Файл:** `app/websocket/table_manager.py`, строки ~60-75  
**Суть проблемы:**

```python
bookings_result = await db.execute(
    select(Booking).where(
        Booking.date == date_obj,    # ← НЕ СУЩЕСТВУЕТ
        ...
    )
)
# ...
b_start_dt = dt.combine(date_obj, b.time)  # ← НЕ СУЩЕСТВУЕТ
```

Модель `Booking` не имеет полей `date` и `time`. WebSocket для публичных столов будет падать с ошибкой.

**Решение:**  
Заменить на `Booking.start_datetime` и правильную фильтрацию по дате.

---

## 3. ПРОБЛЕМЫ АРХИТЕКТУРЫ BACKEND

### 3.1 🟡 Три обработчика OPTIONS запросов — конфликты и дублирование

**Файл:** `app/main.py`

1. `options_interceptor_asgi` (raw ASGI, закомментирован но есть)
2. `OptionsMiddleware` (BaseHTTPMiddleware)
3. `universal_options_handler` (FastAPI route)

Все три делают одно и то же. При запросе OPTIONS они могут конфликтовать, и два из трёх отрабатывают впустую.

**Решение:** Оставить ТОЛЬКО CORSMiddleware от Starlette (он уже обрабатывает OPTIONS). Удалить `OptionsMiddleware` и `universal_options_handler`.

---

### 3.2 🟡 `log_booking_status_change()` делает `await db.rollback()` при ошибке

**Файл:** `app/services/booking_service.py`, строка ~83  
**Суть проблемы:**

```python
async def log_booking_status_change(..., db: AsyncSession):
    try:
        await db.execute(query, {...})
    except Exception as e:
        await db.rollback()  # ← ОТКАТЫВАЕТ ВСЮ ТРАНЗАКЦИЮ!
```

Если таблица `booking_history` не существует, `rollback()` откатит **ВСЕ** изменения в текущей сессии, включая основное обновление статуса бронирования!

**Решение:** Использовать `SAVEPOINT` (вложенную транзакцию) или просто логировать ошибку без rollback:

```python
except Exception as e:
    logger.warning("Failed to log status change", error=str(e))
    # НЕ делать rollback!
```

---

### 3.3 🟡 `booking_lifecycle` — три параллельных бесконечных цикла с общим семафором(5)

**Файл:** `app/services/booking_lifecycle.py`  
**Суть проблемы:**

```python
await asyncio.gather(
    self._auto_complete_bookings_loop(),     # каждые 60 сек
    self._auto_mark_no_show_loop(),          # каждые 60 сек
    self._send_upcoming_alerts_loop(),       # каждые 60 сек
)
```

Каждый loop каждые 60 секунд:

1. Получает собственную `AsyncSessionLocal()` сессию из пула
2. Делает SELECT всех подходящих бронирований
3. Обрабатывает каждую по одной с COMMIT

При совпадении циклов — 3 одновременных сессии + 3×Batch queries. Семафор с лимитом 5 не спасает — это только 3 tasks.

**Решение:**

- Объединить в один цикл с поочерёдным выполнением
- Или увеличить `CHECK_INTERVAL_SECONDS` до 120-180 для `no_show` и `alerts`

---

### 3.4 🟡 `create_booking_with_tables()` — двойной commit

**Файл:** `app/services/booking_service.py`

```python
db.add(booking)
await db.flush()
await db.commit()
await db.refresh(booking)

# ... и затем:
await SlotStateManager.initialize_daily_slots(restaurant_id, ..., db)
# initialize_daily_slots НЕ делает commit (по комментарию)
# но вызывает _invalidate_cache и _publish_slot_update
```

`flush()` + `commit()` + `refresh()` = 3 round-trip к БД. Можно заменить на один `commit()`.

---

### 3.5 🟡 `publish_booking_created()` вычисляет `get_suitable_tables()` ПОВТОРНО

**Файл:** `app/services/booking_service.py`, строка ~990  
**Суть проблемы:**

```python
async def publish_booking_created(booking, restaurant, db):
    suitable_tables = await get_suitable_tables(
        restaurant_id=booking.restaurant_id,
        db=db,
        total_guests=booking.adults + (booking.children or 0),
        start_datetime=booking.start_datetime,
        exclude_booking_id=booking.id
    )
```

`get_suitable_tables()` уже вызывалась при создании брони. Повторный вызов = ещё 4-5 SQL-запросов + полная реинициализация слотов.

**Решение:** Передавать уже вычисленные `suitable_tables` из `create_booking_with_tables()`.

---

### 3.6 🟡 Отсутствие connection pooling для Redis

**Файл:** `app/services/redis_service.py`  
**Суть проблемы:**

Создаётся два Redis-клиента (`redis` и `redis_master`) каждый с `max_connections=200`. При этом:

- Каждый WebSocket-клиент создаёт свой PubSub (отдельное соединение)
- Background tasks используют прямые Redis-операции
- Слоты используют Redis для блокировок

200 соединений на инстанс — это слишком много для малого сервера.

**Решение:**  
Уменьшить `REDIS_MAX_CONNECTIONS` до 20-50. Использовать один Redis-клиент для read/write (если нет Redis-кластера).

---

### 3.7 🟡 handle_table_websocket: двойной accept() до рефакторинга

**Файл:** `app/websocket/table_manager.py`, строка ~97  
**Суть проблемы:**

```python
async def handle_table_websocket(websocket: WebSocket, ...):
    try:
        await websocket.accept()  # ← ВТОРОЙ accept()!
```

В `main.py` WebSocket для tables вызывает `await websocket.accept()` перед `handle_table_websocket()`. Но внутри `handle_table_websocket` есть ещё один `accept()`. Двойной accept может вызвать ошибку `RuntimeError: WebSocket is already connected`.

**Решение:** Убрать `accept()` из `handle_table_websocket()`, так как accept уже сделан в main.py. Или наоборот — убрать из main.py.

_Примечание: в main.py для tables accept вызывается ДО handle_table_websocket, а handle_table_websocket тоже вызывает accept. Надо убрать один из двух._

---

## 4. ПРОБЛЕМЫ FRONTEND CRM

### 4.1 🔴 WebSocket не реконнектится после потери соединения (MAX_RECONNECT = 3)

**Файл:** `components/Dashboard/Dashboard.jsx`  
**Суть проблемы:**

```javascript
const MAX_RECONNECT = 3;
// ...
if (!cancelled && reconnectAttempts >= MAX_RECONNECT) return;
```

После 3 неудачных попыток реконнекта WebSocket навсегда отключается. Если сервер перезагрузился или было кратковременное сетевое нарушение — CRM перестаёт получать обновления до перезагрузки страницы.

**Решение:**

- Увеличить `MAX_RECONNECT` до 10-15
- Добавить "бесконечный" reconnect с увеличивающимся интервалом (max 60 секунд)
- Показывать пользователю уведомление "Соединение потеряно" с кнопкой "Переподключить"

---

### 4.2 🟠 `console.log` в production — мусор в консоли и утечка данных

**Файлы:** `utils/api.js`, `components/Dashboard/Dashboard.jsx`, `components/BookingCard/BookingCard.jsx`  
**Суть проблемы:**

```javascript
console.log(`API Request (attempt ${attempt}): ${method} ${url}`, {...});
console.log(`API Response: ${method} ${url}`, {...});
console.log("WebSocket message received:", data);
console.log("Dashboard State:", {...});
console.log("formatTime input:", { timeValue, type: typeof timeValue });
console.log("getEndTime debug:", {...});
```

Десятки `console.log` на каждом HTTP-запросе и WebSocket-сообщении. При быстрой работе с CRM — сотни логов в минуту, что замедляет браузер.

**Решение:**  
Обернуть в условие:

```javascript
const isDev = process.env.NODE_ENV === 'development';
if (isDev) console.log(...);
```

Или использовать единый logger с уровнями.

---

### 4.3 🟠 `loadBookings` в зависимостях useCallback включает `bookings.length`

**Файл:** `components/Dashboard/Dashboard.jsx`  
**Суть проблемы:**

```javascript
const loadBookings = useCallback(async (...) => {
    if (!force && dateStr === currentDateStr && bookings.length > 0) {
        return;
    }
    // ...
}, [selectedRestaurantId, selectedDate, currentDateStr, bookings.length, ...]);
```

`bookings.length` в массиве зависимостей пересоздаёт `loadBookings` при каждом обновлении bookings. Это триггерит useEffect с WebSocket-реконнектом (так как `loadBookings` в его зависимостях). Потенциально вызывает лишние перезагрузки данных.

**Решение:**  
Убрать `bookings.length` из зависимостей, использовать `bookingsRef.current.length` внутри функции.

---

### 4.4 🟠 Отсутствие debounce на поисковом input

**Файл:** `components/Dashboard/Dashboard.jsx`  
**Суть проблемы:**

```jsx
<input
  type="text"
  placeholder="Поиск по имени или телефону..."
  value={searchQuery}
  onChange={(e) => setSearchQuery(e.target.value)}
/>
```

Каждое нажатие клавиши вызывает `setSearchQuery`, что триггерит `filteredBookings` → `groupedBookings` → полный ре-рендер всех BookingCard. При 50 бронированиях и быстром наборе — ощутимые тормоза.

**Решение:**

```javascript
import { debounce } from "lodash";
const debouncedSearch = useMemo(
  () => debounce((q) => setSearchQuery(q), 300),
  [],
);
```

lodash уже в зависимостях, используйте его.

---

### 4.5 🟠 `useEffect` с WebSocket пересоздаётся при каждом изменении `currentDateStr`

**Файл:** `components/Dashboard/Dashboard.jsx`  
**Суть проблемы:**

```javascript
useEffect(() => {
    // ... connect WebSocket ...
}, [selectedRestaurantSlug, selectedRestaurantId, currentDateStr, ...]);
```

WebSocket для CRM-бронирований привязан к ресторану, НЕ к дате. Но `currentDateStr` в зависимостях заставляет переподключать WebSocket при каждой смене даты. Это неправильно — WebSocket подписан на `booking_updates` для всего ресторана, фильтрация по дате идёт в `onmessage`.

**Решение:**  
Убрать `currentDateStr` из зависимостей useEffect для WebSocket. Хранить текущую дату в ref:

```javascript
const currentDateRef = useRef(currentDateStr);
useEffect(() => {
  currentDateRef.current = currentDateStr;
}, [currentDateStr]);
```

---

### 4.6 🟠 `apiFetch` делает retry на 400-ошибки

**Файл:** `utils/api.js`  
**Суть проблемы:**

```javascript
if (response.status === 400) {
  if (attempt === 0) {
    console.warn("Bad request, retrying with adjusted headers");
    config.headers["Origin"] = window.location.origin;
    return tryRequest(1);
  }
}
```

400 Bad Request — это ошибка клиента, retry не поможет. Добавление `Origin` header ничего не меняет. Это лишний повторный запрос на каждую 400-ошибку.

**Решение:** Убрать retry для 400-ошибок.

---

### 4.7 🟡 `BookingCard` не мемоизирован

**Файл:** `components/BookingCard/BookingCard.jsx`  
**Суть проблемы:**  
`BookingCard` — большой компонент с множеством `useMemo`, `useState`, `useEffect`. При каждом обновлении bookings через WebSocket **ВСЕ** карточки перерендериваются.

**Решение:**  
Обернуть в `React.memo()`:

```javascript
export default React.memo(BookingCard, (prev, next) => {
  return (
    prev.booking.id === next.booking.id &&
    prev.booking.status === next.booking.status &&
    prev.booking.table_id === next.booking.table_id &&
    prev.isOpen === next.isOpen
  );
});
```

---

### 4.8 🟡 `formatBooking` создаёт новый объект каждый раз

**Файл:** `components/Dashboard/Dashboard.jsx`  
**Суть проблемы:**  
`formatBooking` возвращает `{...bookingData, ...}` — новый объект. React будет считать что бронирование изменилось (referential equality fail), даже если данные те же. Это провоцирует лишние ре-рендеры.

**Решение:** Добавить кэш по booking.id или сравнивать перед обновлением:

```javascript
updateBookings((prev) => {
  const exists = prev.find((b) => b.id === formatted.id);
  if (exists && JSON.stringify(exists) === JSON.stringify(formatted))
    return prev;
  // ...update
});
```

---

### 4.9 🟡 Отсутствие `Suspense` и skeleton loading

При переключении дат и ресторанов пользователь видит либо ничего, либо `loading`-спиннер. Skeleton loading позволит улучшить perceived performance.

---

## 5. ПРОБЛЕМЫ ИНФРАСТРУКТУРЫ И ДЕПЛОЯ

### 5.1 🔴 Один воркер Uvicorn без Gunicorn (повтор из 1.2)

Сервер обрабатывает все запросы в одном процессе. Любая блокировка event loop замораживает всё.

---

### 5.2 🟠 HEALTHCHECK в Dockerfile вызывает внешний URL

```dockerfile
HEALTHCHECK CMD python -c "import requests; requests.get('https://server.pticasinicafamily.ru//health')"
```

Проблемы:

1. Двойной слеш `//health`
2. Обращение к **внешнему** URL вместо localhost — healthcheck пойдёт через DNS, TLS, reverse proxy и вернётся. Это медленно и бессмысленно
3. `requests` не в `requirements.txt`, healthcheck ВСЕГДА падает с `ModuleNotFoundError`!

**Решение:**

```dockerfile
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
```

Или через `curl`:

```dockerfile
RUN apt-get update && apt-get install -y curl
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
```

---

### 5.3 🟠 `celery[redis]` в requirements.txt, но Celery не используется

```
celery[redis]>=5.3.6
```

Celery нигде не импортируется и не запускается. Это лишняя зависимость, увеличивающая Docker-образ на ~50MB.

**Решение:** Удалить из requirements.txt.

---

### 5.4 🟡 `DB_POOL_SIZE=20` + `DB_MAX_OVERFLOW=10` для одного worker

Пул на 30 соединений к PostgreSQL при одном Uvicorn worker — все 30 используются в одном event loop. При переходе на 4 workers будет 4 × 30 = 120 соединений, что может превысить лимит PostgreSQL (обычно `max_connections=100`).

**Решение:**  
При переходе на multi-worker: уменьшить `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`. Итого: 4 × 10 = 40 соединений.

---

### 5.5 🟡 `aiohttp` для Strapi sync — создаёт новый `ClientSession` на каждый вызов

**Файл:** `app/core/sync_service.py`

```python
async with aiohttp.ClientSession(timeout=timeout) as session:
    async with session.get(url, headers=headers, params=params) as resp:
```

Каждый вызов `fetch_restaurants_from_strapi()` создаёт новый TCP-connection. При `STRAPI_SYNC_INTERVAL=300` это не критично, но если sync вызывается чаще — лучше переиспользовать сессию.

---

## 6. ПЛАН ДЕЙСТВИЙ (Приоритеты)

### ФАЗА 1 — НЕМЕДЛЕННО (исправляет падения сервера)

| #   | Что сделать                                                                      | Оценка   | Риск поломки |
| --- | -------------------------------------------------------------------------------- | -------- | ------------ |
| 1   | **Заменить SyncSessionLocal на AsyncSessionLocal** в `publish_booking_update()`  | 1-2 часа | Низкий       |
| 2   | **Добавить `--workers 4`** в Dockerfile CMD                                      | 5 минут  | Низкий\*     |
| 3   | **Добавить кэширование** в `get_available_slots_for_frontend()` (Redis, TTL=10s) | 2-3 часа | Низкий       |
| 4   | **Исправить двойной accept()** в table_manager.py                                | 5 минут  | Низкий       |
| 5   | **Исправить обращения к booking.date/booking.time** (заменить на start_datetime) | 30 минут | Низкий       |
| 6   | **Исправить HEALTHCHECK** в Dockerfile                                           | 5 минут  | Нулевой      |

_\*При добавлении workers перенести RateLimitMiddleware в Redis или временно отключить (RATE_LIMIT_PER_MINUTE=0)_

### ФАЗА 2 — В БЛИЖАЙШИЕ ДНИ (устраняет деградацию)

| #   | Что сделать                                                           | Оценка   | Риск поломки |
| --- | --------------------------------------------------------------------- | -------- | ------------ |
| 7   | Batch commit в booking_lifecycle (вместо commit на каждую бронь)      | 1 час    | Низкий       |
| 8   | Убрать вызов `initialize_daily_slots()` из `_collect_table_states`    | 30 минут | Средний\*\*  |
| 9   | Debounce broadcast слотов (1 пересчёт → 1 broadcast на всех клиентов) | 2-3 часа | Средний      |
| 10  | Кэшировать user в CookieAuthMiddleware через Redis                    | 1-2 часа | Низкий       |
| 11  | Убрать console.log из production-кода frontend                        | 30 минут | Нулевой      |
| 12  | Убрать `currentDateStr` из зависимостей WS useEffect                  | 15 минут | Низкий       |
| 13  | Мемоизировать BookingCard через React.memo                            | 15 минут | Низкий       |

_\*\*Нужно убедиться что слоты уже инициализированы при старте приложения (сейчас это делается в startup)_

### ФАЗА 3 — АРХИТЕКТУРНЫЕ УЛУЧШЕНИЯ

| #   | Что сделать                                                         | Оценка   |
| --- | ------------------------------------------------------------------- | -------- |
| 14  | Объединить 3 обработчика OPTIONS в один (через CORSMiddleware)      | 1 час    |
| 15  | Объединить ErrorLogging + RequestLogging middleware                 | 30 минут |
| 16  | Перенести RateLimiting в Redis                                      | 2 часа   |
| 17  | Удалить Celery из requirements.txt                                  | 5 минут  |
| 18  | Добавить debounce для поиска на frontend                            | 15 минут |
| 19  | Убрать retry на 400-ошибки в apiFetch                               | 10 минут |
| 20  | Уменьшить REDIS_MAX_CONNECTIONS до 50                               | 5 минут  |
| 21  | Добавить WS reconnect с бесконечным retry + UI-индикатор            | 1-2 часа |
| 22  | Передавать существующую db-сессию вместо создания AsyncSessionLocal | 2-3 часа |
| 23  | Исправить rollback в log_booking_status_change                      | 10 минут |

---

## ОЖИДАЕМЫЙ ЭФФЕКТ

После внедрения Фазы 1:

- Сервер перестанет падать от 5 заявок (устранение блокировки event loop)
- 4 workers = 4× throughput
- Кэширование слотов уменьшит нагрузку на БД в ~10 раз при WebSocket-broadcast

После внедрения Фазы 2:

- Стабильная работа при 50+ одновременных пользователях
- Время ответа API < 200ms вместо текущих 1-5 секунд при нагрузке
- WebSocket будут получать обновления с задержкой < 1 секунда

---

> ⚠️ **ВАЖНО:** Все изменения нужно вносить постепенно и тестировать. Фаза 1 — минимально инвазивные правки. Фаза 2 — более глубокие, но всё ещё безопасные. Фаза 3 — рефакторинг, требующий тщательного тестирования.
