# CVX Panel — Architecture

## Overview

CVX Panel is a multi-tenant VPS control panel. LXD hosts ("nodes") run a small
agent; the control plane owns all state and drives nodes through that agent.
LXD terminology never reaches users: they see VPS.

```
Browser ──HTTPS──► nginx (web) ──/api──► FastAPI control plane ──HTTPS/bearer──► cvx-agent (per node)
   │                                        │                    │
   └──────── WebSocket console ─────────────┘                    └── unix socket ──► LXD REST
                          (cookie-authenticated WS relay)
```

Three trust domains:

| Domain | Components | Trust |
|---|---|---|
| User | Browser, SPA | Untrusted. Authenticated via server-side sessions. |
| Control plane | `apps/api`, Postgres, Redis | Trusted. Owns all authoritative state. |
| Node | `services/node-agent`, LXD | Semi-trusted executor. Never authoritative for control-plane state. |

## Monorepo layout

```
apps/api            FastAPI control plane
  app/api/v1/routes   HTTP + WS endpoints (auth, users, nodes, vps, snapshots,
                      backups, console, agent-facing endpoints)
  app/services        Business logic (user_service, node_service, vps_service, ...)
  app/providers       ComputeProvider abstraction + LXDProvider (agent protocol client)
  app/schemas         Pydantic request/response models + node-side validators
  app/core            config, security (hashing, cookies), errors, rate_limit, logging
  app/db              async engine/session, redis, models/
  alembic/            migrations
  tests/              functional suite; tests/security/ adversarial suite
apps/web            React 18 + TS SPA (TanStack Query, xterm.js, recharts)
services/node-agent Per-node FastAPI agent (cvx_agent package) + deploy/cvx-install.sh
infrastructure/     docker-compose.prod.yml, Dockerfiles live in apps/*/
docs/               This documentation set
```

## Control plane

### Request lifecycle

1. **nginx** terminates TLS, serves the SPA, proxies `/api/` (including WS
   upgrades) to the API container.
2. **uvicorn** runs with `--proxy-headers --forwarded-allow-ips=$CVX_TRUSTED_PROXIES`
   so only configured proxies may set `X-Forwarded-For`.
3. **Observability middleware** (`app/main.py`): assigns/echoes `x-request-id`,
   applies Redis rate limiting to `/api/*` except `/api/v1/agent/*` (agents have
   their own credential gate).
4. **Route → service → provider**: routes validate input (Pydantic), services
   enforce RBAC and invariants, providers translate to the agent protocol.
5. Errors surface as a uniform envelope: `{"error": {"code", "message"}}` with
   the request id attached (`app/core/errors.py`).

### Data model (essentials)

- `users` — role: owner/admin/user. Owners manage owners; admins manage users.
- `sessions` — server-side session records (revocable individually or in bulk).
- `api_keys` — hashed keys with prefix display, per-user.
- `nodes` — enrolled LXD hosts; credential stored **hashed** (verification) and
  **Fernet-encrypted** (for outbound calls). Heartbeats mark nodes offline after
  90 s of silence.
- `enrollment_tokens` — single-use, expiring (`cvxenroll_...`); claimed via an
  atomic conditional UPDATE.
- `vps` — one row per VPS; `provider_ref` is the opaque instance name on the
  node (`cvx-<hex>`). Status machine: provisioning → running/stopped/error → deleted.
- `ip_addresses` — per-node pools; claiming is atomic (see IPAM below).
- `snapshots`, `backups` — metadata only; payloads stay on the node.
- `audit_logs`, `vps_logs`, `metrics` — append-only operational history.

### Provider abstraction

`ComputeProvider` (abstract) → `LXDProvider` (agent protocol) → `AgentClient`
(HTTP over TLS to the node agent). Services never see "container". Swapping the
virtualization backend means implementing one class.

### IPAM atomicity

Claiming an address does two things (`vps_service.create_vps`):

1. `SELECT ... FOR UPDATE` on the free address (fast-path serialization on
   PostgreSQL).
2. An authoritative conditional `UPDATE ip_addresses SET status='assigned',
   vps_id=... WHERE id=... AND status='available' AND vps_id IS NULL`; a
   rowcount ≠ 1 loses the race and surfaces a clean 422.

This works even where `FOR UPDATE` is a no-op (SQLite). A foreign key from
`ip_addresses.vps_id` to `vps.id` (ON DELETE SET NULL) keeps the pool consistent.

### Node lifecycle & reconciliation

- Enrollment: admin issues token → agent posts hello+system info → credential
  generated, returned once, stored hashed+encrypted.
- Heartbeat every 30 s: counters, metrics, instance list. The control plane
  reconciles:
  - instances missing from the report → VPS marked `error` (`missing_on_node`),
    skipping transitional states;
  - stuck transitional VPS (>30 min) → resolved against the reported truth
    (`provisioning_timeout`, or released/deleted when absent from the report);
  - silence >90 s → node offline.
- Credential rotation invalidates the old secret immediately.

### Console

`GET /api/v1/vps/{id}/console` upgrades to WebSocket after cookie-session auth.
The control plane relays JSON frames `{type: start|resize|input}` toward the
agent's `lxc exec` bridge and streams raw bytes back. Hardened limits: 4 h max
lifetime, re-validation every 60 s (session alive, VPS not deleted), ≤5
concurrent consoles per user, resize clamped to 2–500 × 2–200 both sides.
Close codes: 4401 unauthenticated, 4403 forbidden, 4408 lock held, 4429 rate
limited, 4502 node unreachable, 1011 internal.

## Node agent

FastAPI on :9700 behind HTTPS, bearer-credential auth (constant-time compare),
no docs endpoint, no arbitrary exec. Every name from the control plane is
validated against tight allowlists before it can reach an LXD path or argv.
See `docs/NODE_AGENT.md`.

## Frontend

React 18 + TypeScript + Vite. TanStack Query for data fetching, xterm.js for
the console, recharts for metrics. Production build is static assets served by
nginx which also reverse-proxies the API (single origin → no CORS in prod).

## Environments

- Development: `docker-compose.dev.yml` (Postgres + Redis), uvicorn --reload,
  vite dev server proxying /api.
- Production: `infrastructure/docker-compose.prod.yml` — postgres 16, redis 7
  (AOF), api (runs `alembic upgrade head` then uvicorn), web (nginx :80).
  Put a TLS terminator in front; set `CVX_SESSION_COOKIE_SECURE=true`.
