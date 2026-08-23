import pytest
from httpx import AsyncClient

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def _enroll_node(client: AsyncClient) -> dict:
    resp = await client.post(
        "/api/v1/nodes",
        json={
            "name": "SG-01", "location": "Singapore",
            "hostname": "sg01.cvx.test", "public_ip": "203.0.113.10",
        },
    )
    node_data = resp.json()
    hello = {
        "token": node_data["enrollment"]["token"],
        "agent_version": "1.0.0", "hostname": "sg01.cvx.test",
        "os_name": "Debian", "os_version": "12", "kernel_version": "6.1",
        "architecture": "x86_64", "lxd_version": "5.21", "cpu_cores": 8,
        "ram_total_mb": 16384, "storage_total_gb": 500.0,
    }
    await client.post("/api/v1/agent/enroll", json=hello)
    return node_data["node"]


async def _create_vps(client: AsyncClient, node_id: str, image_id: str, **overrides) -> dict:
    payload = {
        "node_id": node_id,
        "image_id": image_id,
        "name": "web-01",
        "hostname": "web01.cvx.test",
        "cpu_limit": 2,
        "ram_mb": 2048,
        "disk_gb": 20,
    }
    payload.update(overrides)
    resp = await client.post("/api/v1/vps", json=payload)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    # Tests drive the worker inline (deterministic, no background loop).
    from uuid import UUID

    from app.services.vps_service import VPSService

    err = await VPSService.provision_vps(vps_id=UUID(body["vps_id"]))
    assert err is None, err
    fetched = await client.get(f"/api/v1/vps/{body['vps_id']}")
    return fetched.json()


async def test_vps_full_lifecycle(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await _enroll_node(client)

    body = await _create_vps(client, node["id"], str(ubuntu_image.id))
    assert body["status"] == "running", body
    assert body["ipv4"] == "10.10.0.5"
    assert body["mac_address"] == "00:16:3e:aa:bb:cc"

    vps_id = body["id"]

    # Spec reached the provider with correct resources.
    spec = fake_provider.created[0]
    assert spec.cpu_limit == 2 and spec.ram_mb == 2048 and spec.disk_gb == 20

    for action, expected in (("stop", "stopped"), ("start", "running"), ("restart", "running")):
        resp = await client.post(f"/api/v1/vps/{vps_id}/{action}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == expected

    resp = await client.delete(f"/api/v1/vps/{vps_id}")
    assert resp.status_code == 200
    assert not fake_provider.instances

    resp = await client.get(f"/api/v1/vps/{vps_id}")
    assert resp.status_code == 404


async def test_vps_creation_requires_online_node(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/nodes",
        json={"name": "OFF-1", "location": "XX", "hostname": "off.cvx.test",
              "public_ip": "192.0.2.9"},
    )
    pending_node = resp.json()["node"]
    resp = await client.post("/api/v1/vps", json={
        "node_id": pending_node["id"], "image_id": str(ubuntu_image.id),
        "name": "web-01", "hostname": "web01.cvx.test",
    })
    assert resp.status_code == 422
    assert "error" in resp.json()  # node not online -> validation error


async def test_vps_owner_isolation(
    client: AsyncClient, owner_user, plain_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await _enroll_node(client)
    body = await _create_vps(client, node["id"], str(ubuntu_image.id))
    vps_id = body["id"]

    # Switch to the plain user.
    await client.post("/api/v1/auth/logout")
    await login(client, "user@example.com", "UserPass1234!")

    resp = await client.get(f"/api/v1/vps/{vps_id}")
    assert resp.status_code == 403
    resp = await client.post(f"/api/v1/vps/{vps_id}/stop")
    assert resp.status_code == 403
    resp = await client.delete(f"/api/v1/vps/{vps_id}")
    assert resp.status_code == 403


async def test_vps_resource_validation(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await _enroll_node(client)

    # Invalid SSH key type.
    resp = await client.post("/api/v1/vps", json={
        "node_id": node["id"], "image_id": str(ubuntu_image.id),
        "name": "bad-ssh", "hostname": "bad.cvx.test",
        "ssh_keys": ["garbage-key"],
    })
    assert resp.status_code == 422

    # Invalid IPv4.
    resp = await client.post("/api/v1/vps", json={
        "node_id": node["id"], "image_id": str(ubuntu_image.id),
        "name": "bad-ip", "hostname": "bad.cvx.test", "ipv4": "999.1.1.1",
    })
    assert resp.status_code == 422

    # Below image minimums.
    resp = await client.post("/api/v1/vps", json={
        "node_id": node["id"], "image_id": str(ubuntu_image.id),
        "name": "tiny", "hostname": "tiny.cvx.test", "disk_gb": 1,
    })
    assert resp.status_code == 422


async def test_vps_list_pagination_and_search(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await _enroll_node(client)
    for i in range(3):
        resp = await client.post("/api/v1/vps", json={
            "node_id": node["id"], "image_id": str(ubuntu_image.id),
            "name": f"srv-{i}", "hostname": f"srv{i}.cvx.test",
        })
        assert resp.status_code == 202, resp.text

    resp = await client.get("/api/v1/vps?page=1&page_size=2")
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    resp = await client.get("/api/v1/vps?search=srv-1")
    assert resp.json()["total"] == 1

