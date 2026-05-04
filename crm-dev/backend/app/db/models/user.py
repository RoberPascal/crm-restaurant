# app/db/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, Enum, CheckConstraint, DateTime, func, Index
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.core.security import hash_password, verify_password
from app.db.models.enums import StatusEnum
from enum import StrEnum
import structlog

logger = structlog.get_logger(__name__)

class RoleEnum(StrEnum):
    admin = "admin"
    operator = "operator"
    waiter = "waiter"

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(username) >= 3", name="check_username_length"),
        Index('ix_users_username_active', 'username', 'is_active'),
        Index('ix_users_role_active', 'role', 'is_active'),
        Index('ix_users_created_at', 'created_at'),
    )

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.operator, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Связь с ресторанами
    restaurants = relationship(
        "Restaurant",
        secondary="user_restaurant",
        back_populates="users",
        lazy="selectin"
    )

    # Связь с бронированиями, которые пользователь продлил
    extended_bookings = relationship(
        "Booking", 
        foreign_keys="Booking.extended_by_user_id",
        back_populates="extended_by_user"
    )

    @property
    def is_admin(self) -> bool:
        """Проверка, является ли пользователь администратором"""
        return self.role == RoleEnum.admin

    @property
    def is_operator(self) -> bool:
        """Проверка, является ли пользователь оператором"""
        return self.role == RoleEnum.operator

    @property
    def is_waiter(self) -> bool:
        """Проверка, является ли пользователь официантом"""
        return self.role == RoleEnum.waiter

    def verify_password(self, plain_password: str) -> bool:
        """Проверка пароля с улучшенной безопасностью."""
        try:
            if not plain_password or not self.hashed_password:
                logger.warning("Empty password or hash during verification", username=self.username)
                return False
            
            result = verify_password(plain_password, self.hashed_password)
            logger.debug("Password verification completed", username=self.username, success=result)
            return result
        except Exception as e:
            logger.error("Password verification error", username=self.username, error=str(e))
            return False

    @classmethod
    def hash_password(cls, plain_password: str) -> str:
        """Хэширование пароля с использованием улучшенной безопасности."""
        try:
            if not plain_password:
                raise ValueError("Password cannot be empty")
            
            hashed = hash_password(plain_password)
            logger.debug("Password hashed successfully", hash_length=len(hashed))
            return hashed
        except Exception as e:
            logger.error("Password hashing error", error=str(e))
            raise

    def can_manage_restaurant(self, restaurant_id: int) -> bool:
        """Может ли пользователь управлять указанным рестораном"""
        if self.is_admin:
            return True
        
        if not self.restaurants:
            return False
            
        return any(restaurant.id == restaurant_id for restaurant in self.restaurants)

    def get_manageable_restaurant_ids(self) -> list[int]:
        """Получение ID ресторанов, которыми может управлять пользователь"""
        if self.is_admin:
            # Админы могут управлять всеми ресторанами
            # В реальной реализации нужно получить все ID из БД
            return []
        
        return [restaurant.id for restaurant in self.restaurants]

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}', active={self.is_active})>"