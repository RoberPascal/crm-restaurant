"""
Migration 004: Add booking_history table for audit trail
Tracks all status changes with timestamp, user, and reason
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["upgrade", "downgrade"]


async def upgrade(db: AsyncSession):
    """Create booking_history table and index"""
    
    # Create booking_history table
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS booking_history (
            id SERIAL PRIMARY KEY,
            booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
            old_status VARCHAR(50) NOT NULL,
            new_status VARCHAR(50) NOT NULL,
            changed_by_user_id INTEGER,
            reason TEXT,
            changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'Europe/Moscow'),
            CONSTRAINT fk_booking_history_booking FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
        )
    """))
    
    # Create index for efficient querying by booking_id
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_booking_history_booking_id 
        ON booking_history(booking_id)
    """))
    
    # Create index for querying by timestamp
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_booking_history_changed_at 
        ON booking_history(changed_at DESC)
    """))
    
    await db.commit()
    print("✅ Migration 004: booking_history table created successfully")


async def downgrade(db: AsyncSession):
    """Drop booking_history table and indexes"""
    
    await db.execute(text("DROP INDEX IF EXISTS idx_booking_history_changed_at"))
    await db.execute(text("DROP INDEX IF EXISTS idx_booking_history_booking_id"))
    await db.execute(text("DROP TABLE IF EXISTS booking_history"))
    
    await db.commit()
    print("✅ Migration 004 downgrade: booking_history table dropped")
