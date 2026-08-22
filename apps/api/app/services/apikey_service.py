import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationError, NotFoundError
from app.core.security import generate_api_key, hash_token, utcnow
from app.models import ApiKey, User


class ApiKeyService:
    @staticmethod
    async def authenticate(db: AsyncSession, plaintext_key: str) -> ApiKey | None:
        rec = (
            await db.execute(
                select(ApiKey).where(ApiKey.key_hash == hash_token(plaintext_key))
            )
        ).scalar_one_or_none()
        if rec is None or not rec.is_valid:
            return None
        user = await db.get(User, rec.user_id)
        if user is None or user.status != "active":
            return None
        rec.last_used_at = utcnow()
        rec.user = user
        return rec

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        user: User,
        name: str,
        scopes: list[str],
        expires_at: datetime | None = None,
    ) -> tuple[ApiKey, str]:
        key, prefix = generate_api_key()
        rec = ApiKey(
            user_id=user.id,
            name=name,
            prefix=prefix,
            key_hash=hash_token(key),
            scopes=scopes,
            expires_at=expires_at,
        )
        db.add(rec)
        await db.flush()
        return rec, key

    @staticmethod
    async def revoke(db: AsyncSession, *, actor: User, key_id: uuid.UUID) -> ApiKey:
        rec = await db.get(ApiKey, key_id)
        if rec is None:
            raise NotFoundError("API key not found.")
        if rec.user_id != actor.id and actor.role not in ("owner", "admin"):
            raise AuthorizationError()
        rec.revoked_at = utcnow()
        return rec

    @staticmethod
    async def list_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[ApiKey]:
        result = await db.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        )
        return list(result.scalars())
