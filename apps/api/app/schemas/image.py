import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.user import ORMModel


class ImageCreate(BaseModel):
    alias: str = Field(min_length=2, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)
    os_family: str = Field(min_length=1, max_length=48)
    version: str = Field(min_length=1, max_length=48)
    architecture: str = Field(default="amd64", max_length=32)
    source_type: str = Field(default="remote", max_length=24)
    source_remote: str = Field(default="ubuntu", max_length=64)
    source_identifier: str = Field(min_length=1, max_length=255)
    description: str = ""
    size_mb: int | None = None
    enabled: bool = True
    min_cpu: int = Field(default=1, ge=1)
    min_ram_mb: int = Field(default=256, ge=64)
    min_disk_gb: int = Field(default=5, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ImageOut(ORMModel):
    id: uuid.UUID
    alias: str
    display_name: str
    os_family: str
    version: str
    architecture: str
    source_type: str
    source_remote: str
    source_identifier: str
    description: str
    size_mb: int | None
    enabled: bool
    min_cpu: int
    min_ram_mb: int
    min_disk_gb: int
    metadata_json: dict[str, Any]
    created_at: datetime


class ImageUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    architecture: str | None = None
    metadata_json: dict[str, Any] | None = None
