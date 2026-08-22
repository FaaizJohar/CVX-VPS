import pytest
from httpx import AsyncClient

HELLO_BASE = {
    "agent_version": "1.0.0",
    "hostname": "sec01.cvx.test",
    "os_name": "Debian",
    "os_version": "12",
    "kernel_version": "6.1",
    "architecture": "x86_64",
    "lxd_version": "5.21",
    "cpu_cores": 8,
    "ram_total_mb": 16384,
    "storage_total_gb": 500.0,
}


async def login(client: AsyncClient, email: str, password: str) -> None:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text


async def enroll_node(client: AsyncClient, name: str = "SEC-01", **hello_overrides) -> dict:
    """Create a node via the admin API and enroll its agent.

    Returns the node dict with an extra ``credential`` key (the agent secret).
    """
    resp = await client.post(
        "/api/v1/nodes",
        json={
            "name": name,
            "location": "Testland",
            "hostname": f"{name.lower()}.cvx.test",
            "public_ip": "203.0.113.50",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    hello = {**HELLO_BASE, "token": data["enrollment"]["token"], **hello_overrides}
    resp = await client.post("/api/v1/agent/enroll", json=hello)
    assert resp.status_code == 200, resp.text
    node = dict(data["node"])
    node["credential"] = resp.json()["credential"]
    return node


async def create_vps(client: AsyncClient, node_id: str, image_id: str, **overrides):
    payload = {
        "node_id": node_id,
        "image_id": image_id,
        "name": "sec-01",
        "hostname": "sec01.cvx.test",
        "cpu_limit": 1,
        "ram_mb": 1024,
        "disk_gb": 10,
    }
    payload.update(overrides)
    return await client.post("/api/v1/vps", json=payload)
