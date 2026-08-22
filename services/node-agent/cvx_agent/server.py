"""CVX Node Agent server.

Exposes an authenticated HTTPS API used exclusively by the control plane.
There is NO arbitrary command execution endpoint — by design.
"""

import asyncio
import json
import os
import re
import signal
import ssl
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import ORJSONResponse

from cvx_agent.config import AgentConfig
from cvx_agent.lxd import LXDError, LXDClient
from cvx_agent.metrics import collect_load, collect_system_info


class AgentState:
    lxd: LXDClient | None = None
    credential: str = ""


state = AgentState()

# Instance/snapshot/backup names accepted from the control plane. Everything
# is interpolated into LXD API paths and argv, so keep this allowlist tight.
INSTANCE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
SNAPSHOT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


def validate_instance_name(name: object) -> str:
    if not isinstance(name, str) or not INSTANCE_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="Invalid instance name.")
    return name


def validate_snapshot_name(name: object) -> str:
    if not isinstance(name, str) or not SNAPSHOT_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="Invalid snapshot name.")
    return name


def clamp_resize(value_cols: object, value_rows: object) -> tuple[int, int]:
    try:
        cols = int(value_cols)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        cols = 80
    try:
        rows = int(value_rows)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        rows = 24
    return max(2, min(500, cols)), max(2, min(200, rows))


state = AgentState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = AgentConfig.load()
    if cfg is None or not cfg.credential:
        raise RuntimeError("Agent is not enrolled. Run: cvx-agent enroll")
    state.credential = cfg.credential
    state.lxd = LXDClient()
    yield
    if state.lxd:
        await state.lxd.close()


app = FastAPI(default_response_class=ORJSONResponse, lifespan=lifespan, docs_url=None)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    # Health check for local monitoring only.
    if request.url.path == "/healthz":
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    expected = f"Bearer {state.credential}"
    import hmac as _hmac

    if not _hmac.compare_digest(auth.encode(), expected.encode()):
        return ORJSONResponse(
            status_code=401,
            content={"error": {"code": "unauthenticated", "message": "Invalid agent credential."}},
        )
    return await call_next(request)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Instance not found")


@app.get("/v1/info")
async def info() -> dict[str, Any]:
    assert state.lxd is not None
    sysinfo = collect_system_info()
    try:
        lxd_info = await state.lxd.server_info()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LXD unavailable: {e}") from e
    from cvx_agent import __version__

    return {
        "agent_version": __version__,
        **sysinfo,
        "lxd_version": lxd_info.get("lxd_version"),
        "storage_driver": _primary_storage_driver(lxd_info),
    }


def _primary_storage_driver(lxd_info: dict[str, Any]) -> str | None:
    drivers = lxd_info.get("storage_drivers") or []
    for d in drivers:
        if isinstance(d, dict) and d.get("name"):
            return str(d["name"])
    return None


@app.get("/v1/instances/{name}")
async def get_instance(name: str) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    inst = await state.lxd.get_instance(name)
    if inst is None:
        raise _not_found()
    return inst


@app.post("/v1/instances", status_code=201)
async def create_instance(payload: dict[str, Any]) -> dict[str, Any]:
    assert state.lxd is not None
    name = payload.get("name", "")
    validate_instance_name(name)
    try:
        inst = await state.lxd.create_instance(payload)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return inst


@app.delete("/v1/instances/{name}", status_code=204)
async def delete_instance(name: str) -> None:
    assert state.lxd is not None
    validate_instance_name(name)
    try:
        await state.lxd.delete_instance(name)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


def _action_body(body: dict[str, Any] | None) -> tuple[int, bool]:
    b = body or {}
    timeout = int(b.get("timeout", 30))
    force = bool(b.get("force", False))
    return max(5, min(timeout, 300)), force


@app.post("/v1/instances/{name}/start")
async def start_instance(name: str) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    try:
        await state.lxd.start_instance(name)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}


@app.post("/v1/instances/{name}/stop")
async def stop_instance(name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    timeout, force = _action_body(body)
    try:
        await state.lxd.stop_instance(name, timeout=timeout, force=force)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}


@app.post("/v1/instances/{name}/restart")
async def restart_instance(name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    timeout, _force = _action_body(body)
    try:
        await state.lxd.restart_instance(name, timeout=timeout)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}


@app.post("/v1/instances/{name}/shutdown")
async def shutdown_instance(name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    timeout, _ = _action_body(body)
    try:
        await state.lxd.stop_instance(name, timeout=timeout, force=False)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}


@app.patch("/v1/instances/{name}/config")
async def patch_config(name: str, body: dict[str, Any]) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    config = body.get("config") or {}
    if not isinstance(config, dict) or not all(isinstance(v, str) for v in config.values()):
        raise HTTPException(status_code=422, detail="config must be a string map.")
    try:
        await state.lxd.patch_config(name, config)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}


@app.get("/v1/instances/{name}/metrics")
async def instance_metrics(name: str) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    try:
        return await state.lxd.instance_metrics(name)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# --- Snapshots ---------------------------------------------------------------


