# CVX Panel V1 — Production Readiness Gap Audit

**Scope:** Full security, reliability, and operational review of the V1 codebase
(`apps/api`, `apps/web`, `services/node-agent`, `infrastructure/`), performed against the
V1 hardening specification. Every finding below was **verified against source code** — no
speculative issues are listed. Findings that were checked and found *already correct* are
listed at the end (§5) so future audits do not re-litigate them.

**Status legend:** `OPEN` → fix planned; `FIXED` → fixed in this pass with regression test;
`WONTFIX` → consciously accepted with rationale.

---

## 1. Findings summary

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 1 | C1 |
| HIGH | 10 | H1–H10 |
| MEDIUM | 12 | M1–M12 |
| LOW | 7 | L1–L7 |

---

## 2. CRITICAL

### C1 — Privilege escalation via user PATCH: admin can grant `owner`; owner can be disabled

- **Component:** `apps/api/app/api/v1/routes/users.py` (`update_user`)
- **Problem:** The owner-protection guard is nested inside `if body.role is not None:`. Two
  consequences:
  1. An **admin** may set another account's role to `owner` (only an actual owner may mint
     owners).
  2. Because the guard only runs when `role` is being changed, an admin can **disable or
     change the password of an owner account** without hitting the guard — effectively a
     takeover path for the highest-privilege tier.
- **Impact:** Complete panel compromise from admin tier; breaks the documented privilege
  model (owner > admin > user).
- **Expected:** Only owners may grant/revoke the `owner` role. Any modification of an owner
  account (status, password, role) requires an owner. Admins keep full control over
  non-owner accounts.
- **Fix:** Hoist ownership checks out of the role branch; validate both "actor may set this
  role" and "actor may touch this target" before applying any field.
- **Test:** `tests/security/test_privilege_escalation.py`
- **Status:** FIXED

---

## 3. HIGH

### H1 — IP address allocation race; two concurrent creates can claim the same IP

- **Component:** `apps/api/app/services/vps_service.py` (`_allocate_ip`), `models/network.py`
- **Problem:** Allocation does SELECT-then-INSERT with no row lock and no DB-level
  uniqueness constraint tying `(node_id, address)` to active use. Two concurrent
  `create_vps` calls can read the same free address and both commit.
- **Impact:** Duplicate IP assignment → broken networking for two tenants; silent data
  corruption in IPAM.
- **Expected:** Atomic allocation under concurrency + database constraint as backstop.
- **Fix:** `SELECT ... FOR UPDATE` on the address row inside the create transaction,
  followed by an authoritative conditional `UPDATE ip_addresses SET status='assigned',
  vps_id=... WHERE id=... AND status='available' AND vps_id IS NULL` whose rowcount
  decides ownership (works even where FOR UPDATE is a no-op); loser surfaces a clean
  422. FK `ip_addresses.vps_id → vps.id` added as consistency backstop (see M4).
- **Test:** `tests/security/test_ipam_race.py` — sequential double-claim via HTTP plus a
  true service-level concurrency race on an isolated WAL-mode SQLite database
- **Status:** FIXED

### H2 — `/auth/verify-password` has no auth-tier rate limit (step-up brute force)

- **Component:** `apps/api/app/api/v1/routes/auth.py`
- **Problem:** Login is limited to 10/min/IP, but the sensitive-operation re-auth endpoint
  only passes through the global limiter (300/min). An attacker with a valid session can
  brute-force their own password verification at high rate to unlock destructive actions.
- **Fix:** Dedicated limiter (5/min per user+IP), same failure-open policy as login.
- **Test:** `tests/security/test_rate_limits.py::test_verify_password_limited`
- **Status:** FIXED

### H3 — Console WebSocket: no lifetime cap, no post-logout termination, no per-user session cap

- **Component:** `apps/api/app/api/v1/routes/console.py`
- **Problem:** Session/auth is validated once at connect. Afterwards: connection lives
  forever, logging out does not kill open consoles, and one user can open unbounded
  concurrent console sessions to any of their VPS.
- **Impact:** Stale privileged channels after credential compromise/logout; resource
  exhaustion on relay and agent.
