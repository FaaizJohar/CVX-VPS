import asyncio
import os
from collections.abc import AsyncIterator

# Must be set before app.config is first imported/cached.
os.environ.setdefault("CVX_SESSION_COOKIE_SECURE", "false")
os.environ.setdefault("CVX_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("CVX_ALLOW_PRIVATE_NODE_IPS", "true")

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

