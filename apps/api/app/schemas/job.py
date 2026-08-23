import uuid
from datetime import datetime

from app.schemas.user import ORMModel


class JobOut(ORMModel):
    id: uuid.UUID
    kind: str
    status: str
    stage: str
    progress: int
    error: str | None
    vps_id: uuid.UUID | None
    node_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
