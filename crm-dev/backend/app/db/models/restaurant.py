# app/db/models/restaurant.py
from sqlalchemy import Column, Integer, String, Boolean, JSON, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.db.models.user_restaurant import user_restaurant
from typing import List, Dict, Any
import structlog

logger = structlog.get_logger(__name__)

class Restaurant(Base):
    __tablename__ = "restaurants"
    __table_args__ = (
        CheckConstraint("max_booking_days >= 1 AND max_booking_days <= 90", name="check_max_booking_days"),
        CheckConstraint("slot_interval_minutes IN (15, 30, 60)", name="check_slot_interval_minutes"),
        UniqueConstraint("slug", name="uq_restaurant_slug"),
        Index('ix_restaurants_slug_published', 'slug', 'is_published'),
        Index('ix_restaurants_published', 'is_published'),
    )

    id = Column(Integer, primary_key=True)
    strapi_id = Column(Integer, unique=True, index=True)
    slug = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_published = Column(Boolean, default=True, index=True)
    schedule = Column(JSON, nullable=False, default=lambda: [])
    max_booking_days = Column(Integer, default=60)
    slot_interval_minutes = Column(Integer, default=15)
    telegram_chat_id = Column(String(50), nullable=True)
    last_booking_time = Column(String(5), nullable=True, default="22:00")  # HH:MM format

    # Связь с пользователями
    users = relationship(
        "User",
        secondary="user_restaurant",
        back_populates="restaurants",
        lazy="selectin"
    )

    time_slots = relationship("TimeSlot", back_populates="restaurant", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="restaurant", cascade="all, delete-orphan")
    tables = relationship("Table", back_populates="restaurant", cascade="all, delete-orphan")

    @property
    def active_tables(self) -> List['Table']:
        """Получение активных столов ресторана"""
        return [table for table in self.tables if table.is_active]

    @property
    def table_count(self) -> int:
        """Количество активных столов"""
        return len(self.active_tables)

    @property
    def max_capacity(self) -> int:
        """Максимальная вместимость ресторана"""
        return sum(table.seats_max for table in self.active_tables)

    def is_open_on_date(self, date) -> bool:
        """Проверка, открыт ли ресторан в указанную дату"""
        try:
            from datetime import datetime
            day_of_week = date.weekday()  # 0=Пн, 6=Вс
            
            for schedule_item in self.schedule:
                if schedule_item.get('day') == day_of_week:
                    return True
            return False
        except Exception as e:
            logger.error("Error checking restaurant schedule", restaurant_id=self.id, error=str(e))
            return False

    def get_opening_hours(self, date) -> Dict[str, str]:
        """Получение часов работы на указанную дату"""
        try:
            day_of_week = date.weekday()
            
            for schedule_item in self.schedule:
                if schedule_item.get('day') == day_of_week:
                    return {
                        'open': schedule_item.get('open', '09:00'),
                        'close': schedule_item.get('close', '23:00')
                    }
            return {'open': '09:00', 'close': '23:00'}  # Default
        except Exception as e:
            logger.error("Error getting opening hours", restaurant_id=self.id, error=str(e))
            return {'open': '09:00', 'close': '23:00'}

    def __repr__(self):
        return f"<Restaurant(id={self.id}, slug='{self.slug}', name='{self.name}')>"