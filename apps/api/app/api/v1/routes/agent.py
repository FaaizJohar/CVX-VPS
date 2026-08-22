"""Endpoints called BY node agents. Authenticated with node credentials."""

from fastapi import APIRouter, Request

from app.api.deps.node_auth import DbDep, NodeDep
from app.core.rate_limit import enforce_rate_limit
from app.schemas.node import AgentHeartbeat, EnrollRequest
from app.services.audit import record_log, record_security_event
from app.services.node_service import NodeService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/enroll")
async def enroll(body: EnrollRequest, db: DbDep, request: Request) -> dict:
    ip = request.client.host if request.client else None
    await enforce_rate_limit(f"agent-enroll:{ip}", 20)
    node, credential = await NodeService.enroll(db, token=body.token, hello=body)
    await record_security_event(
        db,
        category="node_enrollment",
        message=f"Node {node.name} enrolled from {ip}",
        severity="warning",
        node_id=str(node.id),
        detail={"agent_version": body.agent_version, "lxd_version": body.lxd_version},
    )
    return {
        "node_id": str(node.id),
        "node_name": node.name,
        "credential": credential,  # shown once; stored hashed+encrypted
        "heartbeat_interval_seconds": 30,
    }


@router.post("/heartbeat")
async def heartbeat(body: AgentHeartbeat, node: NodeDep, db: DbDep) -> dict:
    result = await NodeService.heartbeat(db, node=node, hb=body)
    return result


@router.post("/events")
async def report_event(
    payload: dict, node: NodeDep, db: DbDep
) -> dict:
    """Agent-reported security/operational events."""
    message = str(payload.get("message", ""))[:2000]
    category = str(payload.get("category", "agent"))[:64]
    severity = {"info": "info", "warning": "warning", "critical": "critical"}.get(
        str(payload.get("severity", "info")), "info"
    )
    await record_security_event(
        db,
        category=f"agent:{category}",
        message=message or "Agent event",
        severity=severity,  # type: ignore[arg-type]
        node_id=str(node.id),
        detail={k: v for k, v in payload.items() if k not in ("message", "category", "severity")},
    )
    await record_log(
        db, source="security", message=f"[{node.name}] {message or 'Agent event'}",
        severity=severity, node_id=str(node.id),
    )
    return {"ok": True}
