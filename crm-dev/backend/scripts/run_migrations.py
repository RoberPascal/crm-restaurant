#!/usr/bin/env python3
"""
Скрипт для запуска миграций базы данных
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import async_session_maker
from app.db.migrations import (
    migration_001_add_end_time_to_bookings,
    migration_002_add_booking_management_fields,
    migration_003_add_delay_notified_to_bookings,
    migration_004_add_booking_history_table,
)


async def run_migrations():
    """Запуск всех миграций"""
    migrations = [
        ("001_add_end_time_to_bookings", migration_001_add_end_time_to_bookings),
        ("002_add_booking_management_fields", migration_002_add_booking_management_fields),
        ("003_add_delay_notified_to_bookings", migration_003_add_delay_notified_to_bookings),
        ("004_add_booking_history_table", migration_004_add_booking_history_table),
    ]
    
    async with async_session_maker() as db:
        print("🔄 Starting database migrations...")
        print("=" * 60)
        
        for name, migration_module in migrations:
            try:
                print(f"\n📦 Running migration: {name}")
                await migration_module.upgrade(db)
                print(f"✅ Migration {name} completed successfully")
            except Exception as e:
                print(f"❌ Migration {name} failed: {e}")
                raise
        
        print("\n" + "=" * 60)
        print("✅ All migrations completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_migrations())
