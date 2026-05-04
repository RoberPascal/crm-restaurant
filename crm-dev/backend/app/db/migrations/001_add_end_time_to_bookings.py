"""
Миграция: Добавить поле end_time в таблицу bookings

Описание:
- Добавляет поле end_time (Time) для хранения времени окончания бронирования
- Поле опциональное (nullable=True) для обратной совместимости с существующими бронями
- Используется для расчета длительности бронирования и управления freeze/buffer логикой

Дата: 2024-11-13
"""

from sqlalchemy import Column, Time, text
from app.db.base import Base
from app.db.models.booking import Booking

def apply_migration(engine):
    """
    Применить миграцию (добавить столбец end_time к bookings)
    
    Если использовать Alembic:
    alembic revision --autogenerate -m "Add end_time to bookings"
    alembic upgrade head
    
    Для ручного применения в SQLite/PostgreSQL:
    ALTER TABLE bookings ADD COLUMN end_time TIME NULL;
    """
    pass


# Raw SQL для разных БД:

MIGRATIONS = {
    "postgresql": """
        ALTER TABLE bookings ADD COLUMN end_time TIME NULL;
        CREATE INDEX idx_bookings_end_time ON bookings(end_time);
    """,
    "sqlite": """
        ALTER TABLE bookings ADD COLUMN end_time TIME NULL;
        CREATE INDEX idx_bookings_end_time ON bookings(end_time);
    """,
    "mysql": """
        ALTER TABLE bookings ADD COLUMN end_time TIME NULL;
        CREATE INDEX idx_bookings_end_time ON bookings(end_time);
    """,
}

# Примеры использования нового поля:

EXAMPLES = """
-- Пример 1: Добавить end_time к существующей брони
UPDATE bookings 
SET end_time = TIME(datetime(time, '+2 hours'))  -- SQLite
WHERE end_time IS NULL AND date = CURRENT_DATE;

-- Пример 2: Найти активные брони
SELECT id, date, time, end_time, 
       CAST((julianday(end_time) - julianday(time)) * 24 AS INTEGER) as duration_hours
FROM bookings 
WHERE status = 'confirmed' 
  AND date = CURRENT_DATE
  AND time <= CURRENT_TIME
  AND end_time >= CURRENT_TIME;

-- Пример 3: Проверить фриз (2 часа)
SELECT * FROM bookings 
WHERE status = 'confirmed'
  AND ((julianday(end_time) - julianday(time)) * 24 * 60) < 120;  -- Все брони < 2 часов
"""
