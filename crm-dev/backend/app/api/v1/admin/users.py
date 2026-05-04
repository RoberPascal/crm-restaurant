# app/api/v1/admin/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy import select
from app.db.session import get_async_db
from app.db.models.user import User, RoleEnum
from app.db.models.restaurant import Restaurant
from app.schemas.restaurant import RestaurantResponse
from app.schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserWithRestaurants
)
from app.core.security import hash_password, sanitize_input, validate_csrf_dependency
from .deps import get_current_user_from_cookie, require_admin_role
import secrets
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter()

@router.get("/users", response_model=list[UserWithRestaurants])
async def get_users(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role)
):
    """Получить всех пользователей с ресторанами"""
    result = await db.execute(select(User).options(joinedload(User.restaurants)))
    users = result.unique().scalars().all()
    return [
        UserWithRestaurants(
            id=u.id,
            username=u.username,
            role=u.role,
            is_active=u.is_active,
            restaurants=u.restaurants,
        )
        for u in users
    ]

@router.get("/user/restaurants", response_model=list[RestaurantResponse])
async def get_user_restaurants(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Получить рестораны текущего пользователя"""
    logger.info(
        "Fetching user restaurants", 
        user_id=current_user.id,
        user_role=current_user.role.value
    )
    
    # Для администраторов возвращаем ВСЕ рестораны
    if current_user.role == RoleEnum.admin:
        logger.info("Admin user - returning all restaurants")
        result = await db.execute(select(Restaurant).where(Restaurant.is_published.is_(True)))
        restaurants = result.scalars().all()
    else:
        # Для остальных пользователей возвращаем только их рестораны
        # Перезагружаем пользователя с ресторанами в текущей сессии
        result = await db.execute(
            select(User).options(joinedload(User.restaurants)).where(User.id == current_user.id)
        )
        fresh_user = result.unique().scalar_one_or_none()
        restaurants = fresh_user.restaurants if fresh_user else []
    
    logger.info(
        "Restaurants to return", 
        count=len(restaurants),
        restaurant_names=[r.name for r in restaurants]
    )
    
    return restaurants

def generate_memorable_password():
    """
    Генерация простого запоминающегося пароля.
    Формат: Слово + Число + Слово (например: Red42Apple)
    """
    words = [
        "Sun", "Moon", "Star", "Sky", "Cloud", "Rain", "Snow", "Wind",
        "Fire", "Water", "Earth", "Tree", "Flower", "River", "Mountain",
        "Ocean", "Forest", "Desert", "Valley", "Island", "Beach", "Lake",
        "Red", "Blue", "Green", "Gold", "Silver", "Black", "White", "Yellow",
        "Apple", "Berry", "Lemon", "Orange", "Peach", "Grape", "Pear", "Plum",
        "Lion", "Tiger", "Eagle", "Shark", "Whale", "Bear", "Wolf", "Fox",
        "Happy", "Brave", "Calm", "Swift", "Smart", "Wise", "Bold", "Kind"
    ]
    
    word1 = secrets.choice(words)
    word2 = secrets.choice(words)
    number = secrets.randbelow(90) + 10
    
    return f"{word1}{number}{word2}"

@router.post("/users", response_model=UserWithRestaurants, dependencies=[Depends(validate_csrf_dependency)])
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role)
):
    """Создать пользователя с доступом к ресторанам"""
    # Санитизация username
    sanitized_username = sanitize_input(user_data.username)
    
    existing = await db.execute(select(User).where(User.username == sanitized_username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Логин уже занят")

    # Генерируем пароль на СЕРВЕРЕ
    password = generate_memorable_password()
    
    logger.info(
        "Creating user with server-generated password",
        username=sanitized_username,
        by_user_id=current_user.id
    )
    
    user = User(
        username=sanitized_username,
        hashed_password=hash_password(password),
        role=user_data.role,
        is_active=True
    )

    if user_data.restaurant_ids:
        result = await db.execute(select(Restaurant).where(Restaurant.id.in_(user_data.restaurant_ids)))
        restaurants = result.scalars().all()
        user.restaurants = list(restaurants)

    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("User created", user_id=user.id, by=current_user.id)

    return UserWithRestaurants(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        restaurants=user.restaurants,
        password=password
    )

@router.put("/users/{user_id}", response_model=UserWithRestaurants, dependencies=[Depends(validate_csrf_dependency)])
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Санитизация username
    sanitized_username = sanitize_input(user_data.username)
    
    if sanitized_username != user.username:
        existing = await db.execute(select(User).where(User.username == sanitized_username))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Логин уже занят")

    user.username = sanitized_username
    user.role = user_data.role
    user.is_active = user_data.is_active if user_data.is_active is not None else user.is_active

    if user_data.restaurant_ids is not None:
        result = await db.execute(select(Restaurant).where(Restaurant.id.in_(user_data.restaurant_ids)))
        restaurants = result.scalars().all()
        user.restaurants = list(restaurants)

    await db.commit()
    await db.refresh(user)

    logger.info("User updated", user_id=user.id, by=current_user.id)
    return UserWithRestaurants(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        restaurants=user.restaurants,
    )

@router.post("/users/{user_id}/reset-password", dependencies=[Depends(validate_csrf_dependency)])
async def reset_user_password(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role)
):
    """Сбросить пароль пользователя - генерирует новый простой пароль"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Генерируем новый простой пароль
    new_password = generate_memorable_password()
    user.hashed_password = hash_password(new_password)
    await db.commit()

    logger.info(
        "Password reset", 
        user_id=user.id, 
        by=current_user.id
    )
    
    return {
        "detail": "Пароль сброшен", 
        "new_password": new_password,
        "username": user.username
    }

@router.patch("/users/{user_id}/change-password", dependencies=[Depends(validate_csrf_dependency)])
async def change_user_password(
    user_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role)
):
    """Ручное изменение пароля (только для админов)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    new_password = payload.get("new_password")
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Пароль должен быть ≥6 символов")

    user.hashed_password = hash_password(new_password)
    await db.commit()

    logger.info("Password changed manually", user_id=user.id, by=current_user.id)
    return {"detail": "Пароль изменён"}

@router.delete("/users/{user_id}", dependencies=[Depends(validate_csrf_dependency)])
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin_role)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить себя")

    await db.delete(user)
    await db.commit()
    logger.info("User deleted", user_id=user_id, by=current_user.id)
    return {"detail": "Пользователь удалён"}