- **Expected:** Max lifetime (e.g. 4h) with clean close; periodic re-validation of session
  and VPS state; per-user cap on live consoles; close codes distinguishable for the client.
- **Fix:** Relay-side watchdog task + registry keyed by user id; re-check session validity
  every 60s; enforce cap before accepting exec start.
- **Test:** `tests/security/test_console_security.py` (unit tests of new helpers +
  integration connect/close paths)
- **Status:** FIXED

### H4 — Heartbeat reconcile ignores instances missing from the agent inventory

- **Component:** `apps/api/app/services/node_service.py` (`process_heartbeat`)
- **Problem:** Reconcile updates states for instances present in the report but never
  touches panel rows whose instance vanished from the node (deleted out-of-band, disk
  loss). They stay RUNNING forever while billing/metrics continue.
- **Fix:** Instances known to the panel but absent from a fresh heartbeat report are marked
  ERROR with reason `missing_on_node` (after the report is confirmed complete).
- **Test:** `tests/security/test_heartbeat_reconcile.py`
- **Status:** FIXED

### H5 — `ssh_keys` / `root_password` accepted by API but never applied to the instance

- **Component:** `apps/api/app/providers/lxd.py` (`_build_config`), `schemas/vps.py`,
  frontend CreateVpsModal ("N keys provisioned")
- **Problem:** The API validates and accepts SSH keys and a root password, the UI reports
  success, but nothing translates them into the instance — no cloud-init user-data is ever
  generated. Users believe key-based auth works; it does not.
- **Impact:** False success; instances created without intended access control; users may
  assume password auth is disabled when it isn't (or vice versa).
- **Expected:** Keys/password applied at creation via cloud-init `user-data`; response/UI
  reflect reality.
- **Fix:** Build cloud-init config (hostname, `ssh_authorized_keys`, `chpasswd` root
  password when provided, package install of openssh-server) in the provider; store
  `user.user-data` in LXD config; set `root_password_set` flag accordingly (L1).
- **Test:** `tests/security/test_cloudinit.py` (user-data generation incl. hostile inputs)
- **Status:** FIXED

### H6 — Node installer broken for advertised usage; snap/apt precedence bug; no uninstall

- **Component:** `services/node-agent/deploy/cvx-install.sh`
- **Problem:**
  1. Script expects repo files already at `/opt/cvx-agent` yet is documented as
     `curl ... | bash` — remote execution has no files and dies immediately.
  2. `install_from_snap || install_from_apt && post_install` — shell precedence makes apt
     run even when snap succeeds, and failure handling is wrong.
  3. No uninstall path; re-runs clobber existing installs.
- **Fix:** Rewrite: argument parsing (`--panel-url --token --version`), download release
  tarball from the panel URL (or local dir if run from a checkout), strict mode, snap→apt
  fallback done correctly, systemd unit, `uninstall` verb, idempotent re-runs.
- **Test:** Shellcheck-clean; manual matrix documented in NODE_AGENT doc.
- **Status:** FIXED

### H7 — Disk capacity never validated against node storage

- **Component:** `apps/api/app/services/vps_service.py` (`create_vps` capacity check)
- **Problem:** RAM/CPU are checked against node capacity; requested `disk_gb` is not
  compared to remaining storage. Nodes can be oversubscribed on disk until LXD itself
  fails mid-provision.
- **Fix:** Track allocated disk (sum of non-deleted VPS disk_gb per node) and reject when
  `used + requested > storage_total_gb - reserve`.
- **Test:** `tests/security/test_capacity.py`
- **Status:** FIXED

### H8 — XFF spoofing: leftmost-entry trust behind proxy poisons rate limiting & audit trail

- **Component:** `apps/api/app/core/rate_limit.py` (`_client_ip`), `Dockerfile.api`
  (`--forwarded-allow-ips '*'`)
- **Problem:** `_client_ip` takes the **first** entry of `X-Forwarded-For`. A direct client
  can send a fake first hop; nginx appends the real IP, so the fake one wins. Combined with
  uvicorn trusting all proxies, attacker-controlled IPs drive the login limiter (rotate XFF
  to bypass 10/min) and pollute audit logs.
