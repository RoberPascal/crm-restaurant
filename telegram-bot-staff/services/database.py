# services/database.py
"""
Сервис для работы с базой данных для бота персонала
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class DatabaseService:
    """Сервис для работы с БД для персонала"""

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
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection established")

    async def get_today_stats(self) -> Dict:
        """Получить статистику бронирований на сегодня"""
        async with self.SessionLocal() as session:
            today = datetime.now().date()

            result = await session.execute(
                text("""
                    SELECT status, COUNT(*) as count
                    FROM bookings
                    WHERE DATE(start_datetime) = :today
                    GROUP BY status
                """),
                {"today": today}
            )
            rows = result.all()

            stats = {
                'pending': 0,
                'pending_review': 0,
                'confirmed': 0,
                'assigned': 0,
                'arrived': 0,
                'completed': 0,
                'cancelled': 0,
                'no_show': 0,
            }

            for row in rows:
                status = row[0] if isinstance(row[0], str) else (
                    row[0].value if hasattr(row[0], 'value') else str(row[0]))
                count = row[1]
                if status in stats:
                    stats[status] = count

            return stats

    async def get_today_bookings(self) -> List[Dict]:
        """Получить бронирования на сегодня"""
        async with self.SessionLocal() as session:
            today = datetime.now().date()

            result = await session.execute(
                text("""
                    SELECT 
                        b.id,
                        b.start_datetime,
                        b.end_datetime,
                        b.name, 
                        b.adults, 
                        b.children, 
                        b.status, 
                        b.phone,
                        t.number as table_number,
                        r.name as restaurant_name
                    FROM bookings b
                    LEFT JOIN tables t ON b.table_id = t.id
                    LEFT JOIN restaurants r ON b.restaurant_id = r.id
                    WHERE DATE(b.start_datetime) = :today
                    ORDER BY b.start_datetime
                """),
                {"today": today}
            )
            rows = result.all()

            bookings = []
            for row in rows:
                start_dt = row[1]  # start_datetime
                end_dt = row[2]  # end_datetime

                bookings.append({
                    'id': row[0],
                    'start_datetime': start_dt.isoformat() if start_dt else None,
                    'end_datetime': end_dt.isoformat() if end_dt else None,
                    'date': start_dt.date().isoformat() if start_dt else None,
                    'time': start_dt.time().strftime("%H:%M") if start_dt else None,
                    'name': row[3],
                    'adults': row[4],
                    'children': row[5],
                    'status': row[6] if isinstance(row[6], str) else (
                        row[6].value if hasattr(row[6], 'value') else str(row[6])),
                    'phone': row[7],
                    'table_number': row[8] if row[8] else 'не назначен',
                    'restaurant_name': row[9] if row[9] else 'Бар'
                })

            return bookings

    async def get_ending_bookings(self, minutes_ahead: int = 30) -> List[Dict]:
        """Получить бронирования, которые скоро закончатся"""
        async with self.SessionLocal() as session:
            now = datetime.now(timezone.utc)
            target_time = now + timedelta(minutes=minutes_ahead)
            
            # Конвертируем в naive datetime для сравнения с timestamp without timezone в БД
            now_naive = now.replace(tzinfo=None)
            target_time_naive = target_time.replace(tzinfo=None)

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
                        b.children,
                        b.status
                    FROM bookings b
                    LEFT JOIN restaurants r ON b.restaurant_id = r.id
                    LEFT JOIN tables t ON b.table_id = t.id
                    WHERE b.status IN ('assigned', 'arrived', 'confirmed')
                      AND b.end_datetime IS NOT NULL
                      AND b.end_datetime >= :now
                      AND b.end_datetime <= :target_time
                    ORDER BY b.end_datetime
                """),
                {
                    "now": now_naive,
                    "target_time": target_time_naive
                }
            )
            rows = result.all()

            bookings = []
            for row in rows:
                start_dt = row[2]  # start_datetime
                end_dt = row[3]  # end_datetime

                bookings.append({
                    'id': row[0],
                    'restaurant_name': row[1],
                    'start_datetime': start_dt.isoformat() if start_dt else None,
                    'end_datetime': end_dt.isoformat() if end_dt else None,
                    'date': start_dt.date().isoformat() if start_dt else None,
                    'time': start_dt.time().strftime("%H:%M") if start_dt else None,
                    'name': row[4],
                    'phone': row[5],
                    'table_number': row[6],
                    'adults': row[7],
                    'children': row[8],
                    'status': row[9] if isinstance(row[9], str) else (
                        row[9].value if hasattr(row[9], 'value') else str(row[9])),
                })

            return bookings

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
                start_dt = row[1]  # start_datetime
                end_dt = row[2]  # end_datetime

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

    async def close(self):
        """Закрыть подключение"""
        await self.engine.dispose()
        logger.info("Database connection closed")