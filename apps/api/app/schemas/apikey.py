import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.user import ORMModel


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list, max_length=20)
    expires_at: datetime | None = None


class ApiKeyOut(ORMModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[Any]
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreatedOut(ApiKeyOut):
    key: str  # plaintext shown exactly once
