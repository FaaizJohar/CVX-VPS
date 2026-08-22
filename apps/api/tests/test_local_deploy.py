"""V1.1 local deployment mode: registration, creation, guardrails."""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.providers.base import InstanceSpec, InstanceState
from tests.conftest import login

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fake_local_provider(monkeypatch):
    provider = FakeLocalProvider()

    import app.services.node_service as ns
    import app.services.vps_service as vs

    monkeypatch.setattr(
        ns.NodeService, "provider_for", classmethod(lambda cls, node: provider)
    )
    monkeypatch.setattr(
        vs.NodeService, "provider_for", classmethod(lambda cls, node: provider)
    )
    return provider


class FakeLocalProvider:
    def __init__(self) -> None:
        self.instances: dict[str, InstanceState] = {}
        self.created: list[InstanceSpec] = []

    async def ping(self): return {"lxd_version": "5.21"}

    async def create_instance(self, spec: InstanceSpec) -> InstanceState:
        self.created.append(spec)
        state = InstanceState(
            name=spec.name, status="Running", ips={"eth0": "10.0.9.7"}
        )
        self.instances[spec.name] = state
        return state

    async def get_instance(self, name: str):
        return self.instances.get(name)

    async def delete_instance(self, name: str) -> None:
        self.instances.pop(name, None)

    async def start(self, name: str): return {}
    async def stop(self, name: str, timeout: int = 30): return {}
    async def restart(self, name: str, timeout: int = 30): return {}
    async def shutdown(self, name: str, timeout: int = 120): return {}
    async def set_config(self, name: str, config): return {}
    async def instance_metrics(self, name: str): return {}
    async def create_snapshot(self, *a, **k): return {}
    async def delete_snapshot(self, *a, **k): return None
    async def rename_snapshot(self, *a, **k): return None
    async def restore_snapshot(self, *a, **k): return {}
    async def list_snapshots(self, name: str): return []
    async def create_backup(self, *a, **k): return {}
    async def delete_backup(self, *a, **k): return None
    async def restore_backup(self, *a, **k): return {}

    async def console_target(self, name: str, cols: int, rows: int):
        from app.providers.base import ConsoleTarget

        return ConsoleTarget(kind="lxd", url="ws://localhost/1.0/operations/x/websocket",
                             socket_path="/tmp/s.sock", fd_secrets={"0": "s0"})


def _enable_local(monkeypatch) -> None:
    """Force local deployment availability + deterministic capacity facts."""
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_local_deployment", True)

    import app.providers.local_lxd as local_lxd

    monkeypatch.setattr(local_lxd, "local_deployment_available", lambda: True)

    async def _fake_capacity():
        return {
            "hostname": "panel-host", "lxd_version": "5.21",
            "os_name": "Debian", "cpu_cores": 8,
            "ram_total_mb": 16384, "storage_total_gb": 500,
            "storage_used_gb": 42,
        }

    monkeypatch.setattr(local_lxd, "local_capacity", _fake_capacity)


async def test_local_status_disabled_by_default(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.get("/api/v1/nodes/local/status")
    assert resp.status_code == 200
    assert resp.json()["available"] is False


async def test_create_vps_local_unavailable(client: AsyncClient, owner_user, ubuntu_image) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/vps",
        json={"deployment_mode": "local", "image_id": str(ubuntu_image.id),
              "name": "loc-01", "hostname": "loc01.cvx.test"},
    )
    assert resp.status_code == 422
    assert "unavailable" in resp.json()["error"]["message"].lower()


async def test_create_vps_requires_node_id_for_node_mode(
    client: AsyncClient, owner_user, ubuntu_image
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/vps",
        json={"image_id": str(ubuntu_image.id),
              "name": "web-01", "hostname": "web01.cvx.test"},
    )
    assert resp.status_code == 422


async def test_create_vps_rejects_node_id_for_local_mode(
    client: AsyncClient, owner_user, ubuntu_image
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/vps",
        json={"deployment_mode": "local", "node_id": "00000000-0000-0000-0000-000000000000",
              "image_id": str(ubuntu_image.id),
              "name": "loc-01", "hostname": "loc01.cvx.test"},
    )
    assert resp.status_code == 422