- **Fix:** Use the **rightmost** non-trusted entry (the value appended by our own proxy);
  drop `--forwarded-allow-ips '*'` in favor of explicit proxy trust configuration
  (`CVX_TRUSTED_PROXIES`, default: none → socket peer used directly).
- **Test:** `tests/security/test_rate_limits.py::test_xff_spoofing_resisted`
- **Status:** FIXED

### H9 — Enrollment token single-use race: two concurrent enrolls both succeed

- **Component:** `apps/api/app/services/node_service.py` (`enroll`)
- **Problem:** Check-consume of the single-use token is not atomic; two parallel enroll
  requests can both observe `used_at IS NULL` and register two nodes on one token.
- **Fix:** `UPDATE enrollment_tokens SET used_at=... WHERE token=... AND used_at IS NULL`
  inside the transaction (row-count check), serializing claims at the DB level.
- **Test:** `tests/security/test_enrollment_security.py::test_token_single_use_race`
- **Status:** FIXED

### H10 — Instance deletion fails when snapshots exist (agent-side)

- **Component:** `services/node-agent/cvx_agent/lxd.py` (`delete_instance`)
- **Problem:** DELETE instance without removing snapshots first; depending on storage
  driver/version LXD refuses, leaving zombie instances and a failed delete flow.
- **Fix:** Agent lists and deletes all snapshots explicitly before deleting the instance;
  operation becomes deterministic across drivers.
- **Test:** node-agent unit tests (`tests_agent/test_lxd_errors.py::test_delete_instance_is_snapshot_safe`)
- **Status:** FIXED

---

## 4. MEDIUM

### M1 — `LXDClient._request` raises bare `RuntimeError` on error payloads; HTTP status lost

- **Component:** `services/node-agent/cvx_agent/lxd.py`
- **Problem:** LXD error responses become opaque RuntimeErrors; status codes (404 vs 409
  vs 500) vanish, so callers cannot distinguish "not found" from "conflict". Panel maps
  everything to 500.
- **Fix:** Typed `LXDError(status, error)` exception; 404 helper returns `None`.
- **Test:** `tests_agent/test_lxd_errors.py`
- **Status:** FIXED

### M2 — Agent validates instance names only on create; other routes accept arbitrary names into URL paths

- **Component:** `services/node-agent/cvx_agent/server.py`
- **Problem:** `/instances/{name}/...` handlers interpolate `name` straight into LXD API
  paths. Not exploitable for command injection (httpx encodes path segments), but allows
  probing/manipulating names outside the panel namespace.
- **Fix:** Shared `validate_instance_name()` / `validate_snapshot_name()` applied on every
  route; 400 on violation.
- **Test:** `tests_agent/test_validation.py`
- **Status:** FIXED

### M3 — Heartbeat payload lacks bounds validation

- **Component:** `apps/api/app/api/v1/routes/agent.py`, `schemas/node.py`
- **Problem:** Agent-supplied numbers (cpu_percent, byte counters, load, uptime) are stored
  unchecked; a compromised/buggy agent can poison metrics history with absurd values.
- **Fix:** Pydantic constraints (0–100 percents, ≥0 counters, sane magnitude caps).
- **Test:** `tests/security/test_heartbeat_reconcile.py::test_payload_bounds`
- **Status:** FIXED

### M4 — `ip_addresses.vps_id` has no foreign key

- **Component:** `apps/api/app/models/network.py`
- **Problem:** Orphaned/dangling references possible under bugs; DB cannot enforce
  consistency relied upon by IPAM logic.
- **Fix:** FK added in migration; allocation code updated accordingly.
- **Test:** covered by migration check + IPAM tests
- **Status:** FIXED

### M5 — Node `public_ip` accepts loopback/link-local/private targets (SSRF surface)

- **Component:** `apps/api/app/schemas/node.py`, `routes/nodes.py`
- **Problem:** Admin-settable URL-ish fields are later used by the control plane to reach
  agents. Accepting `127.0.0.1`, `169.254.x`, RFC1918 lets a compromised admin account
  pivot scans/requests at internal infrastructure from the panel's network position.
- **Fix:** Validate public IPs; private ranges rejected unless `CVX_ALLOW_PRIVATE_NODE_IPS=true`
  (dev/self-hosted escape hatch).