@app.post("/v1/instances/{name}/snapshots", status_code=201)
async def create_snapshot(name: str, body: dict[str, Any]) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    snap_name = validate_snapshot_name(body.get("name", ""))
    try:
        return await state.lxd.create_snapshot(
            name, snap_name, bool(body.get("stateful", False))
        )
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/v1/instances/{name}/snapshots")
async def list_snapshots(name: str) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    try:
        return {"snapshots": await state.lxd.list_snapshots(name)}
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.post("/v1/instances/{name}/snapshots/{snap_name}/rename")
async def rename_snapshot(name: str, snap_name: str, body: dict[str, Any]) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    snap = validate_snapshot_name(snap_name)
    new_name = validate_snapshot_name(body.get("name", ""))
    try:
        await state.lxd.rename_snapshot(name, snap, new_name)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}


@app.post("/v1/instances/{name}/snapshots/{snap_name}/restore")
async def restore_snapshot(name: str, snap_name: str) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    snap = validate_snapshot_name(snap_name)
    try:
        await state.lxd.restore_snapshot(name, snap)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}


@app.delete("/v1/instances/{name}/snapshots/{snap_name}", status_code=204)
async def delete_snapshot(name: str, snap_name: str) -> None:
    assert state.lxd is not None
    validate_instance_name(name)
    snap = validate_snapshot_name(snap_name)
    try:
        await state.lxd.delete_snapshot(name, snap)
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


# --- Backups -----------------------------------------------------------------


@app.post("/v1/instances/{name}/backups", status_code=201)
async def create_backup(name: str, body: dict[str, Any]) -> dict[str, Any]:
    assert state.lxd is not None
    validate_instance_name(name)
    backup_name = validate_snapshot_name(body.get("name", ""))
    try:
        return await state.lxd.create_backup(
            name, backup_name, bool(body.get("optimized_storage", True))
        )
    except LXDError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.delete("/v1/backups/{backup_name}", status_code=204)
async def delete_backup(backup_name: str) -> None:
    assert state.lxd is not None
    validate_snapshot_name(backup_name)
    try:
        await state.lxd.delete_backup(backup_name)
    except LXDError as e:
        raise HTTPException(status_code=404 if e.status == 404 else 502, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 502, detail=str(e)) from e


@app.post("/v1/instances/{name}/restore-backup")
async def restore_backup(name: str, body: dict[str, Any]) -> dict[str, Any]:
    # V1 note: restoring replaces the instance. Implemented via LXD import of
    # the stored backup archive on the node.
    validate_instance_name(name)
    path = body.get("backup_path", "")
    if not isinstance(path, str):
        raise HTTPException(status_code=422, detail="Invalid backup path.")
    if not path.startswith(("/var/snap/lxd/", "/var/lib/lxd/")) or ".." in path:
        raise HTTPException(status_code=422, detail="Invalid backup path.")
    proc = await asyncio.create_subprocess_exec(
        "lxc", "import", path, name, "--force",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=stderr.decode()[:500])
    return {"ok": True}


# --- Console (websocket) -----------------------------------------------------


@app.websocket("/v1/instances/{name}/console")
async def console_ws(ws: WebSocket, name: str) -> None:
    import hmac as _hmac

    token = (ws.headers.get("authorization") or "").encode()
    if not _hmac.compare_digest(token, f"Bearer {state.credential}".encode()):
        await ws.close(code=4401)
        return
    try:
        validate_instance_name(name)
    except HTTPException:
        await ws.close(code=4522)
        return

    await ws.accept()

    shell = os.environ.get("CVX_AGENT_SHELL", "/bin/bash")
    proc = await asyncio.create_subprocess_exec(
        "lxc", "exec", name, "--env", "TERM=xterm-256color", "--", shell, "-il",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def read_ws() -> None:
        assert proc.stdin is not None
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                text = msg.get("text")
                if text is None:
                    continue
                data = json.loads(text)
                kind = data.get("type")
                if kind == "input":
                    proc.stdin.write(data.get("data", "").encode())
                    await proc.stdin.drain()
                elif kind == "resize":
                    cols, rows = clamp_resize(data.get("cols", 80), data.get("rows", 24))
                    proc.stdin.write(f"stty rows {rows} cols {cols}\n".encode())
                    await proc.stdin.drain()
                elif kind == "start":
                    cols, rows = clamp_resize(data.get("cols", 80), data.get("rows", 24))
                    proc.stdin.write(f"stty rows {rows} cols {cols}\n".encode())
                    await proc.stdin.drain()
        except WebSocketDisconnect:
            pass
        finally:
            if proc.returncode is None:
                try:
                    proc.send_signal(signal.SIGKILL)
                except ProcessLookupError:
                    pass

    async def write_ws() -> None:
        assert proc.stdout is not None
        while True:
            chunk = await proc.stdout.read(8192)
            if not chunk:
                break
            await ws.send_bytes(chunk)

    tasks = [asyncio.create_task(read_ws()), asyncio.create_task(write_ws())]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    if proc.returncode is None:
        proc.kill()
    try:
        await ws.close()
    except Exception:
        pass
