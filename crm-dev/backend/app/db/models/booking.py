# app/db/models/booking.py
from sqlalchemy import Column, Integer, String, DateTime, Date, Time, ForeignKey, Enum, Boolean, Text, JSON, Index
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.db.models.enums import StatusEnum
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False)
    adults = Column(Integer, nullable=False, default=1)
    children = Column(Integer, default=0)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    wishes = Column(Text)
    status = Column(Enum(StatusEnum), default=StatusEnum.pending, index=True)
    table_id = Column(Integer, ForeignKey("tables.id", ondelete="SET NULL"), nullable=True)
    has_time_limit = Column(Boolean, default=False)
    time_limit_hours = Column(Integer)
    idempotency_key = Column(String(36), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    suitable_tables_json = Column(JSON, nullable=True)
    extended_until = Column(DateTime, nullable=True)
    extended_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cleaning_started_at = Column(DateTime, nullable=True)
    user_public_id = Column(Integer, ForeignKey("user_public.id", ondelete="SET NULL"), nullable=True)
    start_datetime = Column(DateTime, nullable=False, index=True)   # 2025-11-26 20:00:00
    end_datetime   = Column(DateTime, nullable=True, index=True)    # NULL = "до закрытия"
    delay_notified = Column(Boolean, default=False, nullable=False) # Гость сообщил об опоздании
    
    # Relationships
    restaurant = relationship("Restaurant", back_populates="bookings")
    table = relationship("Table", back_populates="bookings")
    extended_by_user = relationship("User", foreign_keys=[extended_by_user_id])
    user_public = relationship("UserPublic", back_populates="bookings")

    # Индексы для оптимизации запросов
    __table_args__ = (
        Index('ix_bookings_restaurant_start', 'restaurant_id', 'start_datetime'),
        Index('ix_bookings_start_datetime', 'start_datetime'),
        Index('ix_bookings_phone_status', 'phone', 'status'),
        Index('ix_bookings_status', 'status'),
    )

    @property
    def table_number(self):
        """Номер стола из связанной таблицы (для Pydantic from_attributes)"""
        try:
            return self.table.number if self.table else None
        except Exception:
            return None

    @property
    def table_location(self):
        """Расположение стола из связанной таблицы"""
        try:
            return self.table.location_mark if self.table else None
        except Exception:
            return None

    @property
    def total_guests(self) -> int:
        """Общее количество гостей"""
        return self.adults + self.children

    @property
    def is_active(self) -> bool:
        """Проверка, является ли бронирование активным"""
        active_statuses = {
            StatusEnum.pending,
            StatusEnum.pending_review, 
            StatusEnum.confirmed,
            StatusEnum.assigned,
            StatusEnum.arrived
        }
        return self.status in active_statuses

    @property
    def is_completed(self) -> bool:
        """Проверка, завершено ли бронирование"""
        completed_statuses = {
            StatusEnum.completed,
            StatusEnum.no_show,
            StatusEnum.cancelled
        }
        return self.status in completed_statuses

    def __repr__(self):
        return (
            f"<Booking(id={self.id}, "
            f"restaurant={self.restaurant_id}, "
            f"start={self.start_datetime}, "
            f"end={'closed' if self.end_datetime is None else self.end_datetime}, "
            f"status={self.status})>"
        )