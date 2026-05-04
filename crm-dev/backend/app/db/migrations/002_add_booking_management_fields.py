"""
Миграция: Добавить поля для управления временем бронирования

Описание:
- extended_until: DateTime - когда администратор продлил бронь
- extended_by_user_id: Integer FK(users.id) - кто продлил время
- cleaning_started_at: DateTime - когда началась уборка
- reservation_end_time: DateTime - точное время окончания резервации (с буфером)

ПРАВИЛА ТЗ (2 часа + 15 мин буфера):
1. Стол занят на 2 часа минимум
2. Плюс 15 минут на уборку после конца брони
3. ПЕРЕД временем начала также резервируется 2 часа 15 минут

Дата: 2024-11-13
"""

from sqlalchemy import Column, DateTime, Integer, ForeignKey, text
from app.db.base import Base

def apply_migration(engine):
    """
    Применить миграцию
    
    Использование с Alembic:
    alembic revision --autogenerate -m "Add booking management fields"
    alembic upgrade head
    """
    pass


# Raw SQL для разных БД:

MIGRATIONS = {
    "postgresql": """
        -- Добавляем поля для управления временем бронирования
        ALTER TABLE bookings ADD COLUMN extended_until TIMESTAMP NULL;
        ALTER TABLE bookings ADD COLUMN extended_by_user_id INTEGER REFERENCES users(id) NULL;
        ALTER TABLE bookings ADD COLUMN cleaning_started_at TIMESTAMP NULL;
        ALTER TABLE bookings ADD COLUMN reservation_end_time TIMESTAMP NULL;
        
        -- Индексы для оптимизации запросов
        CREATE INDEX idx_bookings_extended_until ON bookings(extended_until);
        CREATE INDEX idx_bookings_cleaning_started_at ON bookings(cleaning_started_at);
        CREATE INDEX idx_bookings_reservation_end_time ON bookings(reservation_end_time);
        CREATE INDEX idx_bookings_extended_by_user_id ON bookings(extended_by_user_id);
    """,
    "sqlite": """
        ALTER TABLE bookings ADD COLUMN extended_until DATETIME NULL;
        ALTER TABLE bookings ADD COLUMN extended_by_user_id INTEGER REFERENCES users(id) NULL;
        ALTER TABLE bookings ADD COLUMN cleaning_started_at DATETIME NULL;
        ALTER TABLE bookings ADD COLUMN reservation_end_time DATETIME NULL;
        
        CREATE INDEX idx_bookings_extended_until ON bookings(extended_until);
        CREATE INDEX idx_bookings_cleaning_started_at ON bookings(cleaning_started_at);
        CREATE INDEX idx_bookings_reservation_end_time ON bookings(reservation_end_time);
        CREATE INDEX idx_bookings_extended_by_user_id ON bookings(extended_by_user_id);
    """,
    "mysql": """
        ALTER TABLE bookings ADD COLUMN extended_until DATETIME NULL;
        ALTER TABLE bookings ADD COLUMN extended_by_user_id INT REFERENCES users(id) NULL;
        ALTER TABLE bookings ADD COLUMN cleaning_started_at DATETIME NULL;
        ALTER TABLE bookings ADD COLUMN reservation_end_time DATETIME NULL;
        
        CREATE INDEX idx_bookings_extended_until ON bookings(extended_until);
        CREATE INDEX idx_bookings_cleaning_started_at ON bookings(cleaning_started_at);
        CREATE INDEX idx_bookings_reservation_end_time ON bookings(reservation_end_time);
        CREATE INDEX idx_bookings_extended_by_user_id ON bookings(extended_by_user_id);
    """,
}

# Примеры использования:

EXAMPLES = """
-- Пример 1: Администратор продлевает бронь на 1 час
UPDATE bookings 
SET extended_until = NOW() + INTERVAL 1 HOUR,
    extended_by_user_id = 5,
    reservation_end_time = reservation_end_time + INTERVAL 1 HOUR
WHERE id = 123 AND status = 'assigned';

-- Пример 2: Начало уборки после завершения брони
UPDATE bookings 
SET cleaning_started_at = NOW()
WHERE id = 123 AND status = 'arrived';

-- Пример 3: Получить активные брони с их сроками
SELECT 
    id, 
    name, 
    time, 
    reservation_end_time,
    EXTRACT(EPOCH FROM (reservation_end_time - NOW())) / 60 AS minutes_until_end,
    extended_until,
    cleaning_started_at
FROM bookings
WHERE status IN ('assigned', 'arrived')
  AND reservation_end_time > NOW()
ORDER BY reservation_end_time ASC;
"""
