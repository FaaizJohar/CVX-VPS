"""Local compute capability probing.

Determines whether the control-plane host can actually run local VPSes by
probing the real backend (LXD over its unix socket) instead of guessing from
virtualization markers like /dev/kvm. Containers-on-containers are fine for
LXD's unprivileged containers; nested virtualization is NOT required, so KVM
is deliberately never consulted here.

States:
- NOT_CONFIGURED : feature disabled or no LXD socket mounted
- UNAVAILABLE    : socket exists but the LXD daemon does not answer
- DEGRADED       : daemon answers but something required is missing/broken
- READY          : everything needed for instance creation is in place

Results are cached (TTL) so dashboards never hit LXD per request; the admin
refresh endpoint forces a fresh probe.
"""

import asyncio
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("cvx.local")

STATE_NOT_CONFIGURED = "not_configured"
STATE_UNAVAILABLE = "unavailable"
STATE_DEGRADED = "degraded"
STATE_READY = "ready"

_CACHE_TTL_SECONDS = 45.0
_cache_lock = asyncio.Lock()
_cache: dict[str, Any] = {"data": None, "ts": 0.0}


def invalidate_cache() -> None:
    _cache["data"] = None
    _cache["ts"] = 0.0


async def get_local_capability(*, force: bool = False) -> dict[str, Any]:
    """Cached capability snapshot. Never raises."""
    async with _cache_lock:
        now = time.monotonic()
        if (
            not force
            and _cache["data"] is not None
            and now - _cache["ts"] < _CACHE_TTL_SECONDS
        ):
            return _cache["data"]
        try:
            data = await _probe()
        except Exception as e:  # defensive: dashboards must not 500 on this
            log.warning("local capability probe crashed: %s", e)
            data = {
                "state": STATE_UNAVAILABLE,
                "available": False,
                "reason": "capability_probe_failed",
                "message": "The local compute probe could not complete.",
                "diagnostics": [
                    {"check": "probe", "ok": False, "detail": str(e)[:300]}
                ],
                "resources": None,
            }
        _cache["data"] = data
        _cache["ts"] = now
        return data


def _diag(check: str, ok: bool, detail: str, *, hint: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"check": check, "ok": ok, "detail": detail}
    if hint:
        d["hint"] = hint
    return d


