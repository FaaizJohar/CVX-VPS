import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.security import hash_token
from app.db.session import get_db
from app.models import ApiKey, User, UserRole
from app.services.auth_service import AuthService
from app.services.apikey_service import ApiKeyService

from sqlalchemy.ext.asyncio import AsyncSession

DbDep = Annotated[AsyncSession, Depends(get_db)]


@dataclass(slots=True)
class Actor:
    """Resolved caller identity — either a browser session or an API key."""

    user: User
    session_id: uuid.UUID | None = None
    api_key: ApiKey | None = None

    @property
    def is_api_key(self) -> bool:
        return self.api_key is not None


async def _resolve_session_actor(request: Request, db: AsyncSession) -> Actor | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    session = await AuthService.validate_session(db, token)
    if session is None:
        return None
    return Actor(user=session.user, session_id=session.id)


async def _resolve_api_key_actor(request: Request, db: AsyncSession) -> Actor | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    key = auth[7:].strip()
    if not key.startswith("cvx_"):
        return None
    api_key = await ApiKeyService.authenticate(db, key)
    if api_key is None:
        raise AuthenticationError("Invalid or expired API key.")
    return Actor(user=api_key.user, api_key=api_key)


async def get_optional_actor(request: Request, db: DbDep) -> Actor | None:
    actor = await _resolve_session_actor(request, db)
    if actor is not None:
        return actor
    try:
        return await _resolve_api_key_actor(request, db)
    except AuthenticationError:
        return None


async def get_actor(request: Request, db: DbDep) -> Actor:
    actor = await _resolve_session_actor(request, db)
    if actor is not None:
        return actor
    api_actor = await _resolve_api_key_actor(request, db)
    if api_actor is not None:
        return api_actor
    raise AuthenticationError()


ActorDep = Annotated[Actor, Depends(get_actor)]


def require_role(*roles: UserRole):
    async def checker(actor: ActorDep) -> Actor:
        if actor.user.role not in roles:
            raise AuthorizationError()
        return actor

    return Depends(checker)


async def require_admin(actor: ActorDep) -> Actor:
    if actor.user.role not in (UserRole.OWNER, UserRole.ADMIN):
        raise AuthorizationError()
    return actor


AdminDep = Annotated[Actor, Depends(require_admin)]


async def require_owner(actor: ActorDep) -> Actor:
    if actor.user.role != UserRole.OWNER:
        raise AuthorizationError()
    return actor


OwnerDep = Annotated[Actor, Depends(require_owner)]
