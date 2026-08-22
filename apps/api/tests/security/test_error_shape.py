"""L3/L4 — readiness endpoint, request-id correlation, error envelope shape."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_error_envelope_shape(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/vps/00000000-0000-0000-0000-000000000000")
    assert resp.status_code in (401, 403)

    # Unauthenticated error has the canonical envelope.
    if resp.status_code == 401:
        err = resp.json()["error"]
        assert set(err.keys()) >= {"code", "message"}
        assert err["code"] == "unauthenticated"


async def test_request_id_echoed_and_attached(client: AsyncClient, owner_user) -> None:
    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "OwnerPass123!"},
    )
    resp = await client.get(
        "/api/v1/vps/00000000-0000-0000-0000-000000000000",
        headers={"x-request-id": "trace-me-123"},
    )
    assert resp.status_code == 404
    assert resp.headers.get("x-request-id") == "trace-me-123"
    err = resp.json()["error"]
    assert err.get("request_id") == "trace-me-123"


async def test_server_generated_request_id_when_absent(client: AsyncClient, owner_user) -> None:
    await client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "OwnerPass123!"},
    )
    resp = await client.get("/api/v1/vps/00000000-0000-0000-0000-000000000000")
    rid = resp.headers.get("x-request-id")
    assert rid and len(rid) >= 16
    assert resp.json()["error"].get("request_id") == rid


async def test_readyz_reports_checks(client: AsyncClient) -> None:
    # Redis is not running in tests; /readyz should honestly report 503.
    resp = await client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["redis"] == "unavailable"


async def test_healthz_ok(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
