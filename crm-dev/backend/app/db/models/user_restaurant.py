# app/db/models/user_restaurant.py
from sqlalchemy import Column, Integer, ForeignKey, Table, DateTime, func, Index
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

# Ассоциативная таблица для связи многие-ко-многим между пользователями и ресторанами
user_restaurant = Table(
    'user_restaurant',
    Base.metadata,
    Column('user_id', 
           Integer, 
           ForeignKey('users.id', ondelete='CASCADE', onupdate='CASCADE'), 
           primary_key=True, 
           nullable=False,
           comment='ID пользователя'
    ),
    Column('restaurant_id', 
           Integer, 
           ForeignKey('restaurants.id', ondelete='CASCADE', onupdate='CASCADE'), 
           primary_key=True, 
           nullable=False,
           comment='ID ресторана'
    ),
    Column('created_at', 
           DateTime, 
           server_default=func.now(), 
           nullable=False,
           comment='Дата создания связи'
    ),
    Column('updated_at', 
           DateTime, 
           server_default=func.now(), 
           onupdate=func.now(),
           nullable=False,
           comment='Дата последнего обновления'
    ),
    
    # Индексы для оптимизации запросов
    Index('ix_user_restaurant_user_id', 'user_id'),
    Index('ix_user_restaurant_restaurant_id', 'restaurant_id'),
    Index('ix_user_restaurant_created_at', 'created_at'),
    
    # Комментарий к таблице
    comment='Ассоциативная таблица для связи многие-ко-многим между пользователями и ресторанами'
)

# Дополнительные утилиты для работы со связями
class UserRestaurantManager:
    """Менеджер для работы со связями пользователей и ресторанов"""
    
    @staticmethod
    async def get_user_restaurants(db, user_id: int) -> list:
        """Получение ресторанов пользователя"""
        from sqlalchemy import select
        from app.db.models.user import User
        
        try:
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                return user.restaurants
            return []
            
        except Exception as e:
            logger.error("Error getting user restaurants", user_id=user_id, error=str(e))
            return []
    
    @staticmethod
    async def get_restaurant_users(db, restaurant_id: int) -> list:
        """Получение пользователей ресторана"""
        from sqlalchemy import select
        from app.db.models.restaurant import Restaurant
        
        try:
            result = await db.execute(
                select(Restaurant).where(Restaurant.id == restaurant_id)
            )
            restaurant = result.scalar_one_or_none()
            
            if restaurant:
                return restaurant.users
            return []
            
        except Exception as e:
            logger.error("Error getting restaurant users", restaurant_id=restaurant_id, error=str(e))
            return []
    
    @staticmethod
    async def add_user_to_restaurant(db, user_id: int, restaurant_id: int) -> bool:
        """Добавление пользователя к ресторану"""
        from sqlalchemy import insert
        
        try:
            # Проверяем, существует ли уже связь
            from sqlalchemy import select
            result = await db.execute(
                select(user_restaurant).where(
                    user_restaurant.c.user_id == user_id,
                    user_restaurant.c.restaurant_id == restaurant_id
                )
            )
            existing = result.first()
            
            if existing:
                logger.debug("User already has access to restaurant", user_id=user_id, restaurant_id=restaurant_id)
                return True
            
            # Создаем новую связь
            stmt = insert(user_restaurant).values(
                user_id=user_id,
                restaurant_id=restaurant_id
            )
            await db.execute(stmt)
            await db.commit()
            
            logger.info("User added to restaurant", user_id=user_id, restaurant_id=restaurant_id)
            return True
            
        except Exception as e:
            await db.rollback()
            logger.error("Error adding user to restaurant", 
                        user_id=user_id, 
                        restaurant_id=restaurant_id, 
                        error=str(e))
            return False
    
    @staticmethod
    async def remove_user_from_restaurant(db, user_id: int, restaurant_id: int) -> bool:
        """Удаление пользователя из ресторана"""
        from sqlalchemy import delete
        
        try:
            stmt = delete(user_restaurant).where(
                user_restaurant.c.user_id == user_id,
                user_restaurant.c.restaurant_id == restaurant_id
            )
            result = await db.execute(stmt)
            await db.commit()
            
            if result.rowcount > 0:
                logger.info("User removed from restaurant", user_id=user_id, restaurant_id=restaurant_id)
                return True
            else:
                logger.debug("User was not associated with restaurant", user_id=user_id, restaurant_id=restaurant_id)
                return False
                
        except Exception as e:
            await db.rollback()
            logger.error("Error removing user from restaurant", 
                        user_id=user_id, 
                        restaurant_id=restaurant_id, 
                        error=str(e))
            return False
    
    @staticmethod
    async def user_has_access(db, user_id: int, restaurant_id: int) -> bool:
        """Проверка доступа пользователя к ресторану"""
        from sqlalchemy import select
        from app.db.models.user import User
        
        try:
            # Проверяем, является ли пользователь администратором
            result = await db.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return False
            
            # Администраторы имеют доступ ко всем ресторанам
            if user.is_admin:
                return True
            
            # Проверяем связь в ассоциативной таблице
            result = await db.execute(
                select(user_restaurant).where(
                    user_restaurant.c.user_id == user_id,
                    user_restaurant.c.restaurant_id == restaurant_id
                )
            )
            return result.first() is not None
            
        except Exception as e:
            logger.error("Error checking user access", 
                        user_id=user_id, 
                        restaurant_id=restaurant_id, 
                        error=str(e))
            return False

# Глобальный экземпляр менеджера
user_restaurant_manager = UserRestaurantManager()

# Экспорт для использования в других модулях
__all__ = [
    'user_restaurant',
    'user_restaurant_manager',
    'UserRestaurantManager'
]