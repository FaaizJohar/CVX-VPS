import pytest
from httpx import AsyncClient

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def _create_node(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/nodes",
        json={
            "name": "IN-01",
            "location": "Mumbai, IN",
            "hostname": "in01.cvx.test",
            "public_ip": "103.1.2.3",
            "description": "Primary India node",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_node_lifecycle_enrollment(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    data = await _create_node(client)

    node = data["node"]
    assert node["status"] == "pending"
    token = data["enrollment"]["token"]
    assert token.startswith("cvxenroll_")

    # Agent enrolls with hardware facts.
    hello = {
        "token": token,
        "agent_version": "1.0.0",
        "hostname": "in01.cvx.test",
        "os_name": "Ubuntu",
        "os_version": "24.04",
        "kernel_version": "6.8.0",
        "architecture": "x86_64",
        "lxd_version": "5.21",
        "cpu_model": "AMD EPYC",
        "cpu_cores": 16,
        "ram_total_mb": 32768,
        "storage_total_gb": 960.0,
        "storage_driver": "zfs",
    }
    resp = await client.post("/api/v1/agent/enroll", json=hello)
    assert resp.status_code == 200, resp.text
    cred = resp.json()
    assert cred["credential"].startswith("cvxnode_")

    # Token is single-use.
    resp = await client.post("/api/v1/agent/enroll", json=hello)
    assert resp.status_code == 401

    # Heartbeat with the credential authenticates and updates state.
    hb = {
        "agent_version": "1.0.0",
        "lxd_version": "5.21",
        "cpu_percent": 12.5,
        "ram_used_mb": 4096,
        "storage_used_gb": 120.0,
        "load1": 0.4,
        "uptime_seconds": 86400,
        "instances": [],
    }
    resp = await client.post(
        "/api/v1/agent/heartbeat",
        json=hb,
        headers={"Authorization": f"Bearer {cred['credential']}"},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get(f"/api/v1/nodes/{node['id']}")
    body = resp.json()
    assert body["status"] == "online"
    assert body["lxd_version"] == "5.21"
    assert body["cpu_cores"] == 16
    assert body["ram_total_mb"] == 32768


async def test_enrollment_rejects_missing_lxd(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    data = await _create_node(client)
    hello = {
        "token": data["enrollment"]["token"],
        "agent_version": "1.0.0",
        "hostname": "h",
        "os_name": "Linux",
        "os_version": "6.1",
        "kernel_version": "6.1",
        "architecture": "x86_64",
        "lxd_version": None,
    }
    resp = await client.post("/api/v1/agent/enroll", json=hello)
    assert resp.status_code == 422


async def test_heartbeat_requires_valid_credential(
    client: AsyncClient, owner_user
) -> None:
    hb = {"agent_version": "1.0.0"}
    resp = await client.post("/api/v1/agent/heartbeat", json=hb)
    assert resp.status_code == 401
    resp = await client.post(
        "/api/v1/agent/heartbeat",
        json=hb,
        headers={"Authorization": "Bearer cvxnode_deadbeef_invalid"},
    )
    assert resp.status_code == 401


async def test_duplicate_node_name_rejected(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    await _create_node(client)
    resp = await client.post(
        "/api/v1/nodes",
        json={
            "name": "IN-01",
            "location": "XX",
            "hostname": "x.cvx.test",
            "public_ip": "1.2.3.4",
        },
    )
    assert resp.status_code == 409


async def test_invalid_public_ip_rejected(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/nodes",
        json={
            "name": "XX-99",
            "location": "X",
            "hostname": "xx.cvx.test",
            "public_ip": "not-an-ip",
        },
    )
    assert resp.status_code == 422

