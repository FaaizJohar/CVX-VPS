import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps.auth import AdminDep, DbDep
from app.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.models import User, UserRole, UserStatus
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    _admin: AdminDep,
    db: DbDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> list[UserOut]:
    total = (await db.execute(select(func.count(User.id)))).scalar_one()
    rows = (
        await db.execute(
            select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(body: UserCreate, admin: AdminDep, db: DbDep) -> UserOut:
    existing = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A user with this email already exists.")
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        name=body.name,
        role=UserRole.USER,
    )
    db.add(user)
    await db.flush()
    await record_audit(
        db, action="user.create", actor_user_id=str(admin.user.id),
        resource_type="user", resource_id=str(user.id), detail={"email": user.email},
    )
    return UserOut.model_validate(user)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: uuid.UUID, _admin: AdminDep, db: DbDep) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, admin: AdminDep, db: DbDep
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")

    actor_is_owner = admin.user.role == UserRole.OWNER

    if body.role is not None and body.role not in (r.value for r in UserRole):
        raise ValidationError("Invalid role.")
    if body.status is not None and body.status not in (s.value for s in UserStatus):
        raise ValidationError("Invalid status.")

    # Only owners may mint or revoke the owner role.
    if body.role is not None and body.role == UserRole.OWNER.value and not actor_is_owner:
        raise AuthorizationError("Only the owner can grant the owner role.")
    # Only owners may modify an owner account in any way (role, status, password, name).
    if user.role == UserRole.OWNER and not actor_is_owner:
        raise AuthorizationError("Only the owner can modify an owner.")
    # Never allow removing the last active owner (self-demotion lockout guard).
    if (
        admin.user.id == user.id
        and actor_is_owner
        and (
            (body.role is not None and body.role != UserRole.OWNER.value)
            or (body.status is not None and body.status != UserStatus.ACTIVE.value)
        )
    ):
        other_owners = (
            await db.execute(
                select(func.count(User.id)).where(
                    User.role == UserRole.OWNER,
                    User.status == UserStatus.ACTIVE,
                    User.id != user.id,
                )
            )
        ).scalar_one()
        if other_owners == 0:
            raise ConflictError("Cannot demote or disable the last active owner.")

    if body.role is not None:
        user.role = UserRole(body.role)
    if body.status is not None:
        user.status = UserStatus(body.status)
    if body.name is not None:
        user.name = body.name
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    await record_audit(
        db, action="user.update", actor_user_id=str(admin.user.id),
        resource_type="user", resource_id=str(user.id),
        detail={"fields": [k for k, v in body.model_dump().items() if v is not None]},
    )
    return UserOut.model_validate(user)
