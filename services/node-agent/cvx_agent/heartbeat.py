"""Heartbeat loop: reports metrics + instance inventory to the control plane."""

import asyncio

import httpx

from cvx_agent.config import AgentConfig
from cvx_agent.lxd import LXDClient
from cvx_agent.metrics import collect_load


async def heartbeat_loop(stop: asyncio.Event) -> None:
    cfg = AgentConfig.load()
    if cfg is None or not cfg.credential:
        return
    headers = {"Authorization": f"Bearer {cfg.credential}"}
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
                await http.post("/api/v1/agent/heartbeat", json=payload)
            except Exception:
                # Never crash the agent on control-plane hiccups.
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pass


def _version() -> str:
    from cvx_agent import __version__

    return __version__
