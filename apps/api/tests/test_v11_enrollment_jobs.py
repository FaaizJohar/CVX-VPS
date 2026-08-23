"""V1.1: one-command enrollment, public installer endpoints, job flow/authz."""

import hashlib

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from tests.conftest import login

pytestmark = pytest.mark.asyncio


HELLO_BASE = {
    "agent_version": "1.1.0",
    "hostname": "detected.cvx.test",
    "os_name": "Debian",
    "os_version": "12",
    "kernel_version": "6.1",
    "architecture": "x86_64",
    "lxd_version": "5.21",
    "cpu_cores": 4,
    "ram_total_mb": 8192,
    "storage_total_gb": 100.0,
}


async def _create_minimal_node(client: AsyncClient, name: str = "AUTO-1") -> dict:
    """Create a node without hostname/public_ip — they are detected at enroll."""
    resp = await client.post(
        "/api/v1/nodes", json={"name": name, "location": "Testland"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_one_command_enrollment_minimal_create(
    client: AsyncClient, owner_user
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    data = await _create_minimal_node(client)

    node = data["node"]
    assert node["status"] == "pending"
    # Detection placeholders — replaced when the agent checks in.
    assert node["public_ip"] == "pending-detection"

    enrollment = data["enrollment"]
    token = enrollment["token"]
    assert token.startswith("cvxenroll_")
    assert enrollment["expires_at"]

    cmd = enrollment["install_command"]
    assert cmd.startswith("curl -fsSL ")
    assert "/install/node" in cmd
    assert f"--token {token}" in cmd
    assert "--control-plane https://" in cmd


async def test_enroll_adopts_detected_hostname_and_ip(
    client: AsyncClient, owner_user
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    data = await _create_minimal_node(client)
    node_id = data["node"]["id"]

    hello = {**HELLO_BASE, "token": data["enrollment"]["token"],
             "public_ip": "198.51.100.23"}
    resp = await client.post("/api/v1/agent/enroll", json=hello)
    assert resp.status_code == 200, resp.text

    body = (await client.get(f"/api/v1/nodes/{node_id}")).json()
    assert body["status"] == "online"
    assert body["hostname"] == "detected.cvx.test"
    assert body["public_ip"] == "198.51.100.23"


async def test_enroll_rejects_forged_public_ip(
    client: AsyncClient, owner_user
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    data = await _create_minimal_node(client)
    hello = {**HELLO_BASE, "token": data["enrollment"]["token"],
             "public_ip": "not-an-ip-at-all"}
    resp = await client.post("/api/v1/agent/enroll", json=hello)
    assert resp.status_code == 422


async def test_expired_enrollment_token_rejected(
    client: AsyncClient, owner_user, db_session
) -> None:
    from datetime import UTC, datetime

    from app.models import EnrollmentToken

    await login(client, "owner@example.com", "OwnerPass123!")
    data = await _create_minimal_node(client)
    row = (
        await db_session.execute(
            select(EnrollmentToken).where(
                EnrollmentToken.node_id == __import__("uuid").UUID(data["node"]["id"])
            )
        )
    ).scalars().one()
    row.expires_at = datetime.now(UTC).replace(tzinfo=None)
    await db_session.commit()

    hello = {**HELLO_BASE, "token": data["enrollment"]["token"]}
    resp = await client.post("/api/v1/agent/enroll", json=hello)
    assert resp.status_code == 401


async def test_public_installer_and_tarball_endpoints(client: AsyncClient) -> None:
    # No login — these must be reachable by a fresh machine's curl.
    resp = await client.get("/install/node")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/x-shellscript")
    script = resp.text
    assert "--token" in script and "cvxenroll_" in script
    assert "--control-plane" in script and "downloads/cvx-agent-latest.tar.gz" in script

    resp = await client.get("/downloads/cvx-agent-latest.tar.gz")
    assert resp.status_code == 200
    payload = resp.content
    assert payload[:2] == b"\x1f\x8b"  # gzip magic

    resp = await client.get("/downloads/cvx-agent-latest.tar.gz.sha256")
    assert resp.status_code == 200
    expected = hashlib.sha256(payload).hexdigest()
    assert resp.text.strip().startswith(expected)


async def test_job_flow_progress_and_authz(
    client: AsyncClient, owner_user, plain_user, ubuntu_image, fake_provider
):
    from uuid import UUID

    from app.services.provisioning import worker
    from tests.security.helpers import enroll_node

    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await client.post("/api/v1/vps", json={
        "node_id": node["id"], "image_id": str(ubuntu_image.id),
        "name": "job-01", "hostname": "job01.cvx.test",
    })
    assert resp.status_code == 202, resp.text
    created = resp.json()
    job_id = created["job_id"]
    vps_id = created["vps_id"]
    assert created["status"] == "queued"

    # Owner sees the queued job; by-vps resolves it.
    body = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert body["status"] == "queued"
    assert body["vps_id"] == vps_id
    body = (await client.get(f"/api/v1/jobs/by-vps/{vps_id}")).json()
    assert body is not None and body["id"] == job_id

    # Another user must not learn this job exists.
    await client.post("/api/v1/auth/logout")
    await login(client, "user@example.com", "UserPass1234!")
    resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 404
    resp = await client.get(f"/api/v1/jobs/by-vps/{vps_id}")
    assert resp.status_code == 403  # cannot even see the VPS

    # Drive the worker inline (deterministic): job completes, VPS runs.
    await client.post("/api/v1/auth/logout")
    await login(client, "owner@example.com", "OwnerPass123!")
    await worker._execute(job_id)

    body = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert body["status"] == "succeeded"
    assert body["progress"] == 100
    vps = (await client.get(f"/api/v1/vps/{vps_id}")).json()
    assert vps["status"] == "running"

    # Terminal jobs no longer surface via by-vps.
    assert (await client.get(f"/api/v1/jobs/by-vps/{vps_id}")).json() is None


async def test_heartbeat_public_ip_change_recorded(
    client: AsyncClient, owner_user, db_session
) -> None:
    from app.models import SecurityEvent
    from tests.security.helpers import enroll_node

    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)

    hb = {
        "agent_version": "1.0.0",
        "cpu_percent": 5.0,
        "ram_used_mb": 100,
        "storage_used_gb": 1.0,
        "instances": [],
        "public_ip": "203.0.113.77",
    }
    resp = await client.post(
        "/api/v1/agent/heartbeat",
        json=hb,
        headers={"Authorization": f"Bearer {node['credential']}"},
    )
    assert resp.status_code == 200, resp.text

    body = (await client.get(f"/api/v1/nodes/{node['id']}")).json()
    assert body["public_ip"] == "203.0.113.77"

    events = (
        await db_session.execute(select(SecurityEvent))
    ).scalars().all()
    assert any("IP changed" in (e.message or "") for e in events)
