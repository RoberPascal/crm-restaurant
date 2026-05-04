# app/schemas/booking.py
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import date, time, datetime
import phonenumbers
import json
import structlog
from app.db.models.enums import StatusEnum
from .user_public import UserPublicUpdate

logger = structlog.get_logger(__name__)


class BookingCreatePublic(BaseModel):
    restaurant_slug: str
    date: date
    time: time
    end_time: Optional[time] = None
    adults: int = Field(..., ge=1, le=20)
    children: int = Field(0, ge=0, le=20)
    name: str = Field(..., min_length=2, max_length=100)
    phone: str
    wishes: Optional[str] = None
    lock_value: Optional[str] = None
    idempotency_key: Optional[str] = None
    table_id: Optional[int] = None
    telegram_user: Optional[dict] = None
    profile_update: Optional[UserPublicUpdate] = None
    # lock_value дублировался, убираем лишний


    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            parsed = phonenumbers.parse(v, None)
        except phonenumbers.NumberParseException:
            raise ValueError("Неверный формат номера телефона")

        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Несуществующий номер телефона")
            
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class BookingSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            time: lambda v: v.strftime('%H:%M:%S')
        }
    )

    id: int
    restaurant_id: int
    start_datetime: datetime
    end_time: Optional[time] = None
    end_datetime: Optional[datetime] = None  # ДОБАВЛЕНО
    adults: int
    children: int
    name: str
    phone: str
    wishes: Optional[str] = None
    status: str
    table_id: Optional[int] = None
    table_number: Optional[str] = None
    has_time_limit: bool = False
    time_limit_hours: Optional[int] = Field(None, ge=1, le=12)
    idempotency_key: Optional[str] = None
    created_at: Optional[datetime] = None
    delay_notified: bool = False

    # Для совместимости с фронтом
    date: Optional[date] = None
    time: Optional[time] = None

    @model_validator(mode='after')
    def populate_date_time(self):
        if self.start_datetime:
            # Convert UTC datetime to Moscow time before extracting date/time
            from app.core.time_utils import to_moscow_time
            moscow_dt = to_moscow_time(self.start_datetime)
            self.date = moscow_dt.date()
            self.time = moscow_dt.time()
        if self.end_datetime:
            from app.core.time_utils import to_moscow_time
            moscow_end = to_moscow_time(self.end_datetime)
            self.end_time = moscow_end.time()
        return self


class BookingUpdate(BaseModel):
    status: Optional[StatusEnum] = None
    wishes: Optional[str] = None
    has_time_limit: Optional[bool] = None
    time_limit_hours: Optional[int] = Field(None, ge=1, le=6)


class BookingAssignTable(BaseModel):
    table_id: int


class BookingPublicResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            time: lambda v: v.strftime('%H:%M:%S')
        }
    )

    id: int
    restaurant_id: int
    restaurant_name: Optional[str] = None
    restaurant_slug: Optional[str] = None
    start_datetime: datetime
    end_time: Optional[time] = None
    end_datetime: Optional[datetime] = None  # ДОБАВЛЕНО
    adults: int
    children: int
    name: str
    phone: str
    wishes: Optional[str] = None
    status: str
    table_id: Optional[int] = None
    table_number: Optional[str] = None
    created_at: Optional[datetime] = None
    delay_notified: bool = False

    date: Optional[date] = None
    time: Optional[time] = None

    @model_validator(mode='after')
    def populate_date_time(self):
        if self.start_datetime:
            # Convert UTC datetime to Moscow time before extracting date/time
            from app.core.time_utils import to_moscow_time
            moscow_dt = to_moscow_time(self.start_datetime)
            self.date = moscow_dt.date()
            self.time = moscow_dt.time()
        if self.end_datetime:
            from app.core.time_utils import to_moscow_time
            moscow_end = to_moscow_time(self.end_datetime)
            self.end_time = moscow_end.time()
        return self

    @field_validator('status', mode='before')
    @classmethod
    def convert_enum(cls, v):
        return v.value if hasattr(v, 'value') else v


class AdminBookingSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            time: lambda v: v.strftime('%H:%M:%S')
        }
    )

    id: int
    restaurant_id: int
    start_datetime: datetime
    end_time: Optional[time] = None
    end_datetime: Optional[datetime] = None  # ДОБАВЛЕНО
    adults: int
    children: int
    name: str
    phone: str
    wishes: Optional[str] = None
    status: str
    table_id: Optional[int] = None
    table_number: Optional[str] = None
    table_location: Optional[str] = None
    has_time_limit: bool = False
    time_limit_hours: Optional[int] = None
    idempotency_key: Optional[str] = None
    created_at: Optional[datetime] = None
    suitable_tables: Optional[List[Dict[str, Any]]] = None
    delay_notified: bool = False

    date: Optional[date] = None
    time: Optional[time] = None

    @model_validator(mode='after')
    def populate_date_time(self):
        if self.start_datetime:
            # Convert UTC datetime to Moscow time before extracting date/time
            from app.core.time_utils import to_moscow_time
            moscow_dt = to_moscow_time(self.start_datetime)
            self.date = moscow_dt.date()
            self.time = moscow_dt.time()
        if self.end_datetime:
            from app.core.time_utils import to_moscow_time
            moscow_end = to_moscow_time(self.end_datetime)
            self.end_time = moscow_end.time()
        return self

    @field_validator('suitable_tables', mode='before')
    @classmethod
    def parse_suitable_tables(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return None
        return v


class BookingCreateResponse(BaseModel):
    id: int
    status: str
    message: str = "Booking created successfully"
    requires_admin_confirmation: bool = False

    @field_validator('status', mode='before')
    @classmethod
    def convert_enum(cls, v):
        return v.value if hasattr(v, 'value') else v


class BookingCreateAdmin(BaseModel):
    restaurant_slug: str
    date: date
    time: time
    end_time: Optional[time] = None
    adults: int = Field(..., ge=1, le=20)
    children: int = Field(0, ge=0, le=10)
    name: str
    phone: str
    wishes: Optional[str] = None
    table_id: Optional[int] = None
    idempotency_key: Optional[str] = None
    lock_value: Optional[str] = None