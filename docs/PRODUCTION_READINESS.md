# CVX Panel — Production Readiness

Status: **V1 hardening complete.** This document states what is verified, what
is intentionally out of scope for V1, and what to do before serious scale.
Findings and their resolution are tracked in `V1_GAP_AUDIT.md`.

## Verified in this codebase

- **Test suites**: 81 API tests (25 functional + 56 adversarial/security) and
  61 agent unit tests, all passing. Security suite covers privilege
  escalation, IPAM races, rate limits, enrollment replay, heartbeat
  reconciliation, cloud-init injection, capacity accounting, console abuse,
  SSRF/RBAC, injection attempts, error-envelope shape, and failure injection
  (provider delete failures) plus service-level concurrency.
- **Atomicity**: IP claims and enrollment-token redemption use conditional
  UPDATEs with rowcount checks — correct under concurrent loss (proven by the
  race test on an isolated WAL database).
- **Authorization**: owner/admin/user matrix enforced in services; owner-role
  changes owner-only; last-owner lockout prevented; node details admin-only
  with a slimmed list projection for users.
- **Agent surface**: no exec endpoint; name allowlists at both tiers; typed
  error mapping; snapshot-safe deletes; DNS re-validation; clamped console;
  path-restricted backup restore; systemd hardening in the installer.
- **Observability**: `x-request-id` on every response + error envelopes,
  `/readyz` gating on DB+Redis, structured logging setup, audit log with
  redaction.

## Known limitations (accepted for V1)

| Area | Limitation | Mitigation until V2 |
|---|---|---|
| Backups | Node-local only; node loss loses backups | Off-node restic/borg on nodes; pg_dump off-site |
| Rate limiting | Fails open when Redis is down | Monitor Redis; firewall auth endpoints at proxy if needed |
| Metrics | In-DB rolling window (30 d retention) | Move to TSDB (VictoriaMetrics) if cardinality grows |
| Single control plane | One api container | Run uvicorn replicas behind nginx; DB/Redis already external |
| Agent TLS | Trust-on-enrollment; no mTLS | Restrict :9700 to control-plane egress IP |
| Console recording | None (live only) | Audit requirement? Add optional sidecar ttyrec |

## Pre-scale checklist

1. Load-test auth + VPS create paths (rate limiter keys scale per user+IP).
2. Set explicit `CVX_TRUSTED_PROXIES` (never run uvicorn trusting all proxies).
3. Postgres: connection pool sizing (`CVX_DB_POOL_SIZE`, overflow) vs uvicorn
   workers; enable `pg_stat_statements`.
4. Schedule `VACUUM ANALYZE`; monitor `metrics` table growth vs 30-day retention.
5. Alerting wired to `/readyz`, node heartbeat age, and audit-log volume anomalies.
6. Verify backup restores (Postgres AND a sample VPS backup) into staging.
7. Rotate `CVX_SECRET_KEY` on a schedule agreed with node re-enrollment windows.

## Scale ceilings (rough)

- Per control plane: thousands of VPS rows / hundreds of nodes are fine —
  heartbeats are the load driver (30 s × N nodes ≈ N/30 rps of writes).
- Beyond ~500 nodes: shard heartbeat ingestion or lengthen interval; consider
  a queue between agent and reconciler.

## What "done" meant for V1

Every finding in `V1_GAP_AUDIT.md` is either fixed with tests (status FIXED)
or explicitly listed above as accepted-with-mitigation. No invented gaps:
each item traces to a concrete code path reviewed during the audit.
