import pytest
from httpx import AsyncClient

from tests.conftest import login

pytestmark = pytest.mark.asyncio


async def test_ip_pool_add_and_validation(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/ips",
        json={"addresses": ["203.0.113.10", "203.0.113.11", "bogus"], "gateway": "203.0.113.1"},
    )
    assert resp.status_code == 422

    resp = await client.post(
        "/api/v1/ips",
        json={"addresses": ["203.0.113.10", "203.0.113.11", "2001:db8::1"]},
    )
    assert resp.status_code == 201
    assert resp.json()["added"] == 3

    # Duplicates skipped.
    resp = await client.post("/api/v1/ips", json={"addresses": ["203.0.113.10"]})
    assert resp.json()["skipped"] == ["203.0.113.10"]

    resp = await client.get("/api/v1/ips?family=4")
    assert len(resp.json()) == 2


async def test_reserve_release_flow(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    await client.post("/api/v1/ips", json={"addresses": ["198.51.100.5"]})
    ips = (await client.get("/api/v1/ips")).json()
    ip_id = ips[0]["id"]

    resp = await client.post(f"/api/v1/ips/{ip_id}/reserve")
    assert resp.json()["status"] == "reserved"

    resp = await client.post(f"/api/v1/ips/{ip_id}/release")
    assert resp.json()["status"] == "available"


async def test_api_key_lifecycle(client: AsyncClient, owner_user) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    resp = await client.post(
        "/api/v1/apikeys", json={"name": "ci-key", "scopes": ["vps:read"]}
    )
    assert resp.status_code == 201
    body = resp.json()
    key = body["key"]
    assert key.startswith(body["prefix"])

    # Use the API key without a session cookie.
    client.cookies.clear()
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"}
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "owner@example.com"

    resp = await client.get("/api/v1/apikeys", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 200
    assert any(k["name"] == "ci-key" for k in resp.json())

    key_id = resp.json()[0]["id"]
    resp = await client.delete(
        f"/api/v1/apikeys/{key_id}", headers={"Authorization": f"Bearer {key}"}
    )
    assert resp.status_code == 200

    # Revoked key no longer authenticates.
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 401


async def test_invalid_api_key_rejected(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer cvx_abcd_notreal"}
    )
    assert resp.status_code == 401

