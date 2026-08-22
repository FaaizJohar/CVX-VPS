"""H4/M8/M3 — heartbeat reconciliation, stuck-state recovery, payload bounds."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import IPAddress, IPStatus, VPS, VPSStatus
from tests.security.helpers import create_vps, enroll_node, login

pytestmark = pytest.mark.asyncio


async def _heartbeat(client: AsyncClient, node: dict, instances: list[dict], **extra):
    return await client.post(
        "/api/v1/agent/heartbeat",
        json={
            "agent_version": "1.0.0",
            "cpu_percent": 5.0,
            "ram_used_mb": 100,
            "storage_used_gb": 1.0,
            "instances": instances,
            **extra,
        },
        headers={"Authorization": f"Bearer {node['credential']}"},
    )


def _inst(ref: str, status: str) -> dict:
    return {"name": ref, "status": status}


async def _get_ref(db_session, vps_id: str) -> str:
    row = await db_session.get(VPS, uuid.UUID(vps_id))
    assert row is not None
    return row.provider_ref


async def test_out_of_band_deletion_marks_vps_error(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await create_vps(client, node["id"], str(ubuntu_image.id))
    vps_id = resp.json()["id"]

    # Simulate out-of-band deletion: instance missing from the inventory report.
    resp = await _heartbeat(client, node, [])
    assert resp.status_code == 200

    state = (await client.get(f"/api/v1/vps/{vps_id}")).json()
    assert state["status"] == "error", state
    assert state.get("provision_error") == "missing_on_node"


async def test_healthy_instance_not_flagged(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await create_vps(client, node["id"], str(ubuntu_image.id))
    vps_id = resp.json()["id"]
    ref = await _get_ref(db_session, vps_id)

    resp = await _heartbeat(client, node, [_inst(ref, "Running")])
    assert resp.status_code == 200
    state = (await client.get(f"/api/v1/vps/{vps_id}")).json()
    assert state["status"] == "running"


async def test_state_sync_from_inventory(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await create_vps(client, node["id"], str(ubuntu_image.id))
    vps_id = resp.json()["id"]
    ref = await _get_ref(db_session, vps_id)

    # Agent reports the instance stopped.
    resp = await _heartbeat(client, node, [_inst(ref, "Stopped")])
    assert resp.status_code == 200
    detail = (await client.get(f"/api/v1/vps/{vps_id}")).json()
    assert detail["status"] == "stopped"


async def test_heartbeat_payload_bounds_rejected(
    client: AsyncClient, owner_user
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    headers = {"Authorization": f"Bearer {node['credential']}"}

    bad_payloads = [
        {"agent_version": "1.0.0", "cpu_percent": 500},
        {"agent_version": "1.0.0", "ram_used_mb": -5},
        {"agent_version": "1.0.0", "load1": 10**9},
        {"agent_version": "1.0.0", "uptime_seconds": -(2**40)},
        {"agent_version": "1.0.0", "instances": [{"name": ""}]},
        {"agent_version": "1.0.0", "instances": [{"name": "x" * 500}]},
        {"agent_version": "", "instances": []},
    ]
    for payload in bad_payloads:
        resp = await client.post("/api/v1/agent/heartbeat", json=payload, headers=headers)
        assert resp.status_code == 422, f"{payload}: {resp.text}"


async def test_stuck_provisioning_recovered(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    """PROVISIONING rows older than the timeout become ERROR."""
    from app.services import node_service as ns

    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await create_vps(client, node["id"], str(ubuntu_image.id))
    vps_id = resp.json()["id"]

    # Age the row beyond the transitional timeout and force it back to PROVISIONING.
    vps = await db_session.get(VPS, uuid.UUID(vps_id))
    vps.status = VPSStatus.PROVISIONING
    vps.updated_at = datetime.now(UTC) - timedelta(seconds=ns._TRANSITIONAL_TIMEOUT_SECONDS + 60)
    await db_session.commit()

    resp = await _heartbeat(client, node, [])
    assert resp.status_code == 200
    state = (await client.get(f"/api/v1/vps/{vps_id}")).json()
    assert state["status"] == "error"
    assert state.get("provision_error") == "provisioning_timeout"


async def test_recent_provisioning_not_recovered(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    """Fresh PROVISIONING rows must not be touched by reconcile."""
    from app.services import node_service as ns

    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await create_vps(client, node["id"], str(ubuntu_image.id))
    vps_id = resp.json()["id"]

    vps = await db_session.get(VPS, uuid.UUID(vps_id))
    vps.status = VPSStatus.PROVISIONING
    await db_session.commit()

    resp = await _heartbeat(client, node, [])
    assert resp.status_code == 200
    state = (await client.get(f"/api/v1/vps/{vps_id}")).json()
    assert state["status"] == "provisioning"


async def test_stuck_deleting_completes_when_instance_gone(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    from app.services import node_service as ns

    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await create_vps(client, node["id"], str(ubuntu_image.id))
    vps_id = resp.json()["id"]

    vps = await db_session.get(VPS, uuid.UUID(vps_id))
    ref = vps.provider_ref
    vps.status = VPSStatus.DELETING
    vps.updated_at = datetime.now(UTC) - timedelta(seconds=ns._TRANSITIONAL_TIMEOUT_SECONDS + 60)
    ip = IPAddress(node_id=vps.node_id, family=4, address="203.0.113.200",
                   status=IPStatus.ASSIGNED, vps_id=vps.id)
    db_session.add(ip)
    await db_session.commit()

    # Instance absent from report → deletion completes, IP released.
    resp = await _heartbeat(client, node, [])
    assert resp.status_code == 200
    assert (await client.get(f"/api/v1/vps/{vps_id}")).status_code == 404  # DELETED hidden

    await db_session.refresh(ip)
    assert ip.status == IPStatus.AVAILABLE


