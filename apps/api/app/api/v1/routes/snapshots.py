import re
import uuid

from fastapi import APIRouter

from app.api.deps.auth import ActorDep, DbDep
from app.core.errors import ConflictError, NotFoundError, ProviderError
from app.schemas.misc import BackupCreate, BackupOut, SnapshotCreate, SnapshotOut
from app.services.audit import record_audit
from app.services.node_service import NodeService
from app.services.vps_service import VPSService

router = APIRouter(prefix="/vps/{vps_id}", tags=["snapshots", "backups"])

NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def _safe_name(name: str | None, prefix: str) -> str:
    if name is None:
        import time as _t

        return f"{prefix}-{_t.strftime('%Y%m%d-%H%M%S')}"
    if not NAME_RE.match(name):
        from app.core.errors import ValidationError

        raise ValidationError("Name may contain letters, numbers, dots, dashes.")
    return name


# --- Snapshots ---------------------------------------------------------------


@router.get("/snapshots", response_model=list[SnapshotOut])
async def list_snapshots(vps_id: uuid.UUID, actor: ActorDep, db: DbDep) -> list[SnapshotOut]:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    provider, _ = await VPSService._provider(db, vps)
    try:
        snaps = await provider.list_snapshots(vps.provider_ref)
    except Exception as e:
        raise ProviderError("Failed to list snapshots on the node.") from e
    return [
        SnapshotOut(
            id=s.get("uuid") or s.get("name", ""),
            vps_id=vps.id,
            name=str(s.get("name", "")).split("/")[-1],
            description=s.get("description"),
            stateful=bool(s.get("stateful", False)),
            size_bytes=s.get("size"),
            created_at=s.get("created_at") or s.get("taken_at") or _epoch(),
        )
        for s in snaps
    ]


def _epoch():
    from datetime import UTC, datetime

    return datetime.now(UTC)


@router.post("/snapshots", response_model=SnapshotOut, status_code=201)
async def create_snapshot(
    vps_id: uuid.UUID, body: SnapshotCreate, actor: ActorDep, db: DbDep
) -> SnapshotOut:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    provider, node = await VPSService._provider(db, vps)
    name = _safe_name(body.name, "snap")
    try:
        result = await provider.create_snapshot(vps.provider_ref, name, body.stateful)
    except Exception as e:
        raise ProviderError("Snapshot creation failed on the node.") from e
    await record_audit(
        db, action="vps.snapshot.create", actor_user_id=str(actor.user.id),
        resource_type="vps", resource_id=str(vps.id), detail={"snapshot": name},
    )
    return SnapshotOut(
        id=result.get("uuid") or name,
        vps_id=vps.id,
        name=name,
        description=body.description,
        stateful=body.stateful,
        size_bytes=result.get("size"),
        created_at=_epoch(),
    )


@router.post("/snapshots/{snapshot_name}/restore")
async def restore_snapshot(
    vps_id: uuid.UUID, snapshot_name: str, actor: ActorDep, db: DbDep
) -> dict:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    provider, node = await VPSService._provider(db, vps)
    try:
        await provider.restore_snapshot(vps.provider_ref, snapshot_name)
    except Exception as e:
        raise ProviderError("Snapshot restore failed on the node.") from e
    await record_audit(
        db, action="vps.snapshot.restore", actor_user_id=str(actor.user.id),
        resource_type="vps", resource_id=str(vps.id),
        detail={"snapshot": snapshot_name},
    )
    return {"restored": True, "snapshot": snapshot_name}


@router.post("/snapshots/{snapshot_name}/rename")
async def rename_snapshot(
    vps_id: uuid.UUID, snapshot_name: str, new_name: str, actor: ActorDep, db: DbDep
) -> dict:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    new_name = _safe_name(new_name, "snap")
    provider, _ = await VPSService._provider(db, vps)
    try:
        await provider.rename_snapshot(vps.provider_ref, snapshot_name, new_name)
    except Exception as e:
        raise ProviderError("Rename failed on the node.") from e
    await record_audit(
        db, action="vps.snapshot.rename", actor_user_id=str(actor.user.id),
        resource_type="vps", resource_id=str(vps.id),
        detail={"from": snapshot_name, "to": new_name},
    )
    return {"renamed": True, "name": new_name}


