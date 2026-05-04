"""
Миграция: добавление поля delay_notified в таблицу bookings

Это поле отслеживает, сообщил ли гость об опоздании через публичное приложение
"""

from sqlalchemy import text


async def upgrade(db):
    """Добавить поле delay_notified"""
    await db.execute(text("""
        ALTER TABLE bookings 
        ADD COLUMN IF NOT EXISTS delay_notified BOOLEAN DEFAULT FALSE;
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_bookings_delay_notified 
        ON bookings(delay_notified) 
        WHERE delay_notified = TRUE;
    """))
    await db.commit()
    print("✅ Migration 003: Added delay_notified column to bookings table")


async def downgrade(db):
    """Удалить поле delay_notified"""
    await db.execute(text("""
        DROP INDEX IF EXISTS ix_bookings_delay_notified;
    """))
    await db.execute(text("""
        ALTER TABLE bookings 
        DROP COLUMN IF EXISTS delay_notified;
    """))
    await db.commit()
    print("✅ Migration 003: Removed delay_notified column from bookings table")
