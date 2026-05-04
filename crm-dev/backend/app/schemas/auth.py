# app/schemas/auth.py
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from app.db.models.user import RoleEnum
from app.schemas.user import UserResponse


class TokenPayload(BaseModel):
    sub: str  # User ID
    role: RoleEnum | None = None
    exp: int


class Token(BaseModel):
    access_token: str
    token_type: str
    csrf_token: str
    user: UserResponse

class WSToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    role: RoleEnum = Field(default=RoleEnum.operator)