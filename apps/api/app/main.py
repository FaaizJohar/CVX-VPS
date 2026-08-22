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
    yield
    from app.db.redis import close_redis

    from app.db.session import get_engine

    await close_redis()
    await get_engine().dispose()


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
