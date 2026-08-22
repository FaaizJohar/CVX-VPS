import pytest
from httpx import AsyncClient

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def test_rbac_user_cannot_access_admin_endpoints(
    client: AsyncClient, plain_user
) -> None:
    await login(client, "user@example.com", "UserPass1234!")
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 403
    resp = await client.get("/api/v1/logs/audit")
    assert resp.status_code == 403


async def test_admin_can_list_users(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert "owner@example.com" in emails


async def test_node_create_requires_admin(client: AsyncClient, plain_user) -> None:
    await login(client, "user@example.com", "UserPass1234!")
    resp = await client.post(
        "/api/v1/nodes",
        json={
            "name": "IN-01",
            "location": "Mumbai",
            "hostname": "in01.cvx.test",
            "public_ip": "103.1.2.3",
        },
    )
    assert resp.status_code == 403


async def test_owner_can_demote_only_via_owner(
    client: AsyncClient, owner_user, db_session
) -> None:
    from app.core.security import hash_password
    from app.models import User, UserRole

    admin = User(
        email="admin@example.com",
        password_hash=hash_password("AdminPass123!"),
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    await db_session.commit()

    await login(client, "admin@example.com", "AdminPass123!")
    # Admin cannot modify an owner.
    me = await client.get("/api/v1/auth/me")
    owner_id = None
    users = (await client.get("/api/v1/users")).json()
    for u in users:
        if u["role"] == "owner":
            owner_id = u["id"]
    resp = await client.patch(
        f"/api/v1/users/{owner_id}", json={"role": "user"}
    )
    assert resp.status_code == 403

