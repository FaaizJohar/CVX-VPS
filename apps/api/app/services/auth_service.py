import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthenticationError, InvalidCredentialsError, NotFoundError
from app.core.security import (
    expiry,
    generate_token,
    hash_password,
    hash_token,
    needs_rehash,
    utcnow,
    verify_password,
)
from app.models import PasswordResetToken, User, UserSession


class AuthService:
    @staticmethod
    async def login(
        db: AsyncSession,
        *,
        email: str,
        password: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str]:
        user = (
            await db.execute(select(User).where(User.email == email.lower()))
        ).scalar_one_or_none()
        if user is None or user.status != "active":
            # Constant-ish work regardless of user existence.
            verify_password(hash_password("dummy"), password)
            raise InvalidCredentialsError()

        if not verify_password(user.password_hash, password):
            raise InvalidCredentialsError()

        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        user.last_login_at = utcnow()
        token = await AuthService.create_session(db, user=user, ip=ip, user_agent=user_agent)
        return user, token

    @staticmethod
    async def create_session(
        db: AsyncSession,
        *,
        user: User,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        settings = get_settings()
        token = generate_token()
        session = UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            ip_address=ip,
            user_agent=(user_agent or "")[:512],
            expires_at=expiry(settings.session_ttl_seconds),
        )
        db.add(session)
        await db.flush()
        return token

    @staticmethod
    async def validate_session(db: AsyncSession, token: str) -> UserSession | None:
        session = (
            await db.execute(
                select(UserSession).where(UserSession.token_hash == hash_token(token))
            )
        ).scalar_one_or_none()
        if session is None or not session.is_valid:
            return None
        user = await db.get(User, session.user_id)
        if user is None or user.status != "active":
            return None
        session.user = user
        return session

    @staticmethod
    async def revoke_session(db: AsyncSession, session_id: uuid.UUID) -> None:
        session = await db.get(UserSession, session_id)
        if session:
            session.revoked_at = utcnow()

    @staticmethod
    async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
        await db.execute(
            delete(UserSession).where(UserSession.user_id == user_id)
        )

    @staticmethod
    async def change_password(
        db: AsyncSession, *, user: User, current_password: str, new_password: str
    ) -> None:
        if not verify_password(user.password_hash, current_password):
            raise AuthenticationError("Current password is incorrect.")
        user.password_hash = hash_password(new_password)
        await AuthService.revoke_all_sessions(db, user.id)

    @staticmethod
    async def create_reset_token(db: AsyncSession, *, email: str) -> str | None:
        """Returns the plaintext reset token if the account exists, else None.

        The caller decides how to deliver it; we never reveal whether the
        account exists in API responses.
        """
        user = (
            await db.execute(select(User).where(User.email == email.lower()))
        ).scalar_one_or_none()
        if user is None or user.status != "active":
            return None
        token = generate_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=expiry(get_settings().password_reset_ttl_seconds),
            )
        )
        return token

    @staticmethod
    async def confirm_reset(db: AsyncSession, *, token: str, new_password: str) -> None:
        from app.core.security import ensure_aware

        rec = (
            await db.execute(
                select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
            )
        ).scalar_one_or_none()
        if rec is None or rec.used_at is not None or ensure_aware(rec.expires_at) < utcnow():
            raise AuthenticationError("Invalid or expired reset token.")
        user = await db.get(User, rec.user_id)
        if user is None:
            raise NotFoundError("User not found.")
        user.password_hash = hash_password(new_password)
        rec.used_at = utcnow()
        await AuthService.revoke_all_sessions(db, user.id)

