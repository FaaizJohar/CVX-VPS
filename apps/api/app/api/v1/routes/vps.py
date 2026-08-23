import uuid
from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.deps.auth import ActorDep, DbDep
from app.core.errors import ProviderError, ValidationError
from app.core.rate_limit import enforce_rate_limit
from app.providers.lxd import LXDProvider
from app.schemas.vps import RawConfigUpdate, VPSActionResponse, VPSCreate, VPSOut, VPSUpdate
from app.services.node_service import NodeService
from app.services.vps_service import VPSService

router = APIRouter(prefix="/vps", tags=["vps"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("")
async def list_vps(
    actor: ActorDep,
    db: DbDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    node_id: uuid.UUID | None = None,
    status: str | None = None,
    search: str | None = None,
) -> dict:
    vps_list, total = await VPSService.list_vps(
        db, user=actor.user, page=page, page_size=page_size,
        node_id=node_id, status=status, search=search,
    )
    return {
        "items": [VPSOut.model_validate(v).model_dump() for v in vps_list],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", status_code=202)
async def create_vps(body: VPSCreate, actor: ActorDep, db: DbDep, request: Request) -> dict:
    """Queue provisioning. Returns immediately with a job id; progress is
    exposed via GET /jobs/{id} and SSE /jobs/{id}/events."""
    from app.models import ProvisioningJob
    from app.services.provisioning import enqueue_vps_create

    await enforce_rate_limit(f"vps-create:{actor.user.id}", limit=10, window_seconds=3600)
    vps, node = await VPSService.prepare_vps(db, data=body, owner=actor.user)
    job = ProvisioningJob(
        kind="vps_create",
        vps_id=vps.id,
        node_id=node.id,
        user_id=actor.user.id,
    )
    db.add(job)
    await db.flush()
    enqueue_vps_create(str(job.id))
    return {
        "job_id": str(job.id),
        "vps_id": str(vps.id),
        "status": "queued",
        "name": vps.name,
    }


@router.get("/{vps_id}", response_model=VPSOut)
async def get_vps(vps_id: uuid.UUID, actor: ActorDep, db: DbDep) -> VPSOut:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    return VPSOut.model_validate(vps)


@router.patch("/{vps_id}", response_model=VPSOut)
async def update_vps(
    vps_id: uuid.UUID, body: VPSUpdate, actor: ActorDep, db: DbDep
) -> VPSOut:
    from sqlalchemy import select

    from app.models import Node
    from app.services.audit import record_audit

    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise ValidationError("No changes supplied.")

    # Resource changes are applied to the provider first.
    resource_keys = {"cpu_limit", "ram_mb", "swap_mb", "disk_gb", "process_limit"}
    if resource_keys & updates.keys():
        node = await db.get(Node, vps.node_id)
        if node is None:
            raise ValidationError("Node missing.")
        provider = NodeService.provider_for(node)
        config: dict[str, str] = {}
        if "cpu_limit" in updates:
            config["limits.cpu"] = str(updates["cpu_limit"])
        if "ram_mb" in updates:
            config["limits.memory"] = f"{updates['ram_mb']}MiB"
        if "swap_mb" in updates:
            config["limits.memory.swap"] = "true" if updates["swap_mb"] > 0 else "false"
        if "process_limit" in updates:
            config["limits.processes"] = str(updates["process_limit"])
        try:
            await provider.set_config(vps.provider_ref, config)
        except Exception as e:
            raise ProviderError("Failed to apply resource limits on the node.") from e

    for key, value in updates.items():
        setattr(vps, key, value)
    await record_audit(
        db, action="vps.update", actor_user_id=str(actor.user.id),
        resource_type="vps", resource_id=str(vps.id), detail={"fields": list(updates.keys())},
    )
    return VPSOut.model_validate(vps)


@router.delete("/{vps_id}")
async def delete_vps(
    vps_id: uuid.UUID, actor: ActorDep, db: DbDep, request: Request
) -> dict:
    await enforce_rate_limit(f"vps-delete:{actor.user.id}", limit=20, window_seconds=3600)
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    await VPSService.delete_vps(db, vps=vps, actor=actor.user, ip=_client_ip(request))
    return {"deleted": True}


@router.post("/{vps_id}/{action}", response_model=VPSActionResponse)
async def vps_action(
    vps_id: uuid.UUID, action: str, actor: ActorDep, db: DbDep, request: Request
) -> VPSActionResponse:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    result = await VPSService.lifecycle_action(
        db, vps=vps, action=action, actor=actor.user, ip=_client_ip(request)
    )
    return VPSActionResponse(**result)


@router.get("/{vps_id}/state")
async def live_state(vps_id: uuid.UUID, actor: ActorDep, db: DbDep) -> dict:
    """Live state straight from the node (status, IPs, processes)."""
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    provider, _node = await VPSService._provider(db, vps)
    state = await provider.get_instance(vps.provider_ref)
    if state is None:
        return {"reachable": False}
    return {
        "reachable": True,
        "status": state.status.lower(),
        "ips": state.ips,
        "process_count": state.process_count,
        "created_at": state.created_at,
    }


# --- Advanced configuration -------------------------------------------------


@router.get("/{vps_id}/config")
async def get_config(vps_id: uuid.UUID, actor: ActorDep, db: DbDep) -> dict:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    provider, _node = await VPSService._provider(db, vps)
    state = await provider.get_instance(vps.provider_ref)
    raw = (state.raw or {}).get("config", {}) if state else {}
    return {"db_config": vps.raw_config or {}, "provider_config": raw}


@router.put("/{vps_id}/config")
async def set_config(
    vps_id: uuid.UUID, body: RawConfigUpdate, actor: ActorDep, db: DbDep
) -> dict:
    vps = await VPSService.get_vps_checked(db, vps_id=vps_id, user=actor.user)
    result = await VPSService.update_raw_config(
        db, vps=vps, config=body.config, actor=actor.user
    )
    return result or {"ok": True}
