# CVX V1.1 Implementation Report — Async Provisioning, One-Command Enrollment, Universal Local Compute

Scope: the four v1.1 gaps tracked in `docs/V1_GAP_AUDIT.md` that remained after the
initial dual-deployment release (see `docs/V1_1_RELEASE_REPORT.md`):

1. **One-command node enrollment** — no manual IP/hostname entry; a single copy-paste
   command enrolls a machine.
2. **Universal local compute** — local deployment works on any host via real capability
   probing, not just hosts with a KVM-capable / pre-provisioned LXD setup.
3. **Job-based async provisioning** — VPS creation returns immediately with a job id;
   progress is observable instead of holding the HTTP request open for minutes.
4. **Premium UI polish** — wizard-style Add Node flow, deployment chooser with job
   progress, typography and focus-state upgrades.

Everything below describes what is implemented and covered by tests in this repo.
Known limitations are listed explicitly at the end.

---

## 1. Architecture overview

```
POST /api/v1/vps (202)
  └─ VPSService.prepare_vps()          request-time validation, capacity check,
  │                                    atomic IPv4 claim, Fernet-encrypted root pw
  ├─ ProvisioningJob row (queued)      source of truth lives in the DB
  └─ enqueue_vps_create(job_id)        asyncio queue = wakeup channel only
        │
ProvisioningWorker (in-process)
  ├─ pump loop → bounded semaphore (4 concurrent provisions)
  ├─ per-job task: claim job → stage updates (preparing → creating_instance
  │  → finalizing) → VPSService.provision_vps(vps_id) in its own DB session
  ├─ 20-minute hard timeout per job
  └─ startup crash-recovery: re-enqueues queued/running jobs from previous run

GET  /api/v1/jobs/{id}                 poll
GET  /api/v1/jobs/{id}/events          SSE stream (fresh session per poll)
GET  /api/v1/jobs/by-vps/{vps_id}      active job or null when terminal
```

Key property: the asyncio queue is **never** the source of truth. If the process
crashes mid-flight, the VPS row stays `PROVISIONING` and the job row stays
`queued`/`running`; on restart both are reconciled (jobs re-enqueued, stale VPS
rows caught by the existing heartbeat transitional-timeout sweep).

`VPSService.create_vps()` remains as a synchronous prepare+provision path used by
tests/tools; it shares the caller's DB session so it does not depend on the
process-global engine.

## 2. Database changes

Migration: `apps/api/alembic/versions/e5b2c8f41a90_v11_provisioning_jobs.py`
(applied automatically by the API container entrypoint before uvicorn starts;
validated in isolation for both upgrade and downgrade via
`apps/api/alembic/validate_e5b2c8f41a90.py` — server defaults use the
Postgres/SQLite-portable `CURRENT_TIMESTAMP`).

- New table **`provisioning_jobs`**: `kind`, `status` (`queued|running|succeeded|failed`),
  `stage`, `progress`, `error`, `vps_id` (FK), `node_id` (FK), `user_id` (FK),
  timestamps. Indexed on status/vps/user.
- New column **`vps.root_password_encrypted`** — the bootstrap root password is now
  stored Fernet-encrypted at request time and decrypted by the worker when building
  the cloud-init payload. It is nulled out immediately after successful provisioning
  ("transient credential" lifetime).

## 3. API changes

### POST /api/v1/vps → **202 Accepted**

```json
{ "job_id": "...", "vps_id": "...", "status": "queued", "name": "web-01" }
```

All validation/capacity/IP errors still surface synchronously as 4xx before the job
is queued. Rate limiting unchanged (`10/hour/user`). Applies to **both** deployment
modes (`node` and `local`) — one uniform code path.

### Jobs endpoints (`app/api/v1/routes/jobs.py`)

- `GET /jobs/{id}` — owner/admin only; other users' jobs return **404** (existence
  not leaked), consistent with the VPS access checks.
- `GET /jobs/{id}/events` — SSE; polls with a fresh DB session each tick (the
  request-scoped identity map would otherwise cache stale rows), closes on terminal
  state, capped at 30 minutes.
- `GET /jobs/by-vps/{vps_id}` — latest *non-terminal* job, or literal `null` once
  finished; the frontend uses this to stop polling.

### Node enrollment (`app/schemas/node.py`, `app/services/node_service.py`)

- `NodeCreate.name`, `.hostname`, `.public_ip` are all **optional** now. Omitted
  identity fields get detection placeholders (`node-{hex6}`, `pending-detection`)
  and are replaced by real facts when the agent enrolls.
- Create-node and re-issue-token responses include:
  - `install_command`: ``curl -fsSL {base}/install/node | sudo bash -s -- --token … --control-plane {base}``
  - `expires_at` computed from `enrollment_token_ttl_seconds`.
- Enrollment tokens remain SHA-256-hashed, single-use (atomic claim), TTL-bounded,
  revocable.

## 4. Public installer endpoints (`app/main.py`)

Unauthenticated by design — they serve a fresh machine's first `curl`:

- `GET /install/node` — the installer script (`text/x-shellscript`).
- `GET /downloads/cvx-agent-latest.tar.gz` — agent package tarball, built once per
  process and cached in memory. Package dir resolution order: `CVX_AGENT_PACKAGE_DIR`
  env → `/srv/cvx/node-agent` (container image layout) → cwd variants. The Docker
  build context was moved to the repo root so `services/node-agent` ships inside the
  API image at `/srv/cvx/node-agent` (`.dockerignore` added to keep context small).
