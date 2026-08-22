"""M5 — private node IPs rejected by default; M11 — node data gated by role."""

import pytest
from httpx import AsyncClient

from tests.security.helpers import login

pytestmark = pytest.mark.asyncio


async def test_private_public_ip_rejected_by_default(
    client: AsyncClient, owner_user, monkeypatch
) -> None:
    monkeypatch.setenv("CVX_ALLOW_PRIVATE_NODE_IPS", "false")
    from app.schemas.node import validate_public_ip

    for bad in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.1.1", "172.16.0.9"):
        with pytest.raises(ValueError):
            validate_public_ip(bad)
    # Genuinely public addresses are fine.
    assert validate_public_ip("8.8.8.8") == "8.8.8.8"
    assert validate_public_ip("93.184.216.34") == "93.184.216.34"


async def test_loopback_accepted_when_env_allows(
    client: AsyncClient, owner_user, monkeypatch
) -> None:
    monkeypatch.setenv("CVX_ALLOW_PRIVATE_NODE_IPS", "true")
    from app.schemas.node import validate_public_ip

    assert validate_public_ip("127.0.0.1") == "127.0.0.1"


async def test_node_list_hides_infra_from_regular_users(
    client: AsyncClient, owner_user, plain_user
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/nodes",
        json={"name": "HD-01", "location": "XX", "hostname": "hd.cvx.test",
              "public_ip": "198.51.100.20", "description": "secret"},
    )
    assert resp.status_code == 201, resp.text
    node_id = resp.json()["node"]["id"]

    # Owner sees everything.
    body = (await client.get("/api/v1/nodes")).json()
    mine = [n for n in body if n["id"] == node_id][0]
    assert mine["public_ip"] == "198.51.100.20"

    # Regular user gets a slimmed projection.
    await client.post("/api/v1/auth/logout")
    await login(client, "user@example.com", "UserPass1234!")
    body = (await client.get("/api/v1/nodes")).json()
    slim = [n for n in body if n["id"] == node_id][0]
    for hidden in ("public_ip", "hostname", "cpu_cores", "ram_total_mb",
                   "storage_total_gb", "agent_version", "lxd_version",
                   "cpu_percent", "description", "last_heartbeat_at"):
        assert hidden not in slim, hidden

    # Detail endpoint is admin-only.
    resp = await client.get(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 403


async def test_admin_sees_full_node_detail(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/nodes",
        json={"name": "HD-02", "location": "XX", "hostname": "hd2.cvx.test",
              "public_ip": "198.51.100.21"},
    )
    node_id = resp.json()["node"]["id"]
    resp = await client.get(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 200
    assert resp.json()["public_ip"] == "198.51.100.21"
