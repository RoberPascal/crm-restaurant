# app/db/models/slot.py
from typing import List
from sqlalchemy import Column, Integer, String, Date, Time, ForeignKey, Enum, Boolean, DateTime, JSON, Index, UniqueConstraint, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from app.db.base import Base
from app.db.models.enums import SlotStatus
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

class TimeSlot(Base):
    __tablename__ = "time_slots"
    
    id = Column(Integer, primary_key=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), index=True, nullable=False)
    date = Column(Date, index=True, nullable=False)
    time = Column(Time, index=True, nullable=False)
    
    # Используем SlotStatus из общего файла
    status = Column(Enum(SlotStatus), default=SlotStatus.AVAILABLE, index=True, nullable=False)
    
    # Связь с конкретными столами
    table_ids = Column(JSON, nullable=False, default=list)  # Все доступные столы
    locked_tables = Column(JSON, default=list)  # Заблокированные столы
    booked_tables = Column(JSON, default=list)  # Забронированные столы

    locked_count = Column(Integer, default=0)
    lock_value = Column(String(100), nullable=True)
    
    # Блокировки
    lock_token = Column(String(100), nullable=True)
    lock_expires_at = Column(DateTime, nullable=True)
    
    # Статистика
    available_table_count = Column(Integer, default=0)
    total_table_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    restaurant = relationship("Restaurant", back_populates="time_slots")

    # Индексы для оптимизации
    __table_args__ = (
        Index('ix_time_slots_restaurant_date_time', 'restaurant_id', 'date', 'time'),
        Index('ix_time_slots_date_status', 'date', 'status'),
        Index('ix_time_slots_lock_expires', 'lock_expires_at'),
        UniqueConstraint('restaurant_id', 'date', 'time', name='uq_slot_restaurant_datetime'),
    )

    @hybrid_property
    def is_available(self) -> bool:
        """Проверка доступности слота"""
        return (self.available_table_count > self.locked_count and 
                self.status == SlotStatus.AVAILABLE)

    @hybrid_property
    def available_tables_count(self) -> int:
        """Количество доступных столов"""
        return max(0, self.available_table_count - self.locked_count)

    @hybrid_property
    def is_locked(self) -> bool:
        """Проверка, заблокирован ли слот"""
        return self.status == SlotStatus.LOCKED

    @hybrid_property
    def is_booked(self) -> bool:
        """Проверка, забронирован ли слот"""
        return self.status == SlotStatus.BOOKED

    @hybrid_property
    def is_expired(self) -> bool:
        """Проверка, истекла ли блокировка"""
        if not self.lock_expires_at:
            return False
        return datetime.utcnow() > self.lock_expires_at

    def get_available_table_ids(self) -> List[int]:
        """Получение ID доступных столов"""
        try:
            all_tables = set(self.table_ids or [])
            locked_tables = set(self.locked_tables or [])
            booked_tables = set(self.booked_tables or [])
            
            available_tables = all_tables - locked_tables - booked_tables
            return list(available_tables)
        except Exception as e:
            logger.error("Error getting available table IDs", slot_id=self.id, error=str(e))
            return []

    def update_table_counts(self):
        """Обновление счетчиков столов"""
        try:
            self.total_table_count = len(self.table_ids or [])
            available_ids = self.get_available_table_ids()
            self.available_table_count = len(available_ids)
        except Exception as e:
            logger.error("Error updating table counts", slot_id=self.id, error=str(e))

    def __repr__(self):
        return f"<TimeSlot(id={self.id}, restaurant={self.restaurant_id}, date={self.date}, time={self.time}, status={self.status})>"