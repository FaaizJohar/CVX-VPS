"""Terminal console WebSocket — proxies the user's xterm to the node agent.

Security posture:
- Session cookie is validated at connect AND re-validated periodically; logout,
  revocation or VPS deletion tears down live consoles within one interval.
- Consoles are capped per user and in total lifetime.
- Close codes: 4401 unauthenticated, 4403 session revoked/VPS gone,
  4408 lifetime exceeded, 4429 too many concurrent consoles, 4502 node
  unreachable, 1011 internal error.
"""

import asyncio
import json
import uuid

import websockets
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import unix_connect

from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.core.security import decrypt_secret
from app.db.session import get_session_factory
from app.models import NODE_KIND_AGENT, NODE_KIND_LOCAL, Node, VPS, VPSStatus
from app.providers.base import ConsoleTarget
from app.services.audit import record_audit
from app.services.auth_service import AuthService
from app.services.node_service import NodeService
from app.services.vps_service import VPSService

router = APIRouter(tags=["console"])
log = get_logger("cvx.console")

MAX_FRAME = 64 * 1024
CONSOLE_MAX_LIFETIME_SECONDS = 4 * 3600
CONSOLE_REVALIDATE_INTERVAL_SECONDS = 60
MAX_CONSOLES_PER_USER = 5

# Live console counters keyed by user id (single event loop — no lock needed).
_active_consoles: dict[uuid.UUID, int] = {}


def clamp_resize(value_cols: object, value_rows: object) -> tuple[int, int]:
    """Clamp client-supplied resize values to safe bounds."""
    try:
        cols = int(value_cols)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        cols = 80
    try:
        rows = int(value_rows)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        rows = 24
    return max(2, min(500, cols)), max(2, min(200, rows))


async def _relay_lxd_console(
    ws: WebSocket, target: ConsoleTarget, cols: int, rows: int, stop: asyncio.Event
) -> None:
    """Relay a browser terminal to an LXD exec websocket over the unix socket.

    The PTY is already sized at exec time (cols/rows); resizes go through the
    "control" websocket. fd "0" carries the combined interactive session.
    """
    assert target.socket_path and target.url and target.fd_secrets
    base = target.url
    fd0_uri = f"{base}?secret={target.fd_secrets.get('0', '')}"
    control_uri = f"{base}?secret={target.fd_secrets.get('control', '')}"

    try:
        async with unix_connect(fd0_uri, path=target.socket_path, max_size=MAX_FRAME) as io:
            try:
                async with unix_connect(
                    control_uri, path=target.socket_path, max_size=MAX_FRAME
                ) as control:

                    async def pump_to_lxd() -> None:
                        while True:
                            msg = await ws.receive_text()
                            data = json.loads(msg)
                            kind = data.get("type")
                            if kind == "resize":
                                c, r = clamp_resize(
                                    data.get("cols", 80), data.get("rows", 24)
                                )
                                await control.send(json.dumps({"width": c, "height": r}))
                            elif kind == "input":
                                await io.send(str(data.get("data", "")))
                            # "start" needs no action: PTY is already live.

                    async def pump_to_client() -> None:
                        async for raw in io:
                            if isinstance(raw, bytes):
                                await ws.send_bytes(raw)
                            else:
                                await ws.send_text(raw)

                    tasks = [
                        asyncio.create_task(pump_to_lxd()),
                        asyncio.create_task(pump_to_client()),
                        asyncio.create_task(stop.wait()),
                    ]
                    done, pending = await asyncio.wait(
                        tasks, return_when=asyncio.FIRST_COMPLETED
                    )
                    for t in pending:
                        t.cancel()
            except websockets.ConnectionClosed:
                pass
    except (OSError, websockets.InvalidURI, websockets.InvalidHandshake):
        try:
            await ws.close(code=4502, reason="local LXD unreachable")
        except Exception:
            pass


