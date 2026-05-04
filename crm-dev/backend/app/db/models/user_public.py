# app/db/models/user_public.py
from sqlalchemy import Column, Integer, BigInteger, String, Date, Text, Boolean, DateTime, Index
from sqlalchemy.orm import relationship
from app.db.base import Base
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

class UserPublic(Base):
    __tablename__ = "user_public"

    id = Column(Integer, primary_key=True, index=True)
    telegram_user_id = Column(BigInteger, unique=True, index=True)
    username = Column(String(32), nullable=True, index=True)
    first_name = Column(String(64), nullable=True)
    last_name = Column(String(64), nullable=True)
    phone = Column(String(20), nullable=True, index=True)
    email = Column(String(100), nullable=True, index=True)
    birth_date = Column(Date, nullable=True)
    allergies = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Используем back_populates для явного указания связи
    bookings = relationship("Booking", back_populates="user_public")

    # Индексы для оптимизации
    __table_args__ = (
        Index('ix_user_public_phone_active', 'phone', 'is_active'),
        Index('ix_user_public_created_active', 'created_at', 'is_active'),
    )

    @property
    def full_name(self) -> str:
        """Полное имя пользователя"""
        parts = []
        if self.first_name:
            parts.append(self.first_name)
        if self.last_name:
            parts.append(self.last_name)
        return " ".join(parts) if parts else "Анонимный пользователь"

    @property
    def display_name(self) -> str:
        """Отображаемое имя (username или полное имя)"""
        if self.username:
            return f"@{self.username}"
        return self.full_name

    @property
    def age(self) -> int:
        """Возраст пользователя"""
        if not self.birth_date:
            return 0
        
        from datetime import date
        today = date.today()
        age = today.year - self.birth_date.year
        
        # Проверяем, был ли уже день рождения в этом году
        if today.month < self.birth_date.month or (today.month == self.birth_date.month and today.day < self.birth_date.day):
            age -= 1
            
        return age

    def __repr__(self):
        return f"<UserPublic(id={self.id}, telegram_id={self.telegram_user_id}, username='{self.username}')>"