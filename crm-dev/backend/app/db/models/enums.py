# app/db/models/enums.py
import enum
from typing import List, Dict, Any

class CapacityEnum(enum.Enum):
    """Емкость столов"""
    solo = "solo"
    small = "small" 
    medium = "medium"
    large = "large"
    extra_large = "extra_large"

    @classmethod
    def get_seats_range(cls, capacity: 'CapacityEnum') -> tuple:
        """Получение диапазона мест для емкости"""
        ranges = {
            cls.solo: (1, 2),
            cls.small: (2, 4),
            cls.medium: (4, 6),
            cls.large: (6, 8),
            cls.extra_large: (8, 20),
        }
        return ranges.get(capacity, (1, 4))

    @classmethod
    def from_seats_count(cls, seats: int) -> 'CapacityEnum':
        """Определение емкости по количеству мест"""
        if seats <= 2:
            return cls.solo
        elif seats <= 4:
            return cls.small
        elif seats <= 6:
            return cls.medium
        elif seats <= 8:
            return cls.large
        else:
            return cls.extra_large


class StatusEnum(enum.Enum):
    """Статусы бронирований"""
    pending = "pending"
    pending_review = "pending_review"
    confirmed = "confirmed"
    assigned = "assigned"
    arrived = "arrived"
    completed = "completed"
    no_show = "no_show"
    cancelled = "cancelled"

    @classmethod
    def get_active_statuses(cls) -> List['StatusEnum']:
        """Получение активных статусов"""
        return [
            cls.pending,
            cls.pending_review,
            cls.confirmed,
            cls.assigned,
            cls.arrived
        ]

    @classmethod
    def get_completed_statuses(cls) -> List['StatusEnum']:
        """Получение завершенных статусов"""
        return [
            cls.completed,
            cls.no_show,
            cls.cancelled
        ]

    @classmethod
    def can_transition_to(cls, from_status: 'StatusEnum', to_status: 'StatusEnum') -> bool:
        """Проверка возможности перехода между статусами"""
        if from_status == to_status:
            return True
            
        transitions: Dict[StatusEnum, List[StatusEnum]] = {
            cls.pending: [cls.pending_review, cls.confirmed, cls.assigned, cls.cancelled],
            cls.pending_review: [cls.confirmed, cls.cancelled],
            cls.confirmed: [cls.assigned, cls.arrived, cls.no_show, cls.cancelled],
            cls.assigned: [cls.arrived, cls.no_show, cls.cancelled, cls.completed],
            cls.arrived: [cls.completed, cls.no_show],
            cls.completed: [],
            cls.no_show: [],
            cls.cancelled: [],
        }
        return to_status in transitions.get(from_status, [])


class SlotStatus(enum.Enum):
    """Статусы слотов времени"""
    AVAILABLE = "available"
    LOCKED = "locked"
    BOOKED = "booked"
    UNAVAILABLE = "unavailable"

    @classmethod
    def is_available(cls, status: 'SlotStatus') -> bool:
        """Проверка, доступен ли слот"""
        return status == cls.AVAILABLE

    @classmethod
    def is_booked(cls, status: 'SlotStatus') -> bool:
        """Проверка, забронирован ли слот"""
        return status == cls.BOOKED

    @classmethod
    def can_book(cls, status: 'SlotStatus') -> bool:
        """Можно ли забронировать слот"""
        return status in [cls.AVAILABLE, cls.LOCKED]