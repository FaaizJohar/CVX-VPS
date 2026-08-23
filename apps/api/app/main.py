"""CVX control plane entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import CVXError, RateLimitError, cvx_error_handler
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    from app.bootstrap import ensure_local_node, ensure_owner_account

    try:
        await ensure_owner_account()
        await ensure_local_node()
    except Exception:
        # Database may not be migrated yet (e.g. first alembic run); don't crash.
        pass
    from app.services.provisioning import start_worker, stop_worker

    start_worker()  # resumes any provisioning jobs abandoned by a crash
    yield
    await stop_worker()

    from app.db.redis import close_redis

    from app.db.session import get_engine

    await close_redis()
    await get_engine().dispose()


def _agent_package_root():
    """Filesystem location of the node-agent source shipped with the API."""
    import os
    from pathlib import Path

    candidates = [
        Path(os.getenv("CVX_AGENT_PACKAGE_DIR", "") or "/nonexistent"),
        Path("/srv/cvx/node-agent"),
        Path.cwd() / "node-agent",
        Path.cwd().parent / "services" / "node-agent",  # dev checkout
    ]
    for c in candidates:
        if (c / "pyproject.toml").is_file():
            return c
    return None


_agent_archive_cache: dict[str, bytes | None] = {"tar": None}


def _build_agent_archive(root):
    import io
    import tarfile

    if _agent_archive_cache["tar"] is not None:
        return _agent_archive_cache["tar"]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(root / "pyproject.toml", arcname="node-agent/pyproject.toml")
        pkg = root / "cvx_agent"
        for p in sorted(pkg.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                tf.add(p, arcname=f"node-agent/{p.relative_to(root)}")
    data = buf.getvalue()
    _agent_archive_cache["tar"] = data
    return data


def create_app() -> FastAPI:
    from app.api.deps.auth import DbDep

    settings = get_settings()
    app = FastAPI(
        title="CVX Control Plane",
        version="1.0.0",
        docs_url="/api/docs" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    if settings.trusted_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(CVXError)
    async def handle_cvx_error(request: Request, exc: CVXError):  # type: ignore[no-untyped-def]
        return await cvx_error_handler(request, exc)

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        import uuid as _uuid

        from app.core.rate_limit import rate_limit_request

        request_id = request.headers.get("x-request-id") or _uuid.uuid4().hex
        request.state.request_id = request_id
        path = request.url.path
        if path.startswith("/api/") and not path.startswith("/api/v1/agent"):
            try:
                await rate_limit_request(request)
            except RateLimitError as e:
                return e.to_response(request_id=request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    # ------------------------------------------------ public installer ----
    @app.get("/install/node", include_in_schema=False)
    async def install_node_script() -> ORJSONResponse:
        """Serve the node bootstrap script (plain text, no auth)."""
        from fastapi.responses import PlainTextResponse

        root = _agent_package_root()
        if root is None:
            return ORJSONResponse(
                status_code=503,
                content={"error": {"code": "agent_package_missing",
                                   "message": "Agent package is not shipped with this API build."}},
            )
        script = (root / "deploy" / "cvx-install.sh").read_text(encoding="utf-8")
        return PlainTextResponse(script, media_type="text/x-shellscript; charset=utf-8")

    @app.get("/downloads/cvx-agent-latest.tar.gz", include_in_schema=False)
    async def agent_tarball():
        from fastapi import HTTPException
        from fastapi.responses import Response

        root = _agent_package_root()
        if root is None:
            raise HTTPException(status_code=503, detail="agent package missing")
        data = _build_agent_archive(root)
        return Response(
            content=data,
            media_type="application/gzip",
            headers={"Content-Disposition": 'attachment; filename="cvx-agent-latest.tar.gz"'},
        )

    @app.get("/downloads/cvx-agent-latest.tar.gz.sha256", include_in_schema=False)
    async def agent_tarball_sha256():
        import hashlib

        from fastapi import HTTPException
        from fastapi.responses import PlainTextResponse

        root = _agent_package_root()
        if root is None:
            raise HTTPException(status_code=503, detail="agent package missing")
        data = _build_agent_archive(root)
        digest = hashlib.sha256(data).hexdigest()
        return PlainTextResponse(f"{digest}  cvx-agent-latest.tar.gz\n")

    @app.get("/readyz", include_in_schema=False)
    async def readyz(db: DbDep) -> ORJSONResponse:
        """Readiness: DB and Redis must answer. 503 otherwise."""
        from sqlalchemy import text

        from app.db.redis import get_redis

        checks: dict[str, str] = {}
        status = 200
        try:
            await db.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception:
            checks["db"] = "unavailable"
            status = 503
        try:
            await get_redis().ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
            status = 503
        return ORJSONResponse(
            status_code=status,
            content={"status": "ready" if status == 200 else "not_ready", "checks": checks},
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
