"""
Миграция: увеличение max_booking_days с 14 до 60 (2 месяца вперед)

Обновляет CHECK constraint и значение по умолчанию для всех ресторанов.
"""

from sqlalchemy import text


async def upgrade(db):
    """Увеличить max_booking_days до 60"""
    # Удаляем старый constraint
    await db.execute(text("""
        ALTER TABLE restaurants DROP CONSTRAINT IF EXISTS check_max_booking_days;
    """))
    # Создаём новый с лимитом 90
    await db.execute(text("""
        ALTER TABLE restaurants ADD CONSTRAINT check_max_booking_days 
        CHECK (max_booking_days >= 1 AND max_booking_days <= 90);
    """))
    # Обновляем существующие рестораны с дефолтным значением 14 на 60
    await db.execute(text("""
        UPDATE restaurants SET max_booking_days = 60 WHERE max_booking_days = 14;
    """))
    # Обновляем дефолт колонки
    await db.execute(text("""
        ALTER TABLE restaurants ALTER COLUMN max_booking_days SET DEFAULT 60;
    """))
    await db.commit()
    print("✅ Migration 005: Increased max_booking_days to 60 (2 months)")


async def downgrade(db):
    """Откатить max_booking_days обратно к 14"""
    await db.execute(text("""
        UPDATE restaurants SET max_booking_days = 14 WHERE max_booking_days = 60;
    """))
    await db.execute(text("""
        ALTER TABLE restaurants DROP CONSTRAINT IF EXISTS check_max_booking_days;
    """))
    await db.execute(text("""
        ALTER TABLE restaurants ADD CONSTRAINT check_max_booking_days 
        CHECK (max_booking_days >= 1 AND max_booking_days <= 30);
    """))
    await db.execute(text("""
        ALTER TABLE restaurants ALTER COLUMN max_booking_days SET DEFAULT 14;
    """))
    await db.commit()
    print("✅ Migration 005 downgrade: Reverted max_booking_days to 14")
