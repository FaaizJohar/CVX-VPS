FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/cvx

# Build context is the repo root (see docker-compose files) so the node-agent
# package can be shipped for /downloads/cvx-agent-latest.tar.gz + /install/node.
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./
COPY services/node-agent ./node-agent

RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "sqlalchemy[asyncio]>=2.0.36" \
    "asyncpg>=0.30.0" \
    "alembic>=1.14.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "email-validator>=2.2.0" \
    "redis>=5.2.0" \
    "argon2-cffi>=23.1.0" \
    "httpx>=0.28.0" \
    "orjson>=3.10.0" \
    "structlog>=24.4.0" \
    "python-json-logger>=3.1.0" \
    "websockets>=13.0" \
    "cryptography>=43.0"

RUN useradd --system --uid 10001 cvx && chown -R cvx:cvx /srv/cvx
USER cvx

EXPOSE 8000

# CVX_TRUSTED_PROXIES: comma-separated proxy IPs allowed to set X-Forwarded-For.
# Never use '*' in production — spoofed XFF entries poison rate limiting and audit logs.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"${CVX_TRUSTED_PROXIES:-}\""]
