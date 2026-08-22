"""C1 — privilege escalation via user PATCH must be impossible."""

import pytest
from httpx import AsyncClient

from tests.security.helpers import login

pytestmark = pytest.mark.asyncio


async def _admin(client: AsyncClient, db_session) -> None:
    """Create a second-level admin (not owner) and log in as them."""
    from app.core.security import hash_password
    from app.models import User, UserRole

    admin = User(
        email="secadmin@example.com",
        password_hash=hash_password("AdminPass123!"),
        name="Sec Admin",
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    await db_session.commit()
    await login(client, "secadmin@example.com", "AdminPass123!")


async def _owner_user_id(client: AsyncClient) -> str:
    resp = await client.get("/api/v1/auth/me")
    return resp.json()["user"]["id"]


async def test_admin_cannot_grant_owner_role(
    client: AsyncClient, owner_user, plain_user, db_session
) -> None:
    await _admin(client, db_session)
    target = plain_user.id if hasattr(plain_user, "id") else plain_user["id"]
    resp = await client.patch(f"/api/v1/users/{target}", json={"role": "owner"})
    assert resp.status_code == 403, resp.text

    # Verify the role really did not change.
    resp = await client.get(f"/api/v1/users/{target}")
    assert resp.json()["role"] == "user"


async def test_admin_cannot_disable_owner(
    client: AsyncClient, owner_user, db_session
) -> None:
    await _admin(client, db_session)
    owner_id = str(owner_user.id)
    resp = await client.patch(f"/api/v1/users/{owner_id}", json={"status": "disabled"})
    assert resp.status_code == 403, resp.text
    resp = await client.get(f"/api/v1/users/{owner_id}")
    assert resp.json()["status"] == "active"


async def test_admin_cannot_change_owner_password(
    client: AsyncClient, owner_user, db_session
) -> None:
    await _admin(client, db_session)
    owner_id = str(owner_user.id)
    resp = await client.patch(
        f"/api/v1/users/{owner_id}", json={"password": "PwnedPass123!"}
    )
    assert resp.status_code == 403, resp.text


async def test_owner_can_grant_owner_role(
    client: AsyncClient, owner_user, plain_user
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    target = str(plain_user.id)
    resp = await client.patch(f"/api/v1/users/{target}", json={"role": "owner"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "owner"


async def test_last_owner_cannot_self_demote(
    client: AsyncClient, owner_user
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    me = await _owner_user_id(client)
    resp = await client.patch(f"/api/v1/users/{me}", json={"role": "admin"})
    assert resp.status_code == 409, resp.text
    resp = await client.patch(f"/api/v1/users/{me}", json={"status": "disabled"})
    assert resp.status_code == 409, resp.text


async def test_admin_still_controls_regular_users(
    client: AsyncClient, owner_user, plain_user, db_session
) -> None:
    await _admin(client, db_session)
    target = str(plain_user.id)
    resp = await client.patch(f"/api/v1/users/{target}", json={"name": "Renamed"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed"
