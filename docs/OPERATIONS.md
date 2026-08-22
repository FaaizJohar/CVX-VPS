# CVX Panel — Operations Runbook

## Deployment

```bash
cp .env.example .env        # then set the required secrets
docker compose -f infrastructure/docker-compose.prod.yml up -d --build
```

Required env: `CVX_SECRET_KEY` (32+ random bytes), `CVX_DB_PASSWORD`,
`CVX_PUBLIC_BASE_URL`. Recommended: `CVX_BOOTSTRAP_OWNER_EMAIL`/
`CVX_BOOTSTRAP_OWNER_PASSWORD` (bootstrap only happens on an empty users
table), `CVX_TRUSTED_PROXIES` (comma-separated proxy IPs allowed to set
X-Forwarded-For; empty means none).

The `api` container runs `alembic upgrade head` before uvicorn starts. The
`web` container publishes `${CVX_HTTP_PORT:-80}` and proxies `/api/` internally.

### TLS

Terminate TLS at Caddy/Traefik/cloud LB in front of `web`. Then set
`CVX_SESSION_COOKIE_SECURE=true` (default) and `CVX_BEHIND_PROXY=true`.

## Health & monitoring

| Probe | Meaning |
|---|---|
| `GET /healthz` | process up (no deps checked) |
| `GET /readyz` | 200 only when **DB and Redis** answer; body lists per-check status |

Alert on: `readyz` != 200; node heartbeats silent > 90 s (node shows offline);
audit-log write failures in API logs; Redis restarts (rate limiter fails open
while it is down — watch for abuse during outages).

Every response carries `x-request-id`; include it when grepping logs.

## Backups

- **Postgres** is the source of truth. Nightly `pg_dump` + WAL archiving to
  off-node storage. Test restores quarterly.
- **Redis** holds only rate-limit counters — disposable.
- **VPS backups are node-local in V1** (LXD writes archives under
  `/var/snap/lxd/common/lxd/backups/` or `/var/lib/lxd/backups/`). The panel
  stores metadata only. Add node-level off-site sync (restic/borg to object
  storage) if node loss is unacceptable.
- Snapshots use the node storage pool's native copy-on-write — fast, but also
  node-local.

## Secret rotation

| Secret | Procedure |
|---|---|
| `CVX_SECRET_KEY` | Derives session signing **and** node-credential encryption. Rotate → all agent credentials must be re-issued (rotate from each node detail page or re-enroll). Schedule jointly. |
| Node credential | Nodes page → rotate; old secret dies instantly, agent picks up new one on next enroll call. |
| User password | Self-service reset flow (rate-limited); admins can trigger disable. |
| DB password | Compose env + `CVX_DATABASE_URL`, rolling restart. |

## Node lifecycle

- **Enroll**: Nodes → Add node → token (30 min TTL, single-use) → run installer.
- **Drain**: set maintenance mode (blocks new VPS creation on that node).
- **Decommission**: delete node in UI after migrating/deleting its VPS;
  IP pool rows go with it.
- **Reconciliation**: heartbeat reports instance truth every 30 s. VPS missing
  on the node → marked error (`missing_on_node`). Stuck provisioning/deleting
  >30 min → resolved against reported state automatically. No manual DB edits.

## Common incidents

| Symptom | First checks |
|---|---|
| Node flapping offline | agent systemd status; control-plane reachability from node :9700 reverse direction; cert expiry |
| Console WS closes 4502 | agent down / firewall; check node reachable, `cvx-agent.service` logs |
| 429 storms | Redis was down (limiter fails open→closed transitions); check `readyz` redis check |
| Provision stuck "provisioning" | node agent logs; LXD storage pool space; auto-resolves to error after 30 min |
| Login 401 for valid users | clock skew breaking session expiry; `CVX_SECRET_KEY` changed without re-login |

## Upgrades

1. `git pull`, review migration notes below.
2. `docker compose -f infrastructure/docker-compose.prod.yml build`
3. `docker compose -f infrastructure/docker-compose.prod.yml up -d` (api runs
   migrations on start; brief 502s while web waits for api health).
4. Update agents: re-run installer on each node (idempotent).

## Migration history

- `0001..6918a468329b` — initial schema through V1 feature set.
- `b7f2c1a94d03` — adds FK `ip_addresses.vps_id → vps.id` (ON DELETE SET NULL),
  with cleanup of pre-existing dangling references.
