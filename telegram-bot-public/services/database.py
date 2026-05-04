# services/database.py
"""
Сервис для работы с базой данных
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class DatabaseService:
    """Сервис для работы с БД"""
    
    def __init__(self, database_url: str):
        # Преобразуем URL для asyncpg если нужно
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        
        self.engine = create_async_engine(
            database_url,
            echo=False,
            pool_recycle=3600,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        self.SessionLocal = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def initialize(self):
        """Инициализация подключения"""
        async with self.engine.begin() as conn:
            # Проверяем подключение
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection established")
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Получить пользователя по Telegram ID"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                text("SELECT id, telegram_user_id, first_name, last_name, phone FROM user_public WHERE telegram_user_id = :tg_id"),
                {"tg_id": telegram_id}
            )
            row = result.first()
            if row:
                return {
                    'id': row[0],
                    'telegram_user_id': row[1],
                    'first_name': row[2],
                    'last_name': row[3],
                    'phone': row[4],
                }
            return None
    
    async def get_user_by_public_id(self, user_public_id: int) -> Optional[Dict]:
        """Получить пользователя по user_public.id"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                text("SELECT id, telegram_user_id, first_name, last_name, phone FROM user_public WHERE id = :user_id"),
                {"user_id": user_public_id}
            )
            row = result.first()
            if row:
                return {
                    'id': row[0],
                    'telegram_user_id': row[1],
                    'first_name': row[2],
                    'last_name': row[3],
                    'phone': row[4],
                }
            return None
    
    async def get_user_by_phone(self, phone: str) -> Optional[Dict]:
        """Получить пользователя по телефону"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                text("SELECT id, telegram_user_id, first_name, last_name, phone FROM user_public WHERE phone = :phone"),
                {"phone": phone}
            )
            row = result.first()
            if row:
                return {
                    'id': row[0],
                    'telegram_user_id': row[1],
                    'first_name': row[2],
                    'last_name': row[3],
                    'phone': row[4],
                }
            return None
    
    async def get_user_by_booking_id(self, booking_id: int) -> Optional[Dict]:
        """Получить пользователя по ID бронирования"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT up.id, up.telegram_user_id, up.first_name, up.last_name, up.phone
                    FROM user_public up
                    JOIN bookings b ON b.user_public_id = up.id
                    WHERE b.id = :booking_id
                """),
                {"booking_id": booking_id}
            )
            row = result.first()
            if row:
                return {
                    'id': row[0],
                    'telegram_user_id': row[1],
                    'first_name': row[2],
                    'last_name': row[3],
                    'phone': row[4],
                }
            return None

    async def get_booking_by_id(self, booking_id: int) -> Optional[Dict]:
        """Получить бронирование по ID"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT 
                        b.id,
                        b.start_datetime,
                        b.end_datetime,
                        b.name,
                        b.phone,
                        b.adults,
                        b.children,
                        b.status,
                        b.wishes,
                        t.number as table_number,
                        r.name as restaurant_name
                    FROM bookings b
                    LEFT JOIN tables t ON b.table_id = t.id
                    LEFT JOIN restaurants r ON b.restaurant_id = r.id
                    WHERE b.id = :booking_id
                """),
                {"booking_id": booking_id}
            )
            row = result.first()

            if row:
                start_dt = row[1]
                end_dt = row[2]

                return {
                    'id': row[0],
                    'start_datetime': start_dt.isoformat() if start_dt else None,
                    'end_datetime': end_dt.isoformat() if end_dt else None,
                    'date': start_dt.date().isoformat() if start_dt else None,
                    'time': start_dt.time().strftime("%H:%M") if start_dt else None,
                    'name': row[3],
                    'phone': row[4],
                    'adults': row[5],
                    'children': row[6],
                    'status': row[7] if isinstance(row[7], str) else (
                        row[7].value if hasattr(row[7], 'value') else str(row[7])),
                    'wishes': row[8],
                    'table_number': row[9],
                    'restaurant_name': row[10] if row[10] else 'Бар'
                }

            return None

    async def get_user_bookings(self, telegram_id: int) -> List[Dict]:
        """Получить бронирования пользователя"""
        async with self.SessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT 
                        b.id, 
                        r.name as restaurant_name, 
                        b.start_datetime,
                        b.end_datetime,
                        b.adults, 
                        b.children, 
                        b.status,
                        t.number as table_number
                    FROM bookings b
                    JOIN user_public up ON b.user_public_id = up.id
                    LEFT JOIN restaurants r ON b.restaurant_id = r.id
                    LEFT JOIN tables t ON b.table_id = t.id
                    WHERE up.telegram_user_id = :tg_id
                    ORDER BY b.start_datetime DESC
                    LIMIT 20
                """),
                {"tg_id": telegram_id}
            )
            rows = result.all()

            bookings = []
            for row in rows:
                start_dt = row[2]  # start_datetime
                end_dt = row[3]  # end_datetime

                bookings.append({
                    'id': row[0],
                    'restaurant_name': row[1],
                    'date': start_dt.date().isoformat() if start_dt else None,
                    'time': start_dt.time().strftime("%H:%M") if start_dt else None,
                    'start_datetime': start_dt.isoformat() if start_dt else None,
                    'end_datetime': end_dt.isoformat() if end_dt else None,
                    'adults': row[4],
                    'children': row[5],
                    'status': row[6] if isinstance(row[6], str) else (
                        row[6].value if hasattr(row[6], 'value') else str(row[6])),
                    'table_number': row[7]
                })

            return bookings

    async def get_upcoming_bookings(self, hours_ahead: int = 24) -> List[Dict]:
        """Получить предстоящие бронирования для напоминаний"""
        async with self.SessionLocal() as session:
            now = datetime.now(timezone.utc)
            target_time = now + timedelta(hours=hours_ahead)
            
            # Конвертируем в naive datetime (без timezone) для сравнения с timestamp without timezone в БД
            now_naive = now.replace(tzinfo=None)
            target_time_naive = target_time.replace(tzinfo=None)

            result = await session.execute(
                text("""
                    SELECT 
                        b.id, 
                        up.telegram_user_id, 
                        r.name as restaurant_name, 
                        b.start_datetime,
                        b.end_datetime,
                        b.adults, 
                        b.children, 
                        b.name, 
                        b.phone,
                        t.number as table_number,
                        r.schedule
                    FROM bookings b
                    JOIN user_public up ON b.user_public_id = up.id
                    LEFT JOIN restaurants r ON b.restaurant_id = r.id
                    LEFT JOIN tables t ON b.table_id = t.id
                    WHERE b.start_datetime >= :now
                      AND b.start_datetime <= :target_time
                      AND b.status IN ('pending', 'confirmed', 'assigned')
                      AND up.telegram_user_id IS NOT NULL
                    ORDER BY b.start_datetime
                """),
                {
                    "now": now_naive,
                    "target_time": target_time_naive
                }
            )
            rows = result.all()

            bookings = []
            for row in rows:
                start_dt = row[3]  # start_datetime
                end_dt = row[4]  # end_datetime
                schedule_json = row[10]  # schedule JSON
                
                # Извлекаем время закрытия из расписания
                closing_time = None
                if start_dt and schedule_json:
                    try:
                        import json
                        day_of_week = start_dt.weekday()  # 0=Пн, 6=Вс
                        schedule = json.loads(schedule_json) if isinstance(schedule_json, str) else schedule_json
                        for day_schedule in schedule:
                            if day_schedule.get('day') == day_of_week:
                                closing_time = day_schedule.get('close')
                                break
                    except Exception:
                        pass

                bookings.append({
                    'id': row[0],
                    'telegram_user_id': row[1],
                    'restaurant_name': row[2],
                    'date': start_dt.date().isoformat() if start_dt else None,
                    'time': start_dt.time().strftime("%H:%M") if start_dt else None,
                    'start_datetime': start_dt.isoformat() if start_dt else None,
                    'end_datetime': end_dt.isoformat() if end_dt else None,
                    'end_time': end_dt.time().strftime("%H:%M") if end_dt else None,
                    'adults': row[5],
                    'children': row[6],
                    'name': row[7],
                    'phone': row[8],
                    'table_number': row[9],
                    'closing_time': closing_time
                })

            return bookings

    async def get_ending_bookings(self) -> List[Dict]:
        """Получить бронирования, которые скоро завершатся"""
        async with self.SessionLocal() as session:
            now = datetime.now(timezone.utc)
            now_naive = now.replace(tzinfo=None)  # Конвертируем в naive

            result = await session.execute(
                text("""
                    SELECT 
                        b.id, 
                        r.name as restaurant_name, 
                        b.start_datetime,
                        b.end_datetime,
                        b.name, 
                        b.phone, 
                        t.number as table_number,
                        b.adults, 
                        b.children
                    FROM bookings b
                    LEFT JOIN restaurants r ON b.restaurant_id = r.id
                    LEFT JOIN tables t ON b.table_id = t.id
                    WHERE b.status IN ('assigned', 'arrived', 'confirmed')
                      AND b.start_datetime >= :today
                      AND (
                        (b.end_datetime IS NOT NULL AND b.end_datetime <= :now)
                        OR (b.end_datetime IS NULL AND b.start_datetime <= :now)
                      )
                """),
                {
                    "today": now.date(),
                    "now": now_naive
                }
            )
            rows = result.all()

            bookings = []
            for row in rows:
                start_dt = row[2]
                end_dt = row[3]

                bookings.append({
                    'id': row[0],
                    'restaurant_name': row[1],
                    'start_datetime': start_dt.isoformat() if start_dt else None,
                    'end_datetime': end_dt.isoformat() if end_dt else None,
                    'name': row[4],
                    'phone': row[5],
                    'table_number': row[6],
                    'adults': row[7],
                    'children': row[8]
                })

            return bookings

    async def close(self):
        """Закрыть подключение"""
        await self.engine.dispose()
        logger.info("Database connection closed")

