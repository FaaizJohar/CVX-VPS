"""Enrollment flow: exchange a one-time token for a permanent credential."""

import sys

import httpx

from cvx_agent.config import AgentConfig, CONFIG_DIR
from cvx_agent.metrics import collect_system_info, detect_public_ip


def detect_lxd_version() -> str | None:
    import asyncio

    from cvx_agent.lxd import LXDClient

    async def _run() -> str | None:
        try:
            client = LXDClient()
        except RuntimeError:
            return None
        try:
            info = await client.server_info()
            return info.get("lxd_version")
        except Exception:
            return None
        finally:
            await client.close()

    return asyncio.run(_run())


def enroll(control_plane: str, token: str) -> None:
    control_plane = control_plane.rstrip("/")
    print(f"[*] CVX Agent — enrolling against {control_plane}")

    lxd_version = detect_lxd_version()
    if lxd_version is None:
        print("[!] ERROR: LXD not detected on this machine.")
        print("    Install it first:  sudo snap install lxd && sudo lxd init")
        sys.exit(1)
    print(f"[+] LXD detected (version {lxd_version})")

    hello = collect_system_info()
    payload = {
        "token": token,
        "agent_version": _agent_version(),
        **hello,
        "lxd_version": lxd_version,
    }

    print("[*] Detecting public IP ...")
    public_ip = detect_public_ip()
    if public_ip:
        payload["public_ip"] = public_ip
        print(f"[+] Public IP detected ({public_ip})")
    else:
        print("[!] Public IP could not be automatically determined (continuing)")

    resp = httpx.post(
        f"{control_plane}/api/v1/agent/enroll", json=payload, timeout=30.0
    )
    if resp.status_code != 200:
        try:
            detail = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            detail = resp.text
        print(f"[!] Enrollment failed: HTTP {resp.status_code} — {detail}")
        sys.exit(1)

    data = resp.json()
    cfg = AgentConfig(control_plane=control_plane, credential=data["credential"])
    cfg.save()
    print(f"[+] Enrolled as node '{data['node_name']}' ({data['node_id']})")
    print(f"[+] Credential stored at {CONFIG_DIR / 'credential'} (mode 0600)")
    print("[*] Start the service:  sudo systemctl enable --now cvx-agent")


def _agent_version() -> str:
    from cvx_agent import __version__

    return __version__
