# app/api/v1/public/restaurant.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_async_db
from app.db.models.restaurant import Restaurant

# ←←← ПРЕФИКС ДОЛЖЕН БЫТЬ ПУСТЫМ, Т.К. ОН УКАЗАН ПРИ ПОДКЛЮЧЕНИИ ←←←
router = APIRouter()

@router.get("/{slug}/last-booking-time")
async def get_last_booking_time(
    slug: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Публичный эндпоинт: возвращает только last_booking_time для ресторана по slug
    """
    result = await db.execute(
        select(Restaurant.last_booking_time, Restaurant.is_published)
        .where(Restaurant.slug == slug)
    )
    row = result.first()

    if not row or not row.is_published:
        raise HTTPException(status_code=404, detail="Restaurant not found or not published")

    return {
        "last_booking_time": row.last_booking_time  # "18:00" или null
    }