import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(default="", max_length=120)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    role: str
    status: str
    totp_enabled: bool
    last_login_at: datetime | None
    created_at: datetime


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    role: str | None = None
    status: str | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=128)


class TokenResponse(BaseModel):
    user: UserOut


class MessageResponse(BaseModel):
    message: str
