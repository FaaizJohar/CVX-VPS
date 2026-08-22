# CVX Node Agent

The agent (`services/node-agent`) is a small FastAPI service installed on every
LXD host. It is the only component allowed to touch LXD, and it exposes no
arbitrary command execution — by design.

## Install (Ubuntu 22.04/24.04)

From the panel: **Nodes → Add node** → issue enrollment token → on the host:

```bash
curl -fsSL <install-url> | sudo CVX_ENROLL_TOKEN=<token> CVX_CONTROL_PLANE=<panel-url> bash
```

The installer (`deploy/cvx-install.sh`):

- installs system deps (snap LXD preferred, apt fallback),
- fetches the agent package from `CVX_AGENT_TARBALL_URL`
  (default `<control-plane>/downloads/cvx-agent-latest.tar.gz`) or a local path
  via `--local`,
- enrolls (generates the credential, exchanges it for registration),
- installs an inline systemd unit (`cvx-agent.service`, hardening:
  `ProtectSystem=strict` with explicit `ReadWritePaths`),
- is idempotent — re-running repairs/updates an existing install,
- supports `uninstall`.

Manual equivalent:

```bash
pip install ./node-agent-package
cvx-agent enroll --token <token> --control-plane <panel-url>
cvx-agent serve
```

## Runtime profile

| Aspect | Value |
|---|---|
| Listen | `:9700`, HTTPS |
| Auth | `Authorization: Bearer <credential>` (constant-time compare); `/healthz` exempt for local monitoring |
| Docs endpoints | disabled |
| LXD access | REST over `/var/snap/lxd/common/lxd/unix.socket` or `/var/lib/lxd/unix.socket` |
| Credential file | `/etc/cvx-agent/credential`, mode 0600 |

## API surface (control plane only)

```
GET    /v1/info                                  node + LXD facts
GET    /v1/instances/{name}                      instance state (404 → null upstream)
POST   /v1/instances                             create + start (+ optional DNS apply)
DELETE /v1/instances/{name}                      snapshot-safe delete (snaps first, then stop, then delete)
POST   /v1/instances/{name}/start|stop|restart|shutdown
PATCH  /v1/instances/{name}/config               string-map config patch
GET    /v1/instances/{name}/metrics              cpu/mem/disk/net counters
POST   /v1/instances/{name}/snapshots            create; GET list;
POST   .../snapshots/{snap}/rename|restore; DELETE .../snapshots/{snap}
POST   /v1/instances/{name}/backups              create (returns size + on-node path)
DELETE /v1/backups/{name}
POST   /v1/instances/{name}/restore-backup       lxc import of a whitelisted backup path
WS     /v1/instances/{name}/console              supervised `lxc exec` bridge
```

## Hardening details

- **Name allowlists**: instances `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`; snapshots/
  backups additionally allow dots, max 128. Every route validates before names
  can reach LXD URL paths or argv.
- **LXD error mapping**: all LXD failures become typed `LXDError(status,
  message)` → HTTP 502 with truncated detail; 404 on instance get maps to None.
- **DNS**: values re-validated with `ipaddress.ip_address()` inside the agent;
  invalid entries dropped silently, all-invalid means no command runs at all.
- **Console**: resize requests clamped to 2–500 cols × 2–200 rows before they
  reach `stty`; subprocess killed when either side disconnects.
- **Restore-backup**: path must start with `/var/snap/lxd/` or `/var/lib/lxd/`
  and contain no `..`.
- **systemd**: `ProtectSystem=strict`, `NoNewPrivileges`, private tmp.

## Backups are node-local (V1)

Backup archives are written by LXD onto the node's local disk
(`/var/snap/lxd/common/lxd/backups/` or `/var/lib/lxd/backups/`). The control
plane stores metadata only. There is **no off-node transfer in V1** — losing a
node loses its backups. Plan off-node copies (e.g. node-level restic to object
storage) until V2 adds panel-managed export.

## Development & tests

```bash
cd services/node-agent
pip install -e .            # plus fastapi uvicorn httpx pytest for tests
pytest ../tests_agent -q    # 61 unit tests (run from repo root)
```

Unit tests cover name validation, resize clamping, LXD error mapping (mocked
transport), snapshot-safe deletion ordering and DNS filtering — no LXD or root
required.
