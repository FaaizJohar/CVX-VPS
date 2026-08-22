import pytest
from httpx import AsyncClient

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def test_login_success_and_me(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "owner@example.com"
    assert resp.json()["user"]["role"] == "owner"


async def test_login_wrong_password(client: AsyncClient, owner_user) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_login_unknown_user_same_error(client: AsyncClient, owner_user) -> None:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )
    assert resp.status_code == 401


async def test_unauthenticated_me(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_logout_invalidates_session(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_password_change_requires_current(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "wrong", "new_password": "NewPass12345!"},
    )
    assert resp.status_code == 401
    resp = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "OwnerPass123!", "new_password": "NewPass12345!"},
    )
    assert resp.status_code == 200
    # Old session revoked.
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    # New password works.
    await login(client, "owner@example.com", "NewPass12345!")


async def test_reset_flow(client: AsyncClient, owner_user) -> None:
    # The reset request endpoint must not reveal account existence.
    resp = await client.post(
        "/api/v1/auth/password/reset-request", json={"email": "ghost@example.com"}
    )
    assert resp.status_code == 200

    # Confirm with an invalid token fails cleanly.
    resp = await client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"token": "bogus-token", "new_password": "Whatever123!"},
    )
    assert resp.status_code == 401

