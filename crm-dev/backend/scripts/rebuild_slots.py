import sys
import asyncio
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.session import SyncScriptSessionLocal, AsyncSessionLocal
from app.db.models.restaurant import Restaurant
from app.services.slot_state_manager import SlotStateManager
from app.services.slot_generator import invalidate_slots_cache
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

async def do_rebuild(restaurant_id: int, target_date):
    async with AsyncSessionLocal() as async_db:
        try:
            await SlotStateManager.initialize_daily_slots(restaurant_id, target_date, async_db)
            await async_db.commit()
            await invalidate_slots_cache(restaurant_id, target_date)
            await SlotStateManager._publish_slot_update(restaurant_id, target_date)
            print(f"Slots rebuilt for restaurant_id={restaurant_id} date={target_date}")
        except Exception as e:
            print("Error rebuilding slots:", e)

def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/rebuild_slots.py <restaurant_slug> <YYYY-MM-DD>")
        sys.exit(1)

    slug = sys.argv[1]
    date_str = sys.argv[2]
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        print("Invalid date format. Expected YYYY-MM-DD")
        sys.exit(1)

    db = SyncScriptSessionLocal()
    try:
        from sqlalchemy import text
        res = db.execute(text("select id from restaurants where slug = :slug"), {"slug": slug})
        row = res.fetchone()
        if not row:
            print("Restaurant not found for slug:", slug)
            sys.exit(1)
        restaurant_id = row[0]
    finally:
        db.close()

    asyncio.run(do_rebuild(restaurant_id, target_date))

if __name__ == '__main__':
    main()
