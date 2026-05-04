# app/schemas/restaurant.py
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import time

class ScheduleItem(BaseModel):
    day: int = Field(..., ge=0, le=6)  # 0=Mon, 6=Sun
    open: str
    close: str

    @field_validator('open', 'close')
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            time.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Time must be in HH:MM format")

class RestaurantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=50)
    is_published: bool = True
    max_booking_days: int = Field(60, ge=1, le=90)
    slot_interval_minutes: int = Field(30, enum=[15, 30, 60])
    telegram_chat_id: Optional[str] = None
    last_booking_time: Optional[str] = Field(None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")

    @field_validator('last_booking_time')
    @classmethod
    def validate_last_booking_time(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            time.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("last_booking_time must be in HH:MM format")

class RestaurantCreate(RestaurantBase):
    strapi_id: Optional[int] = None
    schedule: List[ScheduleItem] = []

class RestaurantUpdate(RestaurantBase):
    pass

class RestaurantResponse(RestaurantBase):
    id: int
    strapi_id: Optional[int]
    schedule: List[ScheduleItem] = []

    # Переопределяем last_booking_time в Response схеме
    last_booking_time: Optional[str] = Field(None, pattern=r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$")

    class Config:
        from_attributes = True