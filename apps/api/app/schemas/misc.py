import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.user import ORMModel


class SnapshotCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    stateful: bool = False


class SnapshotOut(ORMModel):
    id: uuid.UUID
    vps_id: uuid.UUID
    name: str
    description: str | None
    stateful: bool
    size_bytes: int | None
    created_at: datetime


class BackupCreate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    optimized_storage: bool = True


class BackupOut(ORMModel):
    id: uuid.UUID
    vps_id: uuid.UUID
    node_id: uuid.UUID
    name: str
    status: str
    size_bytes: int | None
    checksum_sha256: str | None
    storage_path: str | None
    optimized_storage: bool
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