async def _probe() -> dict[str, Any]:
    settings = get_settings()

    if not settings.enable_local_deployment:
        return {
            "state": STATE_NOT_CONFIGURED,
            "available": False,
            "reason": "disabled",
            "message": "Local compute is turned off on this installation.",
            "diagnostics": [
                _diag(
                    "feature_flag",
                    False,
                    "CVX_ENABLE_LOCAL_DEPLOYMENT is not enabled.",
                    hint="Set CVX_ENABLE_LOCAL_DEPLOYMENT=true and restart the panel.",
                )
            ],
            "resources": None,
        }

    from app.providers.local_lxd import LocalLXDClient, find_local_socket, local_capacity

    socket_path = find_local_socket()
    if socket_path is None:
        return {
            "state": STATE_NOT_CONFIGURED,
            "available": False,
            "reason": "no_lxd_socket",
            "message": "No LXD unix socket was found on the control-plane host.",
            "diagnostics": [
                _diag(
                    "lxd_socket",
                    False,
                    "Looked for the LXD socket at the usual snap/apt/incus paths "
                    "(override with CVX_LXD_SOCKET_PATH).",
                    hint="Install LXD on the panel host, or bind-mount the host "
                    "socket into the API container (see docker-compose.local.yml).",
                )
            ],
            "resources": None,
        }

    diagnostics: list[dict[str, Any]] = []
    client = LocalLXDClient()
    try:
        # --- daemon reachability ------------------------------------------
        try:
            info = await client.server_info()
        except Exception as e:
            return {
                "state": STATE_UNAVAILABLE,
                "available": False,
                "reason": "lxd_unreachable",
                "message": "Found an LXD socket, but the LXD daemon did not answer.",
                "diagnostics": [
                    _diag(
                        "lxd_daemon", False, f"LXD API error: {str(e)[:300]}",
                        hint="Check that the LXD daemon is running on the host.",
                    )
                ],
                "resources": None,
            }
        diagnostics.append(
            _diag("lxd_daemon", True, f"LXD {info.get('lxd_version') or 'unknown'} answering")
        )

        degraded_reasons: list[str] = []

        # --- storage pool ---------------------------------------------------
        pool_names: list[str] = []
        try:
            resp = await client._request("GET", "/1.0/storage-pools")
            pool_names = [p.split("/1.0/storage-pools/")[-1] for p in resp.get("storage_pools", [])]
        except Exception as e:
            degraded_reasons.append("storage_pool_unreadable")
            diagnostics.append(
                _diag("storage_pool", False, f"Could not list storage pools: {str(e)[:200]}")
            )
        else:
            if pool_names:
                diagnostics.append(
                    _diag("storage_pool", True, ", ".join(pool_names[:5]))
                )
            else:
                degraded_reasons.append("no_storage_pool")
                diagnostics.append(
                    _diag(
                        "storage_pool", False, "No LXD storage pool exists yet.",
                        hint="Run `lxd init --auto` on the host to create one.",
                    )
                )

        # --- default bridge network ----------------------------------------
        bridge_ok = False
        try:
            resp = await client._request("GET", "/1.0/networks")
            names = [n.rsplit("/", 1)[-1] for n in resp.get("networks", [])]
            managed = []
            for name in names:
                if name in ("lo",):
                    continue
                try:
                    net = await client._request("GET", f"/1.0/networks/{name}")
                    if (net.get("config") or {}).get("managed") == "true":
                        managed.append(name)
                except Exception:
                    continue
            bridge_ok = bool(managed)
            if managed:
                diagnostics.append(_diag("bridge_network", True, ", ".join(managed[:5])))
            else:
                degraded_reasons.append("no_managed_bridge")
                diagnostics.append(
                    _diag(
                        "bridge_network", False, "No managed LXD bridge found.",
                        hint="`lxd init --auto` creates lxdbr0 with DHCP+NAT.",
                    )
                )
        except Exception as e:
            degraded_reasons.append("network_probe_failed")
            diagnostics.append(
                _diag("bridge_network", False, f"Could not list networks: {str(e)[:200]}")
            )

        state = STATE_DEGRADED if degraded_reasons else STATE_READY
        message = (
            "Local compute is ready."
            if state == STATE_READY
            else "LXD answers, but VPS creation will fail until the listed issues are fixed."
        )
        resources: dict[str, Any] | None = None
        if not degraded_reasons or "no_storage_pool" not in degraded_reasons:
            try:
                cap = await local_capacity()
                resources = {
                    "cpu_cores": cap.get("cpu_cores"),
                    "ram_total_mb": cap.get("ram_total_mb"),
                    "storage_total_gb": cap.get("storage_total_gb"),
                    "storage_used_gb": cap.get("storage_used_gb"),
                }
            except Exception as e:
                degraded_reasons.append("capacity_probe_failed")
                state = STATE_DEGRADED
                diagnostics.append(
                    _diag("capacity", False, f"Capacity probe failed: {str(e)[:200]}")
                )

        return {
            "state": state,
            "available": state == STATE_READY,
            "reason": degraded_reasons[0] if degraded_reasons else None,
            "reasons": degraded_reasons,
            "message": message,
            "diagnostics": diagnostics,
            "resources": resources,
            "lxd_version": info.get("lxd_version"),
            "socket_path": str(socket_path),
            **({
                k: info[k] for k in ("hostname", "os_name") if info.get(k)
            }),
        }
    finally:
        try:
            await client.close()
        except Exception:
            pass
