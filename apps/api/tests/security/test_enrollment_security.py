"""H9 — enrollment tokens are strictly single-use, expiring, revocable."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.core.security import generate_enrollment_token, hash_token
from app.models import EnrollmentToken, Node, NodeStatus
from tests.security.helpers import HELLO_BASE, enroll_node, login

pytestmark = pytest.mark.asyncio


async def _make_node_with_token(db_session) -> tuple[Node, str]:
    node = Node(
        name="EN-01", location="Testland", hostname="en01.cvx.test",
        public_ip="203.0.113.77", status=NodeStatus.PENDING,
    )
    db_session.add(node)
    await db_session.flush()
    token = generate_enrollment_token()
    db_session.add(
        EnrollmentToken(
            node_id=node.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
    )
    await db_session.commit()
    return node, token


def _hello(token: str) -> dict:
    return {**HELLO_BASE, "token": token}


async def test_token_cannot_be_reused(client: AsyncClient, owner_user, db_session) -> None:
    _, token = await _make_node_with_token(db_session)
    resp = await client.post("/api/v1/agent/enroll", json=_hello(token))
    assert resp.status_code == 200, resp.text
    resp = await client.post("/api/v1/agent/enroll", json=_hello(token))
    assert resp.status_code == 401


async def test_expired_token_rejected(client: AsyncClient, owner_user, db_session) -> None:
    node = Node(
        name="EN-02", location="T", hostname="en02.cvx.test",
        public_ip="203.0.113.78", status=NodeStatus.PENDING,
    )
    db_session.add(node)
    await db_session.flush()
    token = generate_enrollment_token()
    db_session.add(
        EnrollmentToken(
            node_id=node.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await db_session.commit()
    resp = await client.post("/api/v1/agent/enroll", json=_hello(token))
    assert resp.status_code == 401


async def test_revoked_token_rejected(client: AsyncClient, owner_user, db_session) -> None:
    node, token = await _make_node_with_token(db_session)
    result = await db_session.execute(
        EnrollmentToken.__table__.update()
        .where(EnrollmentToken.token_hash == hash_token(token))
        .values(revoked_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    resp = await client.post("/api/v1/agent/enroll", json=_hello(token))
    assert resp.status_code == 401


async def test_unknown_and_malformed_tokens_rejected(client: AsyncClient, owner_user) -> None:
    assert (await client.post("/api/v1/agent/enroll", json=_hello("cvxenroll_nope"))).status_code == 401
    assert (await client.post("/api/v1/agent/enroll", json=_hello(""))).status_code in (401, 422)
    assert (await client.post("/api/v1/agent/enroll", json={"token": "x" * 500})).status_code in (401, 422)


async def test_concurrent_enroll_single_winner(
    client: AsyncClient, owner_user, db_engine
) -> None:
    """Two parallel enroll attempts on one token: exactly one succeeds."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.services.node_service import NodeService

    async with async_sessionmaker(db_engine, expire_on_commit=False)() as session:
        node, token = await _make_node_with_token(session)

    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    from app.schemas.node import AgentHello

    hello = AgentHello(**{**HELLO_BASE, "lxd_version": "5.21"})

    async def attempt():
        async with factory() as session:
            try:
                _, cred = await NodeService.enroll(session, token=token, hello=hello)
                return "ok"
            except Exception as e:
                return type(e).__name__

    results = await asyncio.gather(attempt(), attempt())
    assert sorted(results) == ["AuthenticationError", "ok"], results


async def test_reenrollment_rotates_credential(
    client: AsyncClient, owner_user, db_session
) -> None:
    node, token = await _make_node_with_token(db_session)
    r1 = await client.post("/api/v1/agent/enroll", json=_hello(token))
    cred1 = r1.json()["credential"]

    # Admin issues a new token and the agent re-enrolls.
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(f"/api/v1/nodes/{node.id}/enrollment-token")
    assert resp.status_code == 200, resp.text
    new_token = resp.json()["token"]
    r2 = await client.post("/api/v1/agent/enroll", json=_hello(new_token))
    assert r2.status_code == 200, r2.text
    cred2 = r2.json()["credential"]
    assert cred1 != cred2

    # Old credential no longer authenticates.
    hb = {"agent_version": "1.0.0"}
    resp = await client.post(
        "/api/v1/agent/heartbeat", json=hb,
        headers={"Authorization": f"Bearer {cred1}"},
    )
    assert resp.status_code == 401
