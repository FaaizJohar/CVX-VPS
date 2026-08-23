import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

# Must be set before app.config is first imported/cached.
os.environ.setdefault("CVX_SESSION_COOKIE_SECURE", "false")
os.environ.setdefault("CVX_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("CVX_ALLOW_PRIVATE_NODE_IPS", "true")
# Serve the real node-agent package for /install/node + /downloads endpoints.
os.environ.setdefault(
    "CVX_AGENT_PACKAGE_DIR",
    str(Path(__file__).resolve().parents[3] / "services" / "node-agent"),
)

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Image, User, UserRole


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client(db_engine) -> AsyncIterator[AsyncClient]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    # Background workers (provisioning jobs, SSE streams) build sessions via
    # the module-level factory — point it at this test's in-memory engine.
    import app.db.session as _db_session

    _db_session._engine = db_engine
    _db_session._session_factory = factory

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    _db_session._engine = None
    _db_session._session_factory = None


@pytest.fixture
async def owner_user(db_session: AsyncSession) -> User:
    user = User(
        email="owner@example.com",
        password_hash=hash_password("OwnerPass123!"),
        name="Owner",
        role=UserRole.OWNER,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def plain_user(db_session: AsyncSession) -> User:
    user = User(
        email="user@example.com",
        password_hash=hash_password("UserPass1234!"),
        name="User",
        role=UserRole.USER,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def ubuntu_image(db_session: AsyncSession) -> Image:
    image = Image(
        alias="ubuntu-24.04",
        display_name="Ubuntu 24.04 LTS",
        os_family="ubuntu",
        version="24.04",
        source_identifier="ubuntu-24.04",
    )
    db_session.add(image)
    await db_session.commit()
    return image


async def login(client: AsyncClient, email: str, password: str) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def fake_provider(monkeypatch):
    """Deterministic in-memory provider used to test control-plane logic."""
    from app.providers.base import InstanceSpec, InstanceState

    class FakeProvider:
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
        async def restore_backup(self, *a, **k): return {}
        async def console_target(self, name: str, cols: int, rows: int):
            from app.providers.base import ConsoleTarget

            return ConsoleTarget(
                kind="agent", url=f"wss://agent/v1/instances/{name}/console"
            )

    provider = FakeProvider()

    import app.services.node_service as _ns
    import app.services.vps_service as _vs

    monkeypatch.setattr(
        _ns.NodeService, "provider_for", classmethod(lambda cls, node: provider)
    )
    monkeypatch.setattr(
        _vs.NodeService, "provider_for", classmethod(lambda cls, node: provider)
    )
    return provider

