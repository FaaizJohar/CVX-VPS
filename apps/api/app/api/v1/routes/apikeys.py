import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps.auth import ActorDep, DbDep
from app.core.errors import NotFoundError
from app.models import ApiKey
from app.schemas.apikey import ApiKeyCreate, ApiKeyCreatedOut, ApiKeyOut
from app.services.audit import record_audit
from app.services.apikey_service import ApiKeyService

router = APIRouter(prefix="/apikeys", tags=["api"])


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(actor: ActorDep, db: DbDep) -> list[ApiKeyOut]:
    keys = await ApiKeyService.list_for_user(db, actor.user.id)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.post("", response_model=ApiKeyCreatedOut, status_code=201)
async def create_key(body: ApiKeyCreate, actor: ActorDep, db: DbDep) -> ApiKeyCreatedOut:
    key, plaintext = await ApiKeyService.create(
        db, user=actor.user, name=body.name, scopes=body.scopes, expires_at=body.expires_at
    )
    await record_audit(
        db, action="apikey.create", actor_user_id=str(actor.user.id),
        resource_type="api_key", resource_id=str(key.id), detail={"name": key.name},
    )
    out = ApiKeyCreatedOut(
        **ApiKeyOut.model_validate(key).model_dump(), key=plaintext
    )
    return out


@router.delete("/{key_id}")
async def revoke_key(key_id: uuid.UUID, actor: ActorDep, db: DbDep) -> dict:
    await ApiKeyService.revoke(db, actor=actor.user, key_id=key_id)
    await record_audit(
        db, action="apikey.revoke", actor_user_id=str(actor.user.id),
        resource_type="api_key", resource_id=str(key_id),
    )
    return {"revoked": True}
