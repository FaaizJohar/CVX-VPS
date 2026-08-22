# CVX V1.1 Release Report — Dual Deployment Modes

Status: **implemented** (backend + frontend + deployment plumbing + tests).
Scope: the full V1.1 specification — "Deploy on Node" and "Deploy Locally"
modes, local LXD provider, premium UI/UX overhaul, migrations, tests, docs.

## 1. What shipped

### Deployment modes
- `VPSCreate.deployment_mode` accepts `"node"` (default) or `"local"`.
  `node_id` is required for node mode and forbidden for local mode
  (`apps/api/app/schemas/vps.py`).
- `vps.deployment_mode` column + `ck_vps_deployment_mode` CHECK constraint;
  existing rows backfilled to `"node"` via server default.
- `nodes.kind` column (`"agent"` default, `"local"` for the control-plane
  host). The local machine is a singleton node row named `local-machine`,
  auto-registered at startup when `CVX_ENABLE_LOCAL_DEPLOYMENT=true` and an
  LXD socket is reachable (`app/bootstrap.py::ensure_local_node`,
  `NodeService.get_or_create_local_node`).

> Design note (deviation from spec §7): local VPSes reference the internal
> system-managed local node row instead of a NULL `node_id`. Capacity checks,
> IPAM scoping and reconciliation are all keyed off `nodes`, so reusing the
> row keeps those paths intact; the API and UI still present the user-facing
> concept as a mode ("local"), never exposing the synthetic node in normal
> flows.

### Local provider (no agent)
- `apps/api/app/providers/local_lxd.py`: `LocalLXDProvider` implements the
  same `ComputeProvider` surface as the agent-backed provider by speaking the
  LXD REST API directly over the host unix socket (httpx UDS transport).
  Mirrors the agent's logic one-to-one: create/start/delete with snapshot-safe
  teardown, config limits, DNS apply with re-validation, metrics, snapshots,
  backups. Capacity detection via `/1.0/resources` + storage pools.
- Console for local VPSes uses LXD's native exec websockets
  (`interactive`, `wait-for-websocket`, control-channel resizes) relayed by
  the same hardened console endpoint (`_relay_lxd_console`); session
  revalidation, lifetime caps and per-user concurrency caps all apply
  unchanged.
- Known limitation (documented): backup-archive *restore* is not available
  for locally deployed VPSes (the agent shells out to `lxc import`; the API
  container has no LXD CLI). Snapshot restore covers the recovery path.

### API additions
- `GET /api/v1/nodes/local/status` — availability + coarse host capacity for
  any authenticated user (wizard gate); extra detail (socket path, versions)
  for admins.
- `POST /api/v1/nodes/local/refresh` — admin; re-detects capacity facts into
  the local node row.
- Guardrails: local node cannot be removed or rotated; node-mode creates
  cannot target the local row; kind/mode mismatches rejected with 422.
- `NodeOut.kind` exposed (non-admin field pruning unchanged).

### Frontend (premium UI/UX pass)
- Create wizard now opens with a **deployment selector**: two cards —
  "This Machine" (LOCAL, violet accent, live host capacity) and "On a Node"
  (agent nodes) — followed by OS → Resources → Network → Access → Review
  (6 steps). Auto-selects when only one target type exists; explicit empty-
  state when none do.
- `ModeBadge` component: LOCAL / NODE chips on the VPS list, workspace
  header, overview recents and admin nodes table.
- Admin Nodes page gained a persistent **Local Machine** card: availability,
  detected CPU/RAM/storage, LXD version + socket path (admin), Re-detect
  action, and actionable reasons when unavailable (disabled / no socket /
  unreachable).
- **⌘K command palette** (Ctrl+K on Windows/Linux): fuzzy search across your
  VPSes and pages, full keyboard navigation, ARIA combobox semantics; also
  reachable from the sidebar search button and mobile topbar.
- Accessibility: aria-pressed on selectable cards, aria-current on wizard
  steps, role=alert on errors, labelled icon-only buttons, focus-visible
  rings preserved via existing input styles. Layout remains responsive down
  to small screens (drawer nav, stacked grids).

### Deployment plumbing
- `infrastructure/docker-compose.local.yml`: mounts the host LXD socket into
  the api container and sets `CVX_ENABLE_LOCAL_DEPLOYMENT=true`
  (`CVX_LXD_SOCKET_HOST` overrides the host socket path).
- `install-panel.sh` detects host LXD (snap/apt paths), appends
  `CVX_LXD_SOCKET_HOST` to `.env`, and includes the override automatically;
  uninstall removes both files' stack cleanly.

## 2. Migration

`c3a9d7e51b84` (revises `b7f2c1a94d03`):
- `nodes.kind` VARCHAR(16) NOT NULL DEFAULT 'agent' (+ index)
- `vps.deployment_mode` VARCHAR(16) NOT NULL DEFAULT 'node'
- `ck_vps_deployment_mode` CHECK constraint

SQLite note: as with earlier FK migration, `alembic upgrade` on SQLite does
not support ADD CONSTRAINT; fresh installs are unaffected (constraint baked
into metadata) and production runs PostgreSQL.

## 3. Tests

- New `tests/test_local_deploy.py` (8 cases): status gating, unavailable
  error, pydantic cross-field rules, happy-path create with auto-registered
  local node (capacity asserted), singleton reuse, remove/rotate guardrails,
  refresh endpoint, node-mode targeting rejection.
- Existing suites updated for the new abstract console method
  (`console_target`) — fakes return `ConsoleTarget`.
- Full suite green: **89 API tests** (25 functional + 56 security + 8 local),
  plus the agent's 61 unit tests untouched. Web: `tsc -b` clean, vite build
  clean.

## 4. Config reference

| Env | Default | Purpose |
| --- | --- | --- |
| `CVX_ENABLE_LOCAL_DEPLOYMENT` | `false` | Master switch for local mode |
| `CVX_LXD_SOCKET_PATH` | unset | In-container socket override (rarely needed) |
| `CVX_LOCAL_CONSOLE_SHELL` | `/bin/bash` | Shell used for local consoles |

## 5. Follow-ups (post-1.1 candidates)

- Local backup restore without the LXD CLI (streaming import API).
- Live per-VPS process/network counters for local mode already come from
  LXD state; consider unifying agent + local metric sampling cadence.
- Optional Incus-only deployments currently ride the same socket path
  detection (`/var/lib/incus/unix.socket` candidate) but are not officially
  supported yet.
