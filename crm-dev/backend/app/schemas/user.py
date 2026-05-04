# app/schemas/user.py
from pydantic import BaseModel, Field
from typing import Optional, List
from app.db.models.user import RoleEnum
from app.schemas.restaurant import RestaurantResponse


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    role: RoleEnum
    is_active: bool = True


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    role: RoleEnum
    restaurant_ids: List[int] = Field(default_factory=list)


class UserUpdate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    role: RoleEnum
    is_active: Optional[bool] = None
    restaurant_ids: List[int] = Field(default_factory=list)


class UserResponse(BaseModel):
    id: int
    username: str
    role: RoleEnum
    is_active: bool

    class Config:
        from_attributes = True


class UserWithRestaurants(UserResponse):
    restaurants: List[RestaurantResponse] = Field(default_factory=list)
    password: Optional[str] = None  # Только при создании