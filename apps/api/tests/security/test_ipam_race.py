"""H1 — IP allocation must be atomic under concurrency."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import IPAddress, IPStatus, Node, NodeStatus, VPS, VPSStatus
from tests.security.helpers import create_vps, enroll_node, login

pytestmark = pytest.mark.asyncio


async def _add_ip(db_session, node: Node, address: str) -> IPAddress:
    ip = IPAddress(
        node_id=node.id,
        family=4,
        address=address,
        status=IPStatus.AVAILABLE,
    )
    db_session.add(ip)
    await db_session.commit()
    return ip


async def test_same_ip_cannot_be_assigned_twice_sequentially(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    ip = await _add_ip(
        db_session, await db_session.get(Node, uuid.UUID(node["id"])), "203.0.113.99"
    )

    resp = await create_vps(
        client, node["id"], str(ubuntu_image.id), name="first", ipv4="203.0.113.99"
    )
    assert resp.status_code == 200, resp.text
    first_id = resp.json()["id"]

    # Second claim on the same address must fail cleanly.
    resp = await create_vps(
        client, node["id"], str(ubuntu_image.id), name="second", ipv4="203.0.113.99"
    )
    assert resp.status_code == 422, resp.text

    await db_session.refresh(ip)
    assert str(ip.vps_id) == first_id
    assert ip.status == IPStatus.ASSIGNED


async def test_concurrent_create_race_yields_single_owner(
    tmp_path, owner_user, ubuntu_image, fake_provider
) -> None:
    """Two parallel creates requesting the same IP: exactly one wins.

    Runs at service level against a file-backed SQLite database in WAL mode so
    each attempt gets its own connection and a genuine independent transaction.
    (The shared in-memory engine used by the HTTP fixtures has a single pooled
    connection — concurrent "transactions" there are really one transaction,
    which would make this test measure fixture artifacts instead of the claim.)
    """
    import uuid as _uuid

    from sqlalchemy import text as _text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.security import hash_password
    from app.db.base import Base
    from app.models import Image, User, UserRole
    from app.schemas.vps import VPSCreate
    from app.services.vps_service import VPSService
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'race.db'}",
        connect_args={"timeout": 30},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        node = Node(
            name="race-node", location="L", hostname="race.cvx.test",
            public_ip="203.0.113.1", status=NodeStatus.ONLINE,
            cpu_cores=64, ram_total_mb=262144, storage_total_gb=4096,
        )
        user = User(
            email="racer@example.com", password_hash=hash_password("RacerPass123!"),
            name="Racer", role=UserRole.OWNER,
        )
        image = Image(
            alias="race-img", display_name="Race", os_family="ubuntu",
            version="24.04", source_identifier="ubuntu-24.04",
        )
        session.add_all([node, user, image])
        await session.flush()
        ip = IPAddress(
            node_id=node.id, family=4, address="203.0.113.100",
            status=IPStatus.AVAILABLE,
        )
        session.add(ip)
        await session.commit()
        node_id, user_id, image_id = node.id, user.id, image.id

    data = VPSCreate(
        node_id=node_id, image_id=image_id, name="race", hostname="race.cvx.test",
        ipv4="203.0.113.100",
    )

    async def attempt(tag: str) -> dict:
        async with factory() as session:
            racer = await session.get(User, user_id)
            try:
                vps = await VPSService.create_vps(session, data=data, owner=racer)
                await session.commit()
                return {"tag": tag, "vps_id": str(vps.id), "error": None}
            except Exception as e:
                await session.rollback()
                return {"tag": tag, "vps_id": None, "error": type(e).__name__}

    outcomes = await asyncio.gather(attempt("A"), attempt("B"))
    winners = [o for o in outcomes if o["error"] is None]
    losers = [o for o in outcomes if o["error"] is not None]

    assert len(winners) == 1, outcomes
    assert len(losers) == 1, outcomes
    assert losers[0]["error"] == "ValidationError", outcomes

    # Exactly one VPS row exists and it owns the address.
    async with factory() as session:
        vps_rows = (
            await session.execute(select(VPS).where(VPS.name == "race"))
        ).scalars().all()
        assert len(vps_rows) == 1
        assert str(vps_rows[0].id) == winners[0]["vps_id"]

        final_ip = (
            await session.execute(
                select(IPAddress).where(IPAddress.address == "203.0.113.100")
            )
        ).scalars().one()
        assert final_ip.status == IPStatus.ASSIGNED
        assert str(final_ip.vps_id) == winners[0]["vps_id"]

    await engine.dispose()


async def test_delete_releases_ip_for_reuse(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider, db_session
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    await _add_ip(
        db_session, await db_session.get(Node, uuid.UUID(node["id"])), "203.0.113.101"
    )

    resp = await create_vps(
        client, node["id"], str(ubuntu_image.id), name="tmp", ipv4="203.0.113.101"
    )
    vps_id = resp.json()["id"]
    resp = await client.delete(f"/api/v1/vps/{vps_id}")
    assert resp.status_code == 200

    resp = await create_vps(
        client, node["id"], str(ubuntu_image.id), name="tmp2", ipv4="203.0.113.101"
    )
    assert resp.status_code == 200, resp.text
