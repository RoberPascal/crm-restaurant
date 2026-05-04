# app/services/user_service.py
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.user_public import UserPublic
from sqlalchemy import select

async def get_or_create_user_public(db: AsyncSession, telegram_user_data: dict) -> UserPublic:
    telegram_id = telegram_user_data.get("id")
    if not telegram_id:
        raise ValueError("Telegram user ID is required")

    result = await db.execute(
        select(UserPublic).where(UserPublic.telegram_user_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        # Обновляем актуальные данные (на случай смены имени/юзернейма)
        user.username = telegram_user_data.get("username")
        user.first_name = telegram_user_data.get("first_name")
        user.last_name = telegram_user_data.get("last_name")
        user.updated_at = datetime.utcnow()
        await db.flush()
        return user

    # Создаём нового
    user = UserPublic(
        telegram_user_id=telegram_id,
        username=telegram_user_data.get("username"),
        first_name=telegram_user_data.get("first_name"),
        last_name=telegram_user_data.get("last_name"),
    )
    db.add(user)
    await db.flush()  # Получаем id
    return user