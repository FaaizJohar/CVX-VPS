import uuid
from datetime import timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps.auth import AdminDep, DbDep
from app.api.deps.auth import ActorDep
from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationError
from app.models import NODE_KIND_AGENT, NODE_KIND_LOCAL, Node, NodeStatus, UserRole
from app.schemas.node import NodeCreate, NodeEnrollmentTokenOut, NodeOut
from app.services.audit import record_audit
from app.services.node_service import NodeService

router = APIRouter(prefix="/nodes", tags=["nodes"])

# Fields hidden from non-admin viewers: infrastructure topology, versions,
# addresses and utilization are panel-internal data.
_NONADMIN_HIDDEN_FIELDS = (
    "public_ip", "hostname", "description",
    "agent_version", "lxd_version", "os_name", "os_version",
    "kernel_version", "architecture", "cpu_model", "cpu_cores",
    "ram_total_mb", "storage_total_gb", "storage_driver",
    "cpu_percent", "ram_used_mb", "storage_used_gb", "load1",
    "uptime_seconds", "enrolled_at", "last_heartbeat_at",
)


def _node_out(node: Node, *, is_admin: bool) -> dict:
    data = NodeOut.model_validate(node).model_dump()
    if not is_admin:
        data["status"] = NodeService.effective_status(node)
        for field in _NONADMIN_HIDDEN_FIELDS:
            data.pop(field, None)
    return data


@router.get("")
async def list_nodes(actor: ActorDep, db: DbDep) -> list[dict]:
    from sqlalchemy import select

    is_admin = actor.user.role in (UserRole.OWNER, UserRole.ADMIN)
    rows = (await db.execute(select(Node).where(Node.status != NodeStatus.REMOVED))).scalars().all()
    out = []
    for n in rows:
        d = _node_out(n, is_admin=is_admin)
        if is_admin:
            d["status"] = NodeService.effective_status(n)
        out.append(d)
    return out


@router.post("", status_code=201)
async def create_node(body: NodeCreate, actor: AdminDep, db: DbDep, request: Request) -> dict:
    from datetime import timedelta

    from app.core.security import utcnow

    node, token = await NodeService.create_node(
        db, data=body, created_by_id=actor.user.id
    )
    await record_audit(
        db, action="node.create", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id),
        detail={"name": node.name}, ip_address=request.client.host if request.client else None,
    )
    settings = get_settings()
    return {
        "node": NodeOut.model_validate(node).model_dump(),
        "enrollment": {
            "node_id": str(node.id),
            "token": token,
            "expires_at": (
                utcnow() + timedelta(seconds=settings.enrollment_token_ttl_seconds)
            ).isoformat(),
            "install_command": NodeService.build_install_command(token),
        },
    }


@router.get("/{node_id}", response_model=NodeOut)
async def get_node(node_id: uuid.UUID, _admin: AdminDep, db: DbDep) -> NodeOut:
    node = await NodeService.get_node(db, node_id)
    out = NodeOut.model_validate(node)
    out.status = NodeService.effective_status(node)
    return out


@router.post("/{node_id}/enrollment-token", response_model=NodeEnrollmentTokenOut)
async def new_enrollment_token(
    node_id: uuid.UUID, actor: AdminDep, db: DbDep
) -> NodeEnrollmentTokenOut:
    """Issue a fresh single-use enrollment token (e.g. re-enrollment after rotation)."""
    from app.core.rate_limit import enforce_rate_limit

    await enforce_rate_limit(f"enroll-token:{actor.user.id}", limit=10, window_seconds=3600)
    node = await NodeService.get_node(db, node_id)
    if getattr(node, "kind", NODE_KIND_AGENT) == NODE_KIND_LOCAL:
        raise ValidationError("The local machine does not use agent enrollment.")
    await NodeService.revoke_enrollment_tokens(db, node_id=node.id)
    token = await NodeService.issue_enrollment_token(db, node=node, created_by_id=actor.user.id)
    from app.core.security import utcnow

    expires = utcnow() + timedelta(seconds=get_settings().enrollment_token_ttl_seconds)
    await record_audit(
        db, action="node.enrollment_token.issue", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id),
    )
    return NodeEnrollmentTokenOut(
        node_id=node.id, token=token, expires_at=expires,
        install_command=NodeService.build_install_command(token),
    )


