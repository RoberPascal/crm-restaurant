# app/schemas/table.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.db.models.booking import CapacityEnum

class TableBase(BaseModel):
    number: str = Field(..., min_length=1, max_length=20)
    seats_min: int = Field(..., ge=1)
    seats_max: int = Field(..., ge=1)
    location_mark: Optional[str] = None
    type: Optional[CapacityEnum] = None  # small/medium/large
    is_active: bool = True

    @field_validator('seats_max')
    @classmethod
    def validate_seats(cls, v: int, values) -> int:
        if 'seats_min' in values and v < values['seats_min']:
            raise ValueError("seats_max must be >= seats_min")
        return v

class TableCreate(TableBase):
    restaurant_id: int

class TableUpdate(TableBase):
    pass

class TableSchema(TableBase):
    id: int
    restaurant_id: int

    class Config:
        from_attributes = True