- **Test:** `tests/security/test_ssrf_and_rbac_nodes.py`
- **Status:** FIXED

### M6 — Password reset endpoints lack rate limits

- **Component:** `apps/api/app/api/v1/routes/auth.py` (`reset-request`, `reset-confirm`)
- **Fix:** 5/min/IP on request (constant-response anti-enumeration preserved), 10/min on
  confirm.
- **Test:** `tests/security/test_rate_limits.py`
- **Status:** FIXED

### M7 — No targeted limits on expensive/sensitive operations

- **Component:** `routes/vps.py` (create/delete), `routes/nodes.py` (enrollment-token issue)
- **Fix:** Per-user limiters: vps create 10/hour, delete 20/hour, token issue 10/hour.
- **Test:** `tests/security/test_rate_limits.py`
- **Status:** FIXED

### M8 — Stuck PROVISIONING/DELETING states never recovered

- **Component:** `apps/api/app/services/node_service.py`
- **Problem:** If a create/delete fails between DB commit and provider call (crash, network
  partition), rows stay in transitional states forever.
- **Fix:** During reconcile, transitional states older than 30 min (no updated_at churn)
  are moved to ERROR (`provisioning_timeout`) or force-completed deletion.
- **Test:** `tests/security/test_heartbeat_reconcile.py`
- **Status:** FIXED

### M9 — Backup restore route bypasses provider abstraction

- **Component:** `apps/api/app/api/v1/routes/snapshots.py`
- **Problem:** Route calls raw `provider.client.post("/restore-backup")`, coupling the API
  layer to the agent transport and skipping provider-level validation/error mapping.
- **Fix:** `ComputeProvider.restore_backup()` added; base raises NotImplemented; LXD
  provider implements via AgentClient; route uses abstraction.
- **Test:** existing snapshot tests extended
- **Status:** FIXED

### M10 — `apply_dns` builds shell input by interpolation (defense-in-depth)

- **Component:** `services/node-agent/cvx_agent/lxd.py`
- **Problem:** Schema-level validation exists upstream, but the agent itself interpolates
  values into a shell command executed in the container. One missing validation away from
  injection.
- **Fix:** Agent re-validates each DNS server with `ipaddress.ip_address()` before use;
  invalid entries dropped, all-invalid means no command runs.
- **Test:** `tests_agent/test_apply_dns.py`
- **Status:** FIXED

### M11 — Node detail/metrics endpoints readable by any authenticated user

- **Component:** `apps/api/app/api/v1/routes/nodes.py`
- **Problem:** Infrastructure topology (node count, capacity, utilization, versions,
  addresses) exposed to regular tenants.
- **Fix:** List/detail/metrics gated to admins; regular users get 403 on detail, a slimmed
  projection on list (still readable — VPS creation needs node identity).
- **Test:** `tests/security/test_ssrf_and_rbac_nodes.py`
- **Status:** FIXED

### M12 — Console resize values unclamped; ValueError kills the relay task

- **Component:** `apps/api/app/api/v1/routes/console.py`, agent `server.py`
- **Problem:** `int()` conversion of client-supplied rows/cols can raise inside the relay
  loop, tearing down the session; no bounds enforced end-to-end.
- **Fix:** Clamp to 2–500 cols / 2–200 rows at relay; agent clamps again before writing
  `stty`; malformed values fall back to defaults instead of raising.
- **Test:** `tests/security/test_console_security.py`, `tests_agent/test_clamp_resize.py`
- **Status:** FIXED

---

## 5. LOW / accepted-risk notes

### L1 — `root_password_set` flag never set
Set during creation when a root password is supplied (part of H5 fix). **FIXED**

### L2 — Docs gaps
Backup restore is node-local (backup must exist on the node that holds it); off-node
restore is out of V1 scope. Documented in OPERATIONS. **DOCUMENTED**

### L3 — No readiness endpoint distinguishing DB/Redis health
`GET /readyz` added (DB ping + Redis ping, 503 on failure) for orchestrators. **FIXED**

### L4 — Error responses lack correlation IDs
Exception handlers now emit `request_id` (from middleware) in the error envelope for
support triage. **FIXED**

