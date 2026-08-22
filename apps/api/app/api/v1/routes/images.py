import uuid

from fastapi import APIRouter

from app.api.deps.auth import ActorDep, AdminDep, DbDep
from app.core.errors import ConflictError, NotFoundError
from app.models import Image
from app.schemas.image import ImageCreate, ImageOut, ImageUpdate
from app.services.audit import record_audit

router = APIRouter(prefix="/images", tags=["images"])


@router.get("", response_model=list[ImageOut])
async def list_images(actor: ActorDep, db: DbDep, include_disabled: bool = False) -> list[ImageOut]:
    from sqlalchemy import select

    q = select(Image)
    if not (include_disabled and actor.user.role in ("owner", "admin")):
        q = q.where(Image.enabled.is_(True))
    rows = (await db.execute(q.order_by(Image.os_family, Image.version))).scalars().all()
    return [ImageOut.model_validate(i) for i in rows]


@router.post("", response_model=ImageOut, status_code=201)
async def create_image(body: ImageCreate, admin: AdminDep, db: DbDep) -> ImageOut:
    from sqlalchemy import select

    existing = (
        await db.execute(select(Image).where(Image.alias == body.alias))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("An image with this alias already exists.")
    image = Image(**body.model_dump())
    db.add(image)
    await db.flush()
    await record_audit(
        db, action="image.create", actor_user_id=str(admin.user.id),
        resource_type="image", resource_id=str(image.id), detail={"alias": image.alias},
    )
    return ImageOut.model_validate(image)


@router.patch("/{image_id}", response_model=ImageOut)
async def update_image(
    image_id: uuid.UUID, body: ImageUpdate, admin: AdminDep, db: DbDep
) -> ImageOut:
    image = await db.get(Image, image_id)
    if image is None:
        raise NotFoundError("Image not found.")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(image, k, v)
    await record_audit(
        db, action="image.update", actor_user_id=str(admin.user.id),
        resource_type="image", resource_id=str(image.id),
    )
    return ImageOut.model_validate(image)


@router.delete("/{image_id}")
async def delete_image(image_id: uuid.UUID, admin: AdminDep, db: DbDep) -> dict:
    image = await db.get(Image, image_id)
    if image is None:
        raise NotFoundError("Image not found.")
    await db.delete(image)
    await record_audit(
        db, action="image.delete", actor_user_id=str(admin.user.id),
        resource_type="image", resource_id=str(image_id), detail={"alias": image.alias},
    )
    return {"deleted": True}