@router.post("/{node_id}/rotate-credentials", response_model=dict)
async def rotate_credentials(node_id: uuid.UUID, actor: AdminDep, db: DbDep) -> dict:
    """Invalidate current node credential; agent must re-enroll with a new token."""
    from app.core.security import utcnow

    node = await NodeService.get_node(db, node_id)
    if getattr(node, "kind", NODE_KIND_AGENT) == NODE_KIND_LOCAL:
        raise ValidationError("The local machine does not use agent enrollment.")
    node.credential_hash = None
    node.credential_encrypted = None
    node.status = NodeStatus.PENDING
    await NodeService.revoke_enrollment_tokens(db, node_id=node.id)
    token = await NodeService.issue_enrollment_token(db, node=node, created_by_id=actor.user.id)
    await record_audit(
        db, action="node.rotate_credentials", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id),
    )
    return {"status": "pending_reenrollment", "enrollment_token": token}


@router.post("/{node_id}/maintenance", response_model=NodeOut)
async def set_maintenance(
    node_id: uuid.UUID, actor: AdminDep, db: DbDep, enabled: bool = Query(...)
) -> NodeOut:
    node = await NodeService.get_node(db, node_id)
    if enabled:
        node.status = NodeStatus.MAINTENANCE
    else:
        node.status = NodeStatus.ONLINE
    await record_audit(
        db, action="node.maintenance", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id), detail={"enabled": enabled},
    )
    return NodeOut.model_validate(node)


@router.post("/{node_id}/disable", response_model=NodeOut)
async def disable_node(node_id: uuid.UUID, actor: AdminDep, db: DbDep) -> NodeOut:
    node = await NodeService.get_node(db, node_id)
    node.status = NodeStatus.DISABLED
    await record_audit(
        db, action="node.disable", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id),
    )
    return NodeOut.model_validate(node)


@router.get("/local/status")
async def local_status(actor: ActorDep, db: DbDep) -> dict:
    """Local compute capability + capacity facts (cached probe, any user)."""
    from app.services.local_capability import get_local_capability

    is_admin = actor.user.role in (UserRole.OWNER, UserRole.ADMIN)
    cap = await get_local_capability()

    out: dict = {
        "available": bool(cap.get("available")),
        "state": cap.get("state"),
        "reason": cap.get("reason"),
        "message": cap.get("message"),
        "diagnostics": cap.get("diagnostics", []),
        "resources": cap.get("resources"),
    }
    node = (
        await db.execute(select(Node).where(Node.kind == NODE_KIND_LOCAL))
    ).scalar_one_or_none()
    out["node_id"] = str(node.id) if node else None
    if is_admin:
        out.update(
            {
                "socket_path": cap.get("socket_path"),
                "lxd_version": cap.get("lxd_version"),
                "os_name": cap.get("os_name"),
                "hostname": cap.get("hostname"),
                "reasons": cap.get("reasons", []),
            }
        )
    return out


@router.post("/local/refresh")
async def refresh_local(actor: AdminDep, db: DbDep) -> dict:
    """Force a fresh local-capability probe and re-detect capacity facts."""
    from app.providers.local_lxd import local_deployment_available
    from app.services.local_capability import get_local_capability, invalidate_cache

    invalidate_cache()
    node = (
        await db.execute(select(Node).where(Node.kind == NODE_KIND_LOCAL))
    ).scalar_one_or_none()
    if not local_deployment_available():
        raise ValidationError("Local deployment is unavailable on this installation.")
    cap = await get_local_capability(force=True)
    if node is None:
        created = await NodeService.get_or_create_local_node(db)
        if created is None:
            raise ValidationError(
                "Local compute is not ready: "
                + str(cap.get("message") or "host is not capable.")
            )
        return {"refreshed": True, "state": cap.get("state")}
    if cap.get("resources"):
        r = cap["resources"]
        node.cpu_cores = r.get("cpu_cores")
        node.ram_total_mb = r.get("ram_total_mb")
        node.storage_total_gb = r.get("storage_total_gb")
    await record_audit(
        db, action="node.local_refresh", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id),
        detail={"state": cap.get("state")},
    )
    return {"refreshed": True, "state": cap.get("state")}


@router.delete("/{node_id}")
async def remove_node(node_id: uuid.UUID, actor: AdminDep, db: DbDep) -> dict:
    from sqlalchemy import func, select

    from app.core.errors import ConflictError
    from app.models import VPS, VPSStatus

    node = await NodeService.get_node(db, node_id)
    if getattr(node, "kind", NODE_KIND_AGENT) == NODE_KIND_LOCAL:
        raise ValidationError("The local machine cannot be removed.")
    active = (
        await db.execute(
            select(func.count(VPS.id)).where(
                VPS.node_id == node.id, VPS.status.notin_([VPSStatus.DELETED])
            )
        )
    ).scalar_one()
    if active:
        raise ConflictError(f"Node still hosts {active} VPS(s). Delete them first.")
    node.status = NodeStatus.REMOVED
    await NodeService.revoke_enrollment_tokens(db, node_id=node.id)
    await record_audit(
        db, action="node.remove", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id),
    )
    return {"removed": True}

