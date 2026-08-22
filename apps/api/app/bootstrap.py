"""First-run bootstrap: creates the owner account from environment settings."""

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.session import get_session_factory
from app.models import User, UserRole

log = get_logger("cvx.bootstrap")


async def ensure_owner_account() -> None:
    settings = get_settings()
    if not settings.bootstrap_owner_email or not settings.bootstrap_owner_password:
        return

    factory = get_session_factory()
    async with factory() as db:
        count = (
            await db.execute(select(func.count(User.id)))
        ).scalar_one()
        if count > 0:
            return
        owner = User(
            email=settings.bootstrap_owner_email.lower(),
            password_hash=hash_password(settings.bootstrap_owner_password),
            name="Owner",
            role=UserRole.OWNER,
        )
        db.add(owner)
        await db.commit()
        log.info("bootstrap owner account created email=%s", settings.bootstrap_owner_email)
