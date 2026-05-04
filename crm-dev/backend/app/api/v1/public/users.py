# app/api/v1/public/users.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_async_db
from app.db.models.user_public import UserPublic
from app.schemas.user_public import UserPublicRead, UserPublicUpdate
from app.core.security import get_telegram_user_from_request
from datetime import datetime
from app.core.config import settings
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()

async def get_or_create_user_from_telegram(telegram_data: dict, db: AsyncSession) -> UserPublic:
    """Получить или создать пользователя из данных Telegram"""
    telegram_user_id = telegram_data.get("id")
    
    if not telegram_user_id:
        raise HTTPException(status_code=400, detail="Telegram user ID required")
    
    # Ищем существующего пользователя
    result = await db.execute(
        select(UserPublic).where(UserPublic.telegram_user_id == telegram_user_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        return user
    
    # Создаем нового пользователя
    user = UserPublic(
        telegram_user_id=telegram_user_id,
        username=telegram_data.get("username"),
        first_name=telegram_data.get("first_name"),
        last_name=telegram_data.get("last_name"),
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    logger.info("Created new user from Telegram", user_id=user.id, telegram_id=telegram_user_id)
    return user

@router.options("/me", include_in_schema=False)
async def options_me(request: Request):
    """
    Обработка CORS preflight для /api/v1/public/me
    """
    origin = request.headers.get("origin")
    response = Response(status_code=200)
    if origin in settings.safe_cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-WebApp-Source, X-Telegram-Init-Data"
    return response

@router.get("/me", response_model=UserPublicRead)
async def get_profile(request: Request, db: AsyncSession = Depends(get_async_db)):
    telegram_user = get_telegram_user_from_request(request)
    if not telegram_user or not telegram_user.get("id"):
        raise HTTPException(status_code=401, detail="Telegram user not authenticated")
    return await get_or_create_user_from_telegram(telegram_user, db)

@router.patch("/me", response_model=UserPublicRead)
async def update_profile(
    request: Request,
    update_data: UserPublicUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    telegram_user = get_telegram_user_from_request(request)
    if not telegram_user or not telegram_user.get("id"):
        raise HTTPException(status_code=401, detail="Telegram user not authenticated")
    telegram_user_id = telegram_user.get("id")

    result = await db.execute(
        select(UserPublic).where(UserPublic.telegram_user_id == telegram_user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ✅ Pydantic v2 совместимость
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if hasattr(user, field):
            setattr(user, field, value)

    user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return user