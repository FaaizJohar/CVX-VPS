# CVX Panel

**VPS infrastructure control panel powered by LXD.**

CVX turns LXD hosts into a multi-tenant VPS cloud: enroll compute nodes, provision
virtual private servers in seconds, and manage the full lifecycle — console, snapshots,
backups, metrics, networking and logs — from a single web interface.

**Two deployment modes (v1.1):** deploy VPSes on enrolled nodes running the CVX
agent, or — when the panel host itself has LXD — deploy **locally** with zero
extra setup ("This Machine" in the create wizard; the panel speaks to LXD over
its unix socket, no agent required). See `docs/V1_1_RELEASE_REPORT.md`.

LXD is deliberately hidden behind an abstraction layer. Users see "VPS", never containers.

## Architecture

```
┌──────────────┐   HTTPS + session cookie   ┌───────────────┐
│  apps/web    │ ─────────────────────────► │   apps/api    │
│  React + TS  │ ◄───────────────────────── │   FastAPI     │
└──────────────┘   REST + WebSocket console └───────┬───────┘
                                                    │ mTLS-style bearer auth
                                    ┌───────────────▼───────────────┐
                                    │      services/node-agent      │
                                    │  FastAPI agent on every node  │
                                    │  talks to local LXD (REST)    │
                                    └───────────────────────────────┘
```

- **`apps/api`** — control plane. FastAPI, SQLAlchemy 2.0 (async), Postgres, Redis
  (rate limiting), Alembic migrations. Owns all state; nodes are never authoritative.
- **`apps/web`** — React 18 + TypeScript + Vite SPA. TanStack Query, xterm.js console,
  recharts metrics. Served by nginx in production.
- **`services/node-agent`** — small Python agent installed on each LXD host.
  No arbitrary-exec endpoint: provisioning operations are whitelisted, the console is a
  supervised `lxc exec` bridge.

## Quick start (development)

Prerequisites: Python 3.11+, Node 20+, Docker.

```bash
# 1. Database services
docker compose -f docker-compose.dev.yml up -d

# 2. API
cd apps/api
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../../.env.example .env                     # adjust CVX_DATABASE_URL / CVX_SECRET_KEY
alembic upgrade head
uvicorn app.main:app --reload                  # http://localhost:8000/docs

# 3. Web
cd apps/web
npm install
npm run dev                                    # http://localhost:5173 (proxies /api)
```

The first account is created from `CVX_BOOTSTRAP_OWNER_EMAIL` /
`CVX_BOOTSTRAP_OWNER_PASSWORD` when the users table is empty.

## Production deployment

```bash
cp .env.example .env    # set CVX_SECRET_KEY, CVX_DB_PASSWORD, CVX_PUBLIC_BASE_URL ...
docker compose -f infrastructure/docker-compose.prod.yml up -d --build
```

### One-click deploy on any VPS (Cloudflare Tunnel)

Installs Docker, deploys the whole stack, and exposes it via a Cloudflare Tunnel
(HTTPS, no open ports, no manual DNS):

```bash
curl -fsSL https://raw.githubusercontent.com/FaaizJohar/CVX-VPS/main/infrastructure/cloud/install-panel.sh \
  | sudo CVX_CF_TUNNEL_TOKEN=<token> CVX_PANEL_DOMAIN=panel.example.com bash
```

1. Cloudflare Dashboard → Zero Trust → Networks → Tunnels → Create tunnel → copy token.
2. Run the command above on a fresh Ubuntu/Debian VPS.
3. In the tunnel's Public Hostname settings: `panel.example.com` → HTTP → `localhost:8080`.

No token? Omit `CVX_CF_TUNNEL_TOKEN` and you get a temporary
`trycloudflare.com` URL for testing. Re-running the script updates an existing
install; `--uninstall` removes everything.

- `web` (nginx) serves the SPA on port 80 and reverse-proxies `/api/` to the API,
  including WebSocket upgrades for the console.
- `api` runs Alembic migrations on start, then uvicorn behind proxy headers.
- Put a TLS terminator (Caddy, Traefik, cloud LB) in front of `web`;
  set `CVX_SESSION_COOKIE_SECURE=true`.
- **Local deployment:** if the host runs LXD, the installer enables
  "Deploy on this machine" automatically (compose override
  `infrastructure/docker-compose.local.yml`, env `CVX_ENABLE_LOCAL_DEPLOYMENT=true`).

## Adding a compute node

1. Log in as admin → **Nodes → Add node**.
2. The panel issues a single-use enrollment token (default TTL 30 min).
3. On the target host (Ubuntu 22.04/24.04 with LXD installed):

```bash
curl -fsSL <your-install-url> | sudo CVX_ENROLL_TOKEN=<token> CVX_CONTROL_PLANE=<panel-url> bash
```

or manually:

```bash
pip install services/node-agent        # or copy the cvx_agent package
cvx-agent enroll --token <token>
cvx-agent serve                        # systemd unit provided in deploy/
```

The agent generates its own credential at enrollment, stores it `0600`, and heartbeats
every 30 s with CPU/RAM/storage/metrics. Rotate credentials any time from the node detail
page — the old credential is invalidated immediately.

## Security model

- Session cookies are httpOnly + SameSite=strict (+ Secure in production); sessions are
  server-side records, revocable individually or in bulk.
- Node credentials are stored hashed (for verification) *and* AES-encrypted (so the
  control plane can call agents); plaintext is shown once at enrollment.
- VPS workspaces are additionally gated by password re-entry ("unlock").
- All privileged actions land in an append-only audit log with secret redaction;
  security-relevant events are classified separately.
- Rate limiting on auth endpoints (Redis-backed, fails open if Redis is down).
- The agent exposes no shell/exec-by-request endpoint; console access is a relayed
  interactive `lxc exec` tied to panel sessions.

Full details: [docs/SECURITY.md](docs/SECURITY.md).

## Documentation

| Doc | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data model, request lifecycle, IPAM atomicity, reconciliation |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, auth/RBAC, injection hardening, rate limits |
| [docs/NODE_AGENT.md](docs/NODE_AGENT.md) | Agent install, API surface, hardening, backup caveats |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Deployment, health probes, backups, secret rotation, incident runbook |
| [docs/PRODUCTION_READINESS.md](docs/PRODUCTION_READINESS.md) | Verified guarantees, accepted V1 limitations, pre-scale checklist |
| [docs/V1_GAP_AUDIT.md](docs/V1_GAP_AUDIT.md) | Hardening audit: findings → fixes → tests |

> **Backup note:** VPS backups are **node-local** in V1 — LXD writes archives on the
> node's own disk and the panel stores metadata only. Losing a node loses its backups;
> plan off-node copies until V2 adds panel-managed export.

## Repository layout

```
apps/api          FastAPI control plane (app/, alembic/, tests/)
apps/web          React SPA (src/)
services/node-agent  Per-node agent + deploy/cvx-install.sh
infrastructure/   Production compose + docker assets
docs/             Design notes & runbooks
```

## Tests

```bash
cd apps/api
pytest tests -q                       # 25 functional tests
pytest tests/security -q              # 56 adversarial/security tests
cd ../../services/node-agent
pytest tests_agent -q                 # 61 agent unit tests (no LXD needed)
```

Security suite covers: privilege escalation, IPAM races (atomic claims proven on an
isolated WAL database), rate-limit bypass, enrollment-token replay, heartbeat
reconciliation, cloud-init injection, capacity accounting, console abuse, SSRF/RBAC,
injection attempts, error-shape contracts and provider failure injection.

Frontend type-checking and build:

```bash
cd apps/web
npm run build              # tsc -b && vite build
```