- `GET /downloads/cvx-agent-latest.tar.gz.sha256` — digest of the exact bytes served.

Installer hardening (`services/node-agent/deploy/cvx-install.sh`): argument parsing
(`--token/--control-plane/--local/uninstall`), token format check, HTTPS-only control
plane, staged download + SHA-256 verification, dedicated `cvx-agent` system user with
`lxd` group, hardened systemd unit (ProtectSystem=strict, Umask=077), idempotent
re-install, explicit detection checklist output.

Agent side: `cvx_agent.metrics.detect_public_ip()` (env-overridable echo services,
validated, failure non-fatal) sends `public_ip` at enroll and refreshes it during
heartbeats; the heartbeat loop is actually started in server lifespan now.

## 5. Universal local compute (`app/services/local_capability.py`)

`LocalComputeCapability` replaces the old binary available/unavailable check with a
real probe of the host:

- states: `READY` / `DEGRADED` / `UNAVAILABLE` / `NOT_CONFIGURED`
- probes: feature flag, LXD socket discovery, daemon ping, storage pool inventory,
  managed bridge networks, capacity snapshot
- every probe produces diagnostics with human hints (what to install/enable), so an
  unconfigured host gets actionable output instead of a dead end
- 45-second TTL cache + forced-refresh endpoint

Endpoints:

- `GET /api/v1/nodes/local/status` — rewritten on top of the capability service;
  keeps back-compat fields; admin-only extras gated.
- `POST /api/v1/nodes/local/refresh` — forces a fresh probe and updates the
  singleton `local-machine` node row's detected capacity.

No KVM requirement: the capability model treats LXD-in-a-container (no `/dev/kvm`)
as a valid target; VM-class features simply degrade.

## 6. Frontend changes (`apps/web`)

- **Add Node wizard** (`AdminNodesPage.tsx`): name optional ("Automatically
  detected"), location presets datalist, generated `install_command` shown in a
  copyable command block with token countdown; polls while pending and shows a
  success screen listing the specs the agent reported (hostname, IP, CPU/RAM/disk,
  LXD version) — proving what was auto-detected vs. assumed.
- **Deployment chooser** (`VPSCreatePage.tsx`): spec-mandated step with
  "Deploy on Node" / "Deploy Locally" cards (metadata lines, CTAs "Choose Node" /
  "Use This Machine"); create mutation handles the 202 `{job_id, vps_id}` payload.
- **Job progress** (`JobProgress.tsx`): polls `/jobs/by-vps/{id}` at 2s, progress
  bar + stage labels (Preparing → Creating instance → Finalizing), error surfacing;
  embedded in `VPSWorkspace` while status is creating/provisioning, alongside the
  provision-error alert for failures.
- **Overview compute section**: LOCAL card + per-node cards with CPU/RAM bars.
- **Polish**: Inter + JetBrains Mono loaded in `index.html`; graphite theme tokens;
  global focus-visible ring; `prefers-reduced-motion` handling; resource bar classes.

## 7. Security review notes

- Root password never crosses the worker boundary in plaintext logs; encrypted at
  rest in the request transaction, wiped post-provision.
- Job endpoints enforce ownership; cross-user job access → 404 (not 403) so
  existence isn't disclosed. Covered by test.
- Installer/token endpoints are public but inert without a valid single-use token;
  token reuse/expiry covered by test.
- Agent-supplied `public_ip` is schema-validated at enroll *and* heartbeat; forged
  values rejected with 422. Heartbeat IP changes raise a security event.
- The tarball/installer endpoints expose only the agent package (public code), no
  panel secrets; SHA-256 pinning protects against truncated/tampered downloads.

## 8. Test coverage

- `apps/api/tests`: **96 passed**
  - new `tests/test_v11_enrollment_jobs.py` (7): minimal-node create +
    install_command shape, hostname/IP adoption at enroll, forged-IP rejection,
    expired-token rejection, public installer/tarball/sha256 endpoints (incl.
    gzip magic + digest match), full job flow (queued → inline worker execution →
    succeeded, by-vps lifecycle, cross-user 404/403), heartbeat IP-change security
    event.
  - all prior suites migrated to the 202 flow; provisioning driven deterministically
    inline (`provision_vps` with caller-owned session) so no test depends on wall-
    clock polling.
  - conftest now points the app-level session factory at each test's engine, so
    worker/SSE code paths get the same in-memory DB.
- `services/node-agent`: **61 passed** (public-IP detection incl. env override and
  invalid-input fallbacks, enroll payload, heartbeat wiring).
- `apps/web`: `tsc -b && vite build` clean.

## 9. Known limitations (explicit)

- The provisioning worker is **single-process** (asyncio). Horizontal scaling needs
  a shared broker (e.g. Redis/Postgres SKIP LOCKED) — fine for the current
  self-hosted profile.
- SSE streams cap at 30 minutes per connection then require reconnect (client
  falls back to polling automatically).
- Backup-archive restore for local VPSes remains unsupported (unchanged from the
  v1.1 release report).
- Local mode still requires the LXD snap/socket present; what changed is that the
  UI/API now *diagnose* absence instead of failing opaquely. Container hosts
  without KVM can run containers but not VMs.
- `pending-detection` placeholder IPs must be replaced by a real enroll before the
  control plane can dial the node; nodes stuck pending are flagged by the effective
  status logic.
