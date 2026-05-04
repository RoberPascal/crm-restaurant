# app/schemas/user_public.py
from pydantic import BaseModel, ConfigDict  # ← импортируй ConfigDict
from datetime import datetime, date
from typing import Optional

class UserPublicBase(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    birth_date: Optional[date] = None
    allergies: Optional[str] = None

class UserPublicRead(UserPublicBase):
    id: int
    telegram_user_id: int
    created_at: datetime
    updated_at: datetime

    # ✅ Правильный синтаксис для Pydantic v2:
    model_config = ConfigDict(from_attributes=True)

class UserPublicUpdate(UserPublicBase):
    pass