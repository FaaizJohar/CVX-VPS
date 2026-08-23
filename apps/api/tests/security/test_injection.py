"""Injection / path-traversal resistance through API-reachable inputs."""

import pytest
from httpx import AsyncClient

from tests.security.helpers import create_vps, enroll_node, login

pytestmark = pytest.mark.asyncio


PAYLOADS = [
    "; rm -rf /",
    "$(whoami)",
    "`id`",
    "../../etc/passwd",
    "\n; reboot",
    "x' OR '1'='1",
    "${JNDI:ldap://evil}",
    "\x00null",
]


async def test_hostname_metacharacters_stay_data(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    """Hostile hostnames are either rejected by schema or stored verbatim — never executed."""
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    for p in PAYLOADS:
        resp = await create_vps(
            client, node["id"], str(ubuntu_image.id),
            name="inj", hostname=f"h{p}.cvx.test" if "\n" not in p else "h.cvx.test",
        )
        # 422 (schema) or 200 (stored verbatim) — never a 500 from injection.
        assert resp.status_code in (200, 422), f"{p!r}: {resp.status_code} {resp.text}"
        if resp.status_code == 200:
            spec = fake_provider.created[-1]
            # Value reached the provider as inert data.
            assert spec.hostname in (f"h{p}.cvx.test", "h.cvx.test")


async def test_dns_servers_reject_non_ips(
    client: AsyncClient, owner_user, ubuntu_image
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    image_id = str(ubuntu_image.id)
    for bad in ("8.8.8.8; reboot", "$(reboot)", "not-an-ip", "1.2.3.4/32"):
        resp = await client.post("/api/v1/vps", json={
            "node_id": node["id"], "image_id": image_id,
            "name": "dns-inj", "hostname": "dns.cvx.test",
            "dns_servers": [bad],
        })
        assert resp.status_code == 422, f"{bad!r}: {resp.text}"


async def test_reserved_config_prefixes_require_admin(
    client: AsyncClient, owner_user, plain_user, ubuntu_image, fake_provider
) -> None:
    # Owner prepares an online node.
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    await client.post("/api/v1/auth/logout")

    # Plain user creates their own VPS.
    await login(client, "user@example.com", "UserPass1234!")
    resp = await create_vps(client, node["id"], str(ubuntu_image.id))
    assert resp.status_code == 200, resp.text
    vps_id = resp.json()["id"]

    for key in ("raw.lxc", "security.privileged", "volatile.base_image", "boot.autostart"):
        resp = await client.put(
            f"/api/v1/vps/{vps_id}/config", json={"config": {key: "whatever"}}
        )
        assert resp.status_code == 403, f"{key}: {resp.text}"

    # Non-reserved keys are allowed for the owner of the VPS.
    resp = await client.put(
        f"/api/v1/vps/{vps_id}/config", json={"config": {"user.foo": "bar"}}
    )
    assert resp.status_code == 200, resp.text


async def test_snapshot_names_reject_traversal(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    resp = await create_vps(client, node["id"], str(ubuntu_image.id))
    vps_id = resp.json()["id"]

    for bad in ("../../escape", "a/b", "..", ".hidden-start", "", "x" * 200):
        resp = await client.post(f"/api/v1/vps/{vps_id}/snapshots", json={"name": bad})
        assert resp.status_code in (404, 422), f"{bad!r}: {resp.status_code}"


async def test_search_wildcards_are_escaped(
    client: AsyncClient, owner_user, ubuntu_image, fake_provider
) -> None:
    await login(client, "owner@example.com", "OwnerPass123!")
    node = await enroll_node(client)
    for i in range(3):
        await create_vps(client, node["id"], str(ubuntu_image.id),
                         name=f"srv-{i}", hostname=f"s{i}.cvx.test")

    resp = await client.get("/api/v1/vps?search=srv-%")
    body = resp.json()
    # Literal '%' must not match everything.
    assert body["total"] == 0
    resp = await client.get("/api/v1/vps?search=srv-_")
    assert resp.json()["total"] == 0
    resp = await client.get("/api/v1/vps?search=srv-1")
    assert resp.json()["total"] == 1