@router.websocket("/vps/{vps_id}/console")
async def console_ws(
    ws: WebSocket,
    vps_id: uuid.UUID,
    cols: int = Query(default=80, ge=2, le=500),
    rows: int = Query(default=24, ge=2, le=200),
) -> None:
    await ws.accept()

    # --- authenticate + authorize over the session cookie -------------------
    factory = get_session_factory()
    credential: str | None = None
    agent_ws_url: str | None = None
    lxd_target: ConsoleTarget | None = None
    session_token: str | None = None
    user_id: uuid.UUID | None = None
    try:
        async with factory() as db:
            token = ws.cookies.get(get_settings().session_cookie_name)
            if not token:
                raise AuthenticationError()
            session = await AuthService.validate_session(db, token)
            if session is None:
                raise AuthenticationError()
            user = session.user

            active = _active_consoles.get(user.id, 0)
            if active >= MAX_CONSOLES_PER_USER:
                await ws.close(code=4429, reason="too many console sessions")
                return

            vps = await db.get(VPS, vps_id)
            if vps is None or vps.status == VPSStatus.DELETED:
                raise AuthenticationError()
            if not VPSService.can_access(user, vps):
                raise AuthenticationError()

            node = await db.get(Node, vps.node_id)
            if node is None:
                raise AuthenticationError()

            if getattr(node, "kind", NODE_KIND_AGENT) == NODE_KIND_LOCAL:
                # Local deployments speak LXD's exec websocket directly.
                provider = NodeService.provider_for(node)
                lxd_target = await provider.console_target(
                    vps.provider_ref, cols, rows
                )
            else:
                if not node.credential_encrypted:
                    raise AuthenticationError()
                credential = decrypt_secret(node.credential_encrypted)
                agent_ws_url = NodeService.provider_for(node).console_ws_url(
                    vps.provider_ref
                )

            await record_audit(
                db, action="vps.console.open", actor_user_id=str(user.id),
                resource_type="vps", resource_id=str(vps.id), node_id=str(node.id),
            )
            await db.commit()
            session_token = token
            user_id = user.id
    except AuthenticationError:
        await ws.close(code=4401, reason="unauthenticated")
        return
    except Exception:
        log.exception("console setup failed vps=%s", vps_id)
        await ws.close(code=1011)
        return

    assert user_id is not None and session_token is not None
    _active_consoles[user_id] = _active_consoles.get(user_id, 0) + 1
    stop = asyncio.Event()

    async def revalidate_loop() -> None:
        """Kill the console when the session dies or the VPS disappears."""
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=CONSOLE_REVALIDATE_INTERVAL_SECONDS)
                return  # stopped cleanly
            except asyncio.TimeoutError:
                pass
            try:
                async with factory() as db:
                    session = await AuthService.validate_session(db, session_token)
                    vps = await db.get(VPS, vps_id)
                    valid = (
                        session is not None
                        and vps is not None
                        and vps.status != VPSStatus.DELETED
                    )
            except Exception:
                log.exception("console revalidation failed vps=%s", vps_id)
                valid = True  # transient DB issues must not drop sessions
            if not valid:
                stop.set()
                try:
                    await ws.close(code=4403, reason="session no longer valid")
                except Exception:
                    pass
                return

    # --- relay ---------------------------------------------------------------
    if lxd_target is not None:
        await _relay_lxd_console(ws, lxd_target, cols, rows, stop)
        stop.set()
        return

    try:
        async with websockets.connect(
            agent_ws_url,  # type: ignore[arg-type]
            additional_headers={"Authorization": f"Bearer {credential}"},
            max_size=MAX_FRAME,
        ) as agent:

            async def pump_to_agent() -> None:
                try:
                    await agent.send(json.dumps({"type": "start", "cols": cols, "rows": rows}))
                    while True:
                        msg = await ws.receive_text()
                        data = json.loads(msg)
                        kind = data.get("type")
                        if kind == "resize":
                            c, r = clamp_resize(data.get("cols", 80), data.get("rows", 24))
                            await agent.send(
                                json.dumps({"type": "resize", "cols": c, "rows": r})
                            )
                        elif kind == "input":
                            await agent.send(str(data.get("data", "")))
                except WebSocketDisconnect:
                    pass

            async def pump_to_client() -> None:
                try:
                    async for raw in agent:
                        if isinstance(raw, bytes):
                            await ws.send_bytes(raw)
                        else:
                            await ws.send_text(raw)
                except websockets.ConnectionClosed:
                    pass

            tasks = [
                asyncio.create_task(pump_to_agent()),
                asyncio.create_task(pump_to_client()),
                asyncio.create_task(revalidate_loop()),
            ]
            done, pending = await asyncio.wait(
                tasks,
                timeout=CONSOLE_MAX_LIFETIME_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            timed_out = not done  # lifetime elapsed with no other completion
    except (OSError, websockets.InvalidURI, websockets.InvalidHandshake):
        await ws.close(code=4502, reason="node unreachable")
    except Exception:
        log.exception("console relay error vps=%s", vps_id)
        timed_out = False
        try:
            await ws.close(code=1011)
        except Exception:
            pass
    else:
        if timed_out:
            try:
                await ws.close(code=4408, reason="console session expired")
            except Exception:
                pass
    finally:
        stop.set()
        if user_id is not None:
            remaining = _active_consoles.get(user_id, 1) - 1
            if remaining <= 0:
                _active_consoles.pop(user_id, None)
            else:
                _active_consoles[user_id] = remaining
