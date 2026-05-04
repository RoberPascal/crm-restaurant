# app/db/models/table.py
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.db.models.enums import CapacityEnum
import structlog

logger = structlog.get_logger(__name__)

class Table(Base):
    __tablename__ = "tables"
    __table_args__ = (
        CheckConstraint("seats_min <= seats_max", name="check_seats"),
        CheckConstraint("seats_min >= 1", name="check_seats_min"),
        CheckConstraint("seats_max <= 50", name="check_seats_max"),
        UniqueConstraint("restaurant_id", "number", name="uq_table_number_per_restaurant"),
        Index('ix_tables_restaurant_active', 'restaurant_id', 'is_active'),
        Index('ix_tables_strapi_id', 'strapi_id'),
    )

    id = Column(Integer, primary_key=True)
    strapi_id = Column(Integer, unique=True, nullable=True, index=True)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id", ondelete="CASCADE"), index=True, nullable=False)
    number = Column(String(20), nullable=False)
    seats_min = Column(Integer, nullable=False, default=1)
    seats_max = Column(Integer, nullable=False, default=4)
    location_mark = Column(String(50), nullable=True)
    type = Column(Enum(CapacityEnum), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    bookings = relationship("Booking", back_populates="table")
    restaurant = relationship("Restaurant", back_populates="tables")

    @property
    def capacity_enum(self) -> CapacityEnum:
        """Получение емкости стола на основе количества мест"""
        return CapacityEnum.from_seats_count(self.seats_max)

    @property
    def is_available(self) -> bool:
        """Проверка, активен ли стол"""
        return self.is_active

    @property
    def display_name(self) -> str:
        """Отображаемое имя стола"""
        if self.location_mark:
            return f"Стол {self.number} ({self.location_mark})"
        return f"Стол {self.number}"

    def can_accommodate(self, guests_count: int) -> bool:
        """Может ли стол вместить указанное количество гостей"""
        return self.seats_min <= guests_count <= self.seats_max

    def get_capacity_display(self) -> str:
        """Отображение вместимости стола"""
        if self.seats_min == self.seats_max:
            return f"{self.seats_max} чел."
        return f"{self.seats_min}-{self.seats_max} чел."

    def __repr__(self):
        return f"<Table(id={self.id}, restaurant={self.restaurant_id}, number='{self.number}', seats={self.seats_min}-{self.seats_max})>"