async def test_create_vps_local_happy_path(
    client: AsyncClient, owner_user, ubuntu_image, monkeypatch, fake_local_provider
) -> None:
    _enable_local(monkeypatch)
    await login(client, "owner@example.com", "OwnerPass123!")

    resp = await client.post(
        "/api/v1/vps",
        json={"deployment_mode": "local", "image_id": str(ubuntu_image.id),
              "name": "loc-01", "hostname": "loc01.cvx.test",
              "cpu_limit": 2, "ram_mb": 1024, "disk_gb": 10},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["deployment_mode"] == "local"
    assert body["status"] == "running"
    assert body["ipv4"] == "10.0.9.7"

    # Local node row auto-registered with detected capacity.
    nodes = (await client.get("/api/v1/nodes")).json()
    local = [n for n in nodes if n["kind"] == "local"]
    assert len(local) == 1
    assert local[0]["name"] == "local-machine"
    assert local[0]["cpu_cores"] == 8 and local[0]["ram_total_mb"] == 16384

    # A second create reuses the same singleton node row.
    resp2 = await client.post(
        "/api/v1/vps",
        json={"deployment_mode": "local", "image_id": str(ubuntu_image.id),
              "name": "loc-02", "hostname": "loc02.cvx.test"},
    )
    assert resp2.status_code == 201
    nodes = (await client.get("/api/v1/nodes")).json()
    assert len([n for n in nodes if n["kind"] == "local"]) == 1


async def test_local_node_remove_and_rotate_blocked(
    client: AsyncClient, owner_user, ubuntu_image, monkeypatch, fake_local_provider
) -> None:
    _enable_local(monkeypatch)
    await login(client, "owner@example.com", "OwnerPass123!")
    await client.post(
        "/api/v1/vps",
        json={"deployment_mode": "local", "image_id": str(ubuntu_image.id),
              "name": "loc-01", "hostname": "loc01.cvx.test"},
    )
    nodes = (await client.get("/api/v1/nodes")).json()
    local_id = next(n["id"] for n in nodes if n["kind"] == "local")

    resp = await client.delete(f"/api/v1/nodes/{local_id}")
    assert resp.status_code == 422
    assert "cannot be removed" in resp.json()["error"]["message"].lower()

    resp = await client.post(f"/api/v1/nodes/{local_id}/rotate-credentials")
    assert resp.status_code == 422


async def test_local_refresh_endpoint(
    client: AsyncClient, owner_user, ubuntu_image, monkeypatch, fake_local_provider
) -> None:
    _enable_local(monkeypatch)
    await login(client, "owner@example.com", "OwnerPass123!")
    await client.post(
        "/api/v1/vps",
        json={"deployment_mode": "local", "image_id": str(ubuntu_image.id),
              "name": "loc-01", "hostname": "loc01.cvx.test"},
    )
    resp = await client.post("/api/v1/nodes/local/refresh")
    assert resp.status_code == 200
    assert resp.json()["refreshed"] is True


async def test_node_mode_cannot_target_local_node(
    client: AsyncClient, owner_user, ubuntu_image, monkeypatch, fake_local_provider
) -> None:
    """A node-mode create whose node_id points at the local row must fail."""
    _enable_local(monkeypatch)
    await login(client, "owner@example.com", "OwnerPass123!")
    await client.post(
        "/api/v1/vps",
        json={"deployment_mode": "local", "image_id": str(ubuntu_image.id),
              "name": "loc-01", "hostname": "loc01.cvx.test"},
    )
    nodes = (await client.get("/api/v1/nodes")).json()
    local_id = next(n["id"] for n in nodes if n["kind"] == "local")

    resp = await client.post(
        "/api/v1/vps",
        json={"node_id": local_id, "image_id": str(ubuntu_image.id),
              "name": "bad-01", "hostname": "bad01.cvx.test"},
    )
    assert resp.status_code == 422
