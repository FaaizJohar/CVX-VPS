"""H2/M6/M7 — targeted rate limits; H8 — XFF spoofing resistance."""

import time

import pytest
from starlette.requests import Request

from app.core.rate_limit import _client_ip, enforce_rate_limit
from tests.security.helpers import login

pytestmark = pytest.mark.asyncio


class FakeRedis:
    """Minimal stand-in for the redis client used by the fixed-window limiter."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, float] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = time.time() + seconds


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()
    import app.core.rate_limit as rl

    monkeypatch.setattr(rl, "get_redis", lambda: r)
    return r


def _request_with_headers(xff: str | None = None, peer: str = "198.51.100.7") -> Request:
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 12345),
        "query_string": b"",
    }
    return Request(scope)


async def test_verify_password_is_limited(
    client, owner_user, fake_redis
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    for i in range(5):
        resp = await client.post(
            "/api/v1/auth/verify-password", json={"email": "x@example.com", "password": "wrong"}
        )
        assert resp.status_code == 401, resp.text
    resp = await client.post(
        "/api/v1/auth/verify-password", json={"email": "x@example.com", "password": "wrong"}
    )
    assert resp.status_code == 429, resp.text


async def test_reset_request_is_limited(client, owner_user, fake_redis) -> None:
    for i in range(5):
        resp = await client.post(
            "/api/v1/auth/password/reset-request",
            json={"email": f"u{i}@example.com"},
        )
        assert resp.status_code == 200, resp.text
    resp = await client.post(
        "/api/v1/auth/password/reset-request", json={"email": "u6@example.com"}
    )
    assert resp.status_code == 429, resp.text


async def test_vps_create_is_limited_per_user(
    client, owner_user, ubuntu_image, fake_provider, fake_redis
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    from tests.security.helpers import enroll_node

    node = await enroll_node(client)
    last_resp = None
    for i in range(10):
        last_resp = await client.post("/api/v1/vps", json={
            "node_id": node["id"], "image_id": str(ubuntu_image.id),
            "name": f"rl-{i}", "hostname": f"rl{i}.cvx.test",
        })
        assert last_resp.status_code == 202, last_resp.text
    last_resp = await client.post("/api/v1/vps", json={
        "node_id": node["id"], "image_id": str(ubuntu_image.id),
        "name": "rl-over", "hostname": "rlover.cvx.test",
    })
    assert last_resp.status_code == 429, last_resp.text


async def test_xff_rightmost_entry_wins(monkeypatch) -> None:
    """Behind a proxy the rightmost XFF entry (set by our nginx) must be used."""
    import app.core.rate_limit as rl

    monkeypatch.setattr(rl, "get_settings_safe", lambda: type("S", (), {"behind_proxy": True})())

    req = _request_with_headers(xff="1.2.3.4, 10.0.0.9, 203.0.113.5")
    assert _client_ip(req) == "203.0.113.5"

    # Attacker-controlled single entry still wins when there is no proxy append —
    # but with behind_proxy set, deployment guarantees our proxy appended the last.
    req2 = _request_with_headers(xff="6.6.6.6")
    assert _client_ip(req2) == "6.6.6.6"


async def test_xff_ignored_without_proxy_flag(monkeypatch) -> None:
    import app.core.rate_limit as rl

    monkeypatch.setattr(rl, "get_settings_safe", lambda: type("S", (), {"behind_proxy": False})())
    req = _request_with_headers(xff="6.6.6.6", peer="198.51.100.7")
    assert _client_ip(req) == "198.51.100.7"


async def test_enforce_rate_limit_counts_and_raises(fake_redis) -> None:
    from app.core.errors import RateLimitError

    for _ in range(3):
        await enforce_rate_limit("unit:test", limit=3, window_seconds=60)
    with pytest.raises(RateLimitError):
        await enforce_rate_limit("unit:test", limit=3, window_seconds=60)