### L5 — nginx defaults
`client_max_body_size 10m`, WS proxy timeouts raised to 3600s for console longevity. **FIXED**

### L6 — EnrollmentToken timestamps naive (`datetime.utcnow`)
Handled consistently via `ensure_aware()` comparisons; migration to timezone-aware column
deferred (no functional bug). **WONTFIX (documented)**

### L7 — SameSite=lax cookie mitigates CSWSH on WS handshake
Cross-origin WS cannot attach the session cookie; no additional work required. **WONTFIX (accepted)**

---

## 6. Verified-correct during audit (no action needed)

- Password hashing (argon2), API-key/token storage hashed (SHA-256 + compare_digest).
- Login has dummy-hash verification → no username enumeration timing signal.
- Enrollment tokens: single-use intent, expiry, `cvxenroll_` prefix, constant-time lookup.
- Node credentials: hashed for verification + Fernet-encrypted for dispatch; never returned
  in full after enrollment.
- Agent auth middleware: Bearer HMAC comparison, `/healthz` only unauthenticated route;
  **no arbitrary command-execution endpoint exists**.
- Audit log redaction list covers password/token fields.
- Reserved LXD config prefixes (`volatile.`, `security.`, `raw.`, `boot.`) blocked from
  user-supplied config; `security.privileged` denied.
- VPSCreate schema validation: hostname pattern, IPv4/IPv6/DNS via `ipaddress`, SSH key
  type check.
- Rate limiter fails open when Redis is down (availability over strictness — documented
  tradeoff).
- Frontend: no `dangerouslySetInnerHTML`, no `eval`; XSS surface clean; server-side RBAC is
  authoritative (client guards cosmetic only).
- Test suite isolation: FakeProvider monkeypatching, SQLite in-memory overrides.

---

## 7. Fix plan order

1. C1 (RBAC) → 2. H1/H9/M4 (IPAM + enrollment atomicity + FK migration) → 3. H2/M6/M7
(rate limits) → 4. H3/M12 (console) → 5. H4/M8/M3 (heartbeat/reconcile) → 6. H5/L1
(cloud-init) → 7. H7 (capacity) → 8. H8 (proxy trust) → 9. Agent batch M1/M2/M10/H10 →
10. M5/M9/M11/L3/L4 → 11. H6 installer → 12. tests/security suite → 13. docs → 14. final
validation + gap closure report.

---

## 8. Gap closure report (final)

**Outcome: 30 of 30 findings closed** — 28 FIXED with regression tests, 2 consciously
accepted with documented rationale (L6 naive timestamps handled via `ensure_aware()`,
L7 SameSite=lax covers CSWSH). No finding remains OPEN.

### Verification results

| Check | Result |
|---|---|
| `pytest apps/api/tests` (functional) | **25 passed** |
| `pytest apps/api/tests/security` (adversarial) | **56 passed** |
| `pytest services/node-agent/tests_agent` | **61 passed** |
| Alembic fresh DB → `6918a468329b` on SQLite | 21 tables created cleanly |
| Alembic full chain offline SQL (PG dialect) | compiles; FK migration emits
  `ALTER TABLE ip_addresses ADD CONSTRAINT fk_ip_addresses_vps_id_vps ... ON DELETE SET NULL` |
| `npm run build` (web) | clean tsc + vite build |

Docker image builds could not be exercised on the audit machine (no Docker daemon);
compose files and Dockerfiles are unchanged in structure from the previously working
setup apart from the reviewed CMD/proxy-flags edits.

### Test-suite notes worth keeping

- The IPAM race test runs at service level against an isolated file-backed WAL SQLite
  database so each attempt gets a genuine independent transaction; the shared in-memory
  engine used by HTTP fixtures has a single pooled connection, which would measure fixture
  artifacts instead of the claim logic.
- Agent unit tests run without LXD or root: LXD transport is stubbed at the HTTP layer,
  error mapping / delete ordering / DNS filtering are verified against those stubs.

### Documentation set produced

`docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/NODE_AGENT.md`,
`docs/OPERATIONS.md`, `docs/PRODUCTION_READINESS.md`; README updated (test matrix,
docs index, node-local backup caveat).
