import pytest

from app.providers.base import InstanceSpec, InstanceState


class FakeProvider:
    """Deterministic in-memory provider used to test control-plane logic."""

    def __init__(self) -> None:
        self.instances: dict[str, InstanceState] = {}
        self.created: list[InstanceSpec] = []
        self.fail_delete: set[str] = set()

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
        if name in self.fail_delete:
            raise RuntimeError("simulated delete failure")
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
    async def restore_backup(self, *a, **k): return {}
    async def console_target(self, name: str, cols: int, rows: int):
        from app.providers.base import ConsoleTarget

        return ConsoleTarget(
            kind="agent", url=f"wss://agent/v1/instances/{name}/console"
        )


@pytest.fixture
def fake_provider(monkeypatch):
    provider = FakeProvider()

    import app.services.node_service as ns
    import app.services.vps_service as vs

    monkeypatch.setattr(
        ns.NodeService, "provider_for", classmethod(lambda cls, node: provider)
    )
    monkeypatch.setattr(
        vs.NodeService, "provider_for", classmethod(lambda cls, node: provider)
    )
    return provider


async def login(client, email: str, password: str) -> None:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
