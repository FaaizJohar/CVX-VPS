import pytest
from httpx import AsyncClient

from app.providers.base import InstanceSpec, InstanceState
from tests.conftest import login

pytestmark = pytest.mark.asyncio


class FakeProvider:
    """Deterministic in-memory provider used to test control-plane logic."""

    def __init__(self) -> None:
        self.instances: dict[str, InstanceState] = {}
        self.created: list[InstanceSpec] = []

    async def ping(self): return {}

    async def create_instance(self, spec: InstanceSpec) -> InstanceState:
        self.created.append(spec)
        state = InstanceState(
            name=spec.name, status="Running",
            ips={"eth0": "10.10.0.5"}, raw={"mac": "00:16:3e:aa:bb:cc"},
        )
        self.instances[spec.name] = state
        return state

    async def get_instance(self, name: str):
        return self.instances.get(name)

    async def delete_instance(self, name: str) -> None:
        self.instances.pop(name, None)

    async def start(self, name: str): return {"ok": True}
    async def stop(self, name: str, timeout: int = 30): return {"ok": True}
    async def restart(self, name: str, timeout: int = 30): return {"ok": True}
    async def shutdown(self, name: str, timeout: int = 120): return {"ok": True}
    async def set_config(self, name: str, config): return {"ok": True}
    async def instance_metrics(self, name: str): return {}
    async def create_snapshot(self, *a, **k): return {}
    async def delete_snapshot(self, *a, **k): return None
    async def rename_snapshot(self, *a, **k): return None
    async def restore_snapshot(self, *a, **k): return {}
    async def list_snapshots(self, name: str): return []
    async def create_backup(self, *a, **k): return {}
    async def delete_backup(self, *a, **k): return None
    def console_ws_url(self, name: str): return f"wss://agent/v1/instances/{name}/console"


@pytest.fixture
def fake_provider(monkeypatch):
    provider = FakeProvider()

    import app.services.node_service as ns
    from app.models import Node

    monkeypatch.setattr(
        ns.NodeService, "provider_for", classmethod(lambda cls, node: provider)
    )
    # Also patch the reference imported inside vps_service.
    import app.services.vps_service as vs

    monkeypatch.setattr(
        vs.NodeService, "provider_for", classmethod(lambda cls, node: provider)
    )
    return provider


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
    return (await client.post("/api/v1/vps", json=payload)).json()


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
    body = await _create_vps(client, pending_node["id"], str(ubuntu_image.id))
    assert "error" in body  # node not online -> validation error


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
        assert resp.status_code == 201, resp.text

    resp = await client.get("/api/v1/vps?page=1&page_size=2")
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    resp = await client.get("/api/v1/vps?search=srv-1")
    assert resp.json()["total"] == 1

