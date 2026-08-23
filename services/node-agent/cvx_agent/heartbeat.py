"""Heartbeat loop: reports metrics + instance inventory to the control plane."""

import asyncio

import httpx

from cvx_agent.config import AgentConfig
from cvx_agent.lxd import LXDClient
from cvx_agent.metrics import collect_load, detect_public_ip


async def heartbeat_loop(stop: asyncio.Event) -> None:
    global _counter
    cfg = AgentConfig.load()
    if cfg is None or not cfg.credential:
        return
    headers = {"Authorization": f"Bearer {cfg.credential}"}
    public_ip = detect_public_ip()
    async with httpx.AsyncClient(
        base_url=cfg.control_plane.rstrip("/"), headers=headers, timeout=20.0
    ) as http, LXDClient() as lxd:
        while not stop.is_set():
            try:
                instances = await lxd.list_instances()
                payload = {
                    "agent_version": _version(),
                    **collect_load(),
                    "instances": instances,
                }
                # Refresh the public IP occasionally (DHCP rebinds happen);
                # cheap, non-fatal if it fails.
                if public_ip is None or _counter % 40 == 39:
                    public_ip = detect_public_ip()
                if public_ip:
                    payload["public_ip"] = public_ip
                _counter += 1
                await http.post("/api/v1/agent/heartbeat", json=payload)
            except Exception:
                # Never crash the agent on control-plane hiccups.
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass


_counter = 0


def _version() -> str:
    from cvx_agent import __version__

    return __version__
