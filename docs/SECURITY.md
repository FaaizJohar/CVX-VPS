# CVX Panel — Security

## Threat model summary

- **Users** may only touch their own VPS/resources; admins manage users; owners
  manage owners. All authorization is enforced server-side in services, never
  in the SPA.
- **The node agent is the highest-value target on a node**: it holds root and
  talks to LXD. Its API is reachable only from the control plane over TLS with
  a per-node bearer credential.
- **The control plane never trusts node-reported state for billing/ownership
  decisions**; nodes report facts, the panel decides.

## Authentication & sessions

- Passwords: argon2-style hashing via passlib; minimum length configurable
  (`CVX_PASSWORD_MIN_LENGTH`, default 10).
- Sessions: opaque random tokens in an httpOnly `cvx_session` cookie,
  SameSite=strict, Secure in production. Sessions are DB rows — logout,
  admin revocation, and "revoke all my sessions" are immediate.
- Login, password reset request/confirm are rate limited per user+IP
  (5/min login attempts; 5/min reset requests; 10/min reset confirms).
- API keys: generated with `cvx` prefix, stored hashed, shown once.
- Bootstrap owner is created only while the users table is empty.

## Authorization (RBAC)

- Roles: `owner` > `admin` > `user`.
- Only owners can grant/revoke the owner role or modify owner accounts;
  the last active owner cannot demote/disable themselves (409).
- Node management endpoints are admin-only; the node **list** stays readable by
  regular users (needed to create VPS) but returns a slimmed projection without
  capacity counters, credentials or enrollment state.
- VPS access: owner or admin; workspaces additionally require password
  re-entry ("unlock") which sets a short-lived server-side unlock flag.

## Secrets

- Node credentials: generated at enrollment (32-byte urlsafe), returned exactly
  once, stored as hash (verification) + Fernet ciphertext (outbound calls).
  Rotation invalidates the previous secret instantly.
- Enrollment tokens: single-use, TTL 30 min (configurable), claimed atomically —
  replay after use fails closed.
- Fernet key derives from `CVX_SECRET_KEY`. Rotating it requires re-enrolling
  nodes (documented in OPERATIONS.md).
- Audit log redacts secret-shaped fields before persistence.

## Injection & input hardening

- All SQL through SQLAlchemy bound parameters; no string-built SQL anywhere.
- Instance/snapshot names validated at both ends:
  - control plane Pydantic validators,
  - agent allowlist regexes (`^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$` for instances,
    dots allowed for snapshots). Names interpolate into LXD URL paths and argv,
    hence the tight charset.
- cloud-init user-data is base64-encoded JSON — values survive transport
  verbatim and are never shell-interpolated. Hostile strings round-trip intact
  (covered by tests).
- DNS settings re-validated inside the agent (`ipaddress.ip_address`) before
  any command construction; invalid entries dropped, all-invalid = no-op.
- Backup restore paths must live under `/var/snap/lxd/` or `/var/lib/lxd/`
  and may not contain `..`.
- SSRF guard: node `public_ip` must be a globally-routable address unless
  `CVX_ALLOW_PRIVATE_NODE_IPS=true` (lab mode).

## Rate limiting

Redis fixed-window counters keyed by route class + client identity:

| Scope | Limit |
|---|---|
| Auth endpoints (login/register/reset) | 10/min default |
| VPS create | 10/h per user |
| VPS delete | 20/h per user |
| Enrollment token issue | 10/h |
| Default authenticated API | 300/min |

Client IP resolution uses the **rightmost** X-Forwarded-For entry when
`CVX_BEHIND_PROXY=true`; uvicorn's `--forwarded-allow-ips` restricts who may set
that header. If Redis is unavailable the limiter fails **open** (availability
over strictness) — monitor Redis.

## Console security

WebSocket console requires a valid session cookie *and* VPS access; the relay
enforces lifetime (4 h), periodic re-validation (60 s), concurrency cap (5/user)
and terminal size clamps. The agent side spawns `lxc exec` under the instance
name allowlist and kills the subprocess when either side disconnects.

## Transport

- Browser → nginx: TLS terminates at your proxy/LB; set
  `CVX_SESSION_COOKIE_SECURE=true`.
- Control plane → agent: HTTPS with the node credential as bearer token;
  self-signed certificates are pinned out of band at enrollment time.
- Agent binds :9700; firewall it to the control plane egress IP.

## Reporting

See SECURITY disclosure contact in README. Please include reproduction steps
and the `x-request-id` from the error envelope.
