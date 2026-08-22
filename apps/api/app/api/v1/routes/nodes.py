import uuid

from fastapi import APIRouter, Query, Request

from app.api.deps.auth import AdminDep, DbDep
from app.api.deps.auth import ActorDep
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models import Node, NodeStatus, UserRole
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

    node, token = await NodeService.create_node(
        db, data=body, created_by_id=actor.user.id
    )
    await record_audit(
        db, action="node.create", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id),
        detail={"name": node.name}, ip_address=request.client.host if request.client else None,
    )
    settings = get_settings()
    install_command = (
        f"curl -fsSL {settings.cvx_agent_install_url} | sudo CVX_ENROLL_TOKEN={token} "
        f"CVX_CONTROL_PLANE={settings.public_base_url} bash"
        if settings.cvx_agent_install_url
        else f"cvx-agent enroll --token {token}"
    )
    return {
        "node": NodeOut.model_validate(node).model_dump(),
        "enrollment": {
            "node_id": str(node.id),
            "token": token,
            "expires_at": (
                node.created_at
                + timedelta(seconds=settings.enrollment_token_ttl_seconds)
            ).isoformat(),
            "install_command": install_command,
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
    from datetime import timedelta

    from app.core.rate_limit import enforce_rate_limit

    await enforce_rate_limit(f"enroll-token:{actor.user.id}", limit=10, window_seconds=3600)
    node = await NodeService.get_node(db, node_id)
    await NodeService.revoke_enrollment_tokens(db, node_id=node.id)
    token = await NodeService.issue_enrollment_token(db, node=node, created_by_id=actor.user.id)
    expires = (
        node.last_heartbeat_at or node.created_at
    ) + timedelta(seconds=get_settings().enrollment_token_ttl_seconds)
    await record_audit(
        db, action="node.enrollment_token.issue", actor_user_id=str(actor.user.id),
        resource_type="node", resource_id=str(node.id),
    )
    return NodeEnrollmentTokenOut(
        node_id=node.id, token=token, expires_at=expires,
        install_command=f"cvx-agent enroll --token {token}",
    )


@router.post("/{node_id}/rotate-credentials", response_model=dict)
async def rotate_credentials(node_id: uuid.UUID, actor: AdminDep, db: DbDep) -> dict:
    """Invalidate current node credential; agent must re-enroll with a new token."""
    from app.core.security import utcnow

    node = await NodeService.get_node(db, node_id)
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


@router.delete("/{node_id}")
async def remove_node(node_id: uuid.UUID, actor: AdminDep, db: DbDep) -> dict:
    from sqlalchemy import func, select

    from app.core.errors import ConflictError
    from app.models import VPS, VPSStatus

    node = await NodeService.get_node(db, node_id)
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

