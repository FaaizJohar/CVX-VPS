"""System metrics collection for heartbeats."""

import platform
import time
from typing import Any

import psutil


def collect_system_info() -> dict[str, Any]:
    uname = platform.uname()
    cpu_model: str | None = None
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    cpu_model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "hostname": uname.node,
        "os_name": uname.system,
        "os_version": uname.release,
        "kernel_version": uname.release,
        "architecture": uname.machine,
        "cpu_model": cpu_model,
        "cpu_cores": psutil.cpu_count(logical=True),
        "ram_total_mb": int(mem.total // (1024 * 1024)),
        "storage_total_gb": round(disk.total / (1024**3), 1),
    }


def collect_load() -> dict[str, Any]:
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    net1 = _net_io()
    time.sleep(0.5)
    net2 = _net_io()
    dt = max(net2[2] - net1[2], 0.001)
    load1, _, _ = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0.0, 0.0, 0.0)
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_used_mb": int(mem.used // (1024 * 1024)),
        "ram_total_mb": int(mem.total // (1024 * 1024)),
        "swap_used_mb": int(swap.used // (1024 * 1024)),
        "storage_used_gb": round(disk.used / (1024**3), 1),
        "storage_total_gb": round(disk.total / (1024**3), 1),
        "net_rx_bps": max(0, int((net2[0] - net1[0]) / dt)),
        "net_tx_bps": max(0, int((net2[1] - net1[1]) / dt)),
        "load1": round(float(load1), 2),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }


def _net_io() -> tuple[int, int, float]:
    counters = psutil.net_io_counters()
    return counters.bytes_recv, counters.bytes_sent, time.monotonic()


def detect_public_ip() -> str | None:
    """Best-effort public IP discovery via a configurable echo service.

    Never fatal — the control plane accepts nodes whose public IP cannot be
    determined (NAT'd or offline environments).
    """
    import os

    import httpx

    urls = [
        u.strip()
        for u in os.getenv(
            "CVX_PUBLIC_IP_URLS",
            "https://api.ipify.org,https://ipv4.icanhazip.com",
        ).split(",")
        if u.strip()
    ]
    for url in urls[:3]:
        try:
            resp = httpx.get(url, timeout=5.0)
            value = resp.text.strip()
            if resp.status_code == 200 and 0 < len(value) <= 64:
                import ipaddress as _ip

                _ip.ip_address(value)  # validate before reporting
                return value
        except Exception:
            continue
    return None