@router.delete("/snapshots/{snapshot_name}")
async def delete_snapshot(
    vps_id: uuid.UUID, snapshot_name: str, actor: ActorDep, db: DbDep
) -> dict:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    provider, _ = await VPSService._provider(db, vps)
    try:
        await provider.delete_snapshot(vps.provider_ref, snapshot_name)
    except Exception as e:
        raise ProviderError("Snapshot deletion failed on the node.") from e
    await record_audit(
        db, action="vps.snapshot.delete", actor_user_id=str(actor.user.id),
        resource_type="vps", resource_id=str(vps.id), detail={"snapshot": snapshot_name},
    )
    return {"deleted": True}


# --- Backups -----------------------------------------------------------------


@router.get("/backups", response_model=list[BackupOut])
async def list_backups(vps_id: uuid.UUID, actor: ActorDep, db: DbDep) -> list[BackupOut]:
    from sqlalchemy import select

    from app.models import Backup

    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    rows = (
        await db.execute(
            select(Backup).where(Backup.vps_id == vps.id).order_by(Backup.created_at.desc())
        )
    ).scalars().all()
    return [BackupOut.model_validate(b) for b in rows]


@router.post("/backups", response_model=BackupOut, status_code=202)
async def create_backup(
    vps_id: uuid.UUID, body: BackupCreate, actor: ActorDep, db: DbDep
) -> BackupOut:
    from datetime import UTC, datetime

    from app.models import Backup, BackupStatus

    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    provider, node = await VPSService._provider(db, vps)
    name = _safe_name(body.name, f"backup-{vps.name}")

    backup = Backup(
        vps_id=vps.id,
        node_id=node.id,
        name=name,
        status=BackupStatus.RUNNING,
        optimized_storage=body.optimized_storage,
    )
    db.add(backup)
    await db.flush()

    try:
        result = await provider.create_backup(
            vps.provider_ref, name, body.optimized_storage
        )
        backup.status = BackupStatus.COMPLETED
        backup.size_bytes = result.get("size")
        backup.checksum_sha256 = result.get("checksum")
        backup.storage_path = result.get("path")
        backup.completed_at = datetime.now(UTC)
    except Exception as e:
        backup.status = BackupStatus.FAILED
        backup.error = str(e)[:1000]
        raise ProviderError("Backup failed on the node.") from e

    await record_audit(
        db, action="vps.backup.create", actor_user_id=str(actor.user.id),
        resource_type="vps", resource_id=str(vps.id), detail={"backup": name},
    )
    return BackupOut.model_validate(backup)


@router.post("/backups/{backup_id}/restore")
async def restore_backup(
    vps_id: uuid.UUID, backup_id: uuid.UUID, actor: ActorDep, db: DbDep
) -> dict:
    from datetime import UTC, datetime

    from app.models import Backup, BackupStatus

    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    backup = await db.get(Backup, backup_id)
    if backup is None or backup.vps_id != vps.id:
        raise NotFoundError("Backup not found.")
    if backup.status != BackupStatus.COMPLETED or not backup.storage_path:
        raise ConflictError("Backup is not in a restorable state.")

    provider, node = await VPSService._provider(db, vps)
    try:
        await provider.restore_backup(vps.provider_ref, backup.storage_path)
    except Exception as e:
        raise ProviderError("Restore failed on the node.") from e

    backup.restored_at = datetime.now(UTC)
    await record_audit(
        db, action="vps.backup.restore", actor_user_id=str(actor.user.id),
        resource_type="vps", resource_id=str(vps.id), detail={"backup": backup.name},
    )
    return {"restored": True}


@router.delete("/backups/{backup_id}")
async def delete_backup(
    vps_id: uuid.UUID, backup_id: uuid.UUID, actor: ActorDep, db: DbDep
) -> dict:
    from app.models import Backup

    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    backup = await db.get(Backup, backup_id)
    if backup is None or backup.vps_id != vps.id:
        raise NotFoundError("Backup not found.")
    provider, _ = await VPSService._provider(db, vps)
    try:
        await provider.delete_backup(backup.name)
    except Exception as e:
        raise ProviderError("Backup deletion failed on the node.") from e
    await db.delete(backup)
    await record_audit(
        db, action="vps.backup.delete", actor_user_id=str(actor.user.id),
        resource_type="vps", resource_id=str(vps.id), detail={"backup": backup.name},
    )
    return {"deleted": True}
