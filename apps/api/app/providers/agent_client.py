"""Authenticated HTTP client for CVX Node Agents.

Every request carries the node credential as a bearer token. The credential
is decrypted from the database only in memory, never logged.
"""

from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import NodeUnavailableError, ProviderError
from app.core.logging import get_logger

log = get_logger("cvx.agent")

AGENT_PORT = 9700


class AgentClient:
    def __init__(self, base_url: str, credential: str) -> None:
        settings = get_settings()
        verify: bool | str = True
        if base_url.startswith("https://") and settings.environment == "development":
            # Dev deployments commonly use self-signed certs on agents.
            verify = False
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {credential}"},
            timeout=settings.agent_timeout_seconds,
            verify=verify,
        )

    @classmethod
    def for_node(cls, public_ip: str, credential: str) -> "AgentClient":
        return cls(f"https://{public_ip}:{AGENT_PORT}", credential)

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as e:
            log.warning("agent unreachable path=%s err=%s", path, type(e).__name__)
            raise NodeUnavailableError(f"Node agent unreachable: {path}") from e
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                detail = body.get("error", {}).get("message", "") or str(body)
            except Exception:
                pass
            raise ProviderError(
                f"Agent returned {resp.status_code} for {path}",
                details={"agent_detail": detail[:500]},
            )
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return await self._request("POST", path, json=json, **kwargs)

    async def patch(self, path: str, json: Any = None, **kwargs: Any) -> Any:
        return await self._request("PATCH", path, json=json, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        return await self._request("DELETE", path, **kwargs)

    def ws_url(self, path: str) -> str:
        base = str(self._client.base_url).rstrip("/")
        ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_base}{path}"
