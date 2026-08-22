import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.api.deps.auth import ActorDep, DbDep
from app.core.config import get_settings
from app.core.errors import AuthenticationError, InvalidCredentialsError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import utcnow
from app.models import UserSession
from app.schemas.user import (
    MessageResponse,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
    UserLogin,
)
from app.services.audit import record_audit, record_security_event
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, request: Request, response: Response, db: DbDep) -> TokenResponse:
    ip = request.client.host if request.client else None
    await enforce_rate_limit(f"login:{ip}", get_settings().rate_limit_auth_per_minute)
    user, token = await AuthService.login(
        db, email=body.email, password=body.password, ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    _set_session_cookie(response, token)
    await record_security_event(
        db, category="auth", message=f"User {user.email} logged in",
        user_id=str(user.id),
    )
    return TokenResponse(user=user)  # type: ignore[arg-type]


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response, actor: ActorDep, db: DbDep) -> MessageResponse:
    if actor.session_id:
        await AuthService.revoke_session(db, actor.session_id)
    _clear_session_cookie(response)
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=TokenResponse)
async def me(actor: ActorDep) -> TokenResponse:
    return TokenResponse(user=actor.user)  # type: ignore[arg-type]


@router.post("/verify-password", response_model=MessageResponse)
async def verify_password(
    body: UserLogin, request: Request, actor: ActorDep, db: DbDep
) -> MessageResponse:
    """Step-up authentication used by the VPS secure-entry screen."""
    from app.core.security import verify_password

    ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"verify-pw:{actor.user.id}:{ip}", limit=5, window_seconds=60)
    if not verify_password(actor.user.password_hash, body.password):
        raise InvalidCredentialsError()
    return MessageResponse(message="verified")


@router.post("/password/change", response_model=MessageResponse)
async def change_password(
    body: PasswordChange, response: Response, actor: ActorDep, db: DbDep
) -> MessageResponse:
    await AuthService.change_password(
        db, user=actor.user,
        current_password=body.current_password, new_password=body.new_password,
    )
    _clear_session_cookie(response)
    await record_security_event(
        db, category="auth", message=f"Password changed for {actor.user.email}",
        severity="warning", user_id=str(actor.user.id),
    )
    return MessageResponse(message="Password changed. Please sign in again.")


@router.post("/password/reset-request", response_model=MessageResponse)
async def reset_request(body: PasswordResetRequest, request: Request, db: DbDep) -> MessageResponse:
    ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"reset-req:{ip}", limit=5, window_seconds=60)
    # Always the same response whether or not the account exists.
    await AuthService.create_reset_token(db, email=body.email)
    return MessageResponse(message="If that account exists, a reset link has been generated.")


@router.post("/password/reset-confirm", response_model=MessageResponse)
async def reset_confirm(body: PasswordResetConfirm, request: Request, db: DbDep) -> MessageResponse:
    ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"reset-cfm:{ip}", limit=10, window_seconds=60)
    await AuthService.confirm_reset(db, token=body.token, new_password=body.new_password)
    return MessageResponse(message="Password has been reset.")


@router.get("/sessions")
async def list_sessions(actor: ActorDep, db: DbDep) -> dict:
    rows = (
        await db.execute(
            select(UserSession)
            .where(UserSession.user_id == actor.user.id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.created_at.desc())
        )
    ).scalars().all()
    now = datetime.now(UTC)
    return {
        "items": [
            {
                "id": str(s.id),
                "current": s.id == actor.session_id,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
                "valid": s.expires_at > now,
            }
            for s in rows
        ]
    }


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
async def revoke_session(session_id: uuid.UUID, actor: ActorDep, db: DbDep) -> MessageResponse:
    row = await db.get(UserSession, session_id)
    if row is None or row.user_id != actor.user.id:
        raise AuthenticationError()
    await AuthService.revoke_session(db, session_id)
    return MessageResponse(message="Session revoked.")
