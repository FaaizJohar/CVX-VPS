#!/usr/bin/env bash
# CVX Panel installer for hosts WITHOUT systemd (LXC/OpenVZ containers).
# Installs Docker manually, deploys the panel in nodes-only mode, and starts
# a temporary Cloudflare quick tunnel. Paste-proof: run this file with bash.
set -euo pipefail

REPO="FaaizJohar/CVX-VPS"
INSTALL_DIR="/opt/cvx-panel"
HTTP_PORT="${CVX_HTTP_PORT:-8080}"
TARBALL_URLS=(
  "https://github.com/${REPO}/archive/refs/heads/main.tar.gz"
  "https://github.com/${REPO}/releases/latest/download/cvx-panel-source.tar.gz"
)

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run as root."

log "Installing packages (docker.io, docker-compose-v2)"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || true
apt-get install -y -qq docker.io docker-compose-v2 curl openssl ca-certificates >/dev/null

log "Starting dockerd (no systemd detected path)"
if ! docker info >/dev/null 2>&1; then
  if [ -S /run/docker.sock ]; then rm -f /run/docker.sock; fi
  mkdir -p /var/log
  nohup dockerd >/var/log/dockerd.log 2>&1 &
  for _ in $(seq 1 30); do
    docker info >/dev/null 2>&1 && break
    sleep 1
  done
  if ! docker info >/dev/null 2>&1; then
    pkill dockerd 2>/dev/null || true
    sleep 2
    log "Retrying dockerd with --storage-driver=vfs --iptables=false"
    nohup dockerd --storage-driver=vfs --iptables=false >/var/log/dockerd.log 2>&1 &
    for _ in $(seq 1 45); do
      docker info >/dev/null 2>&1 && break
      sleep 1
    done
    docker info >/dev/null 2>&1 || { tail -50 /var/log/dockerd.log; die "dockerd failed to start (see /var/log/dockerd.log)"; }
  fi
fi
docker version --format 'docker {{.Server.Version}} OK'

log "Fetching source into ${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}.old"
[ -d "$INSTALL_DIR" ] && mv "$INSTALL_DIR" "${INSTALL_DIR}.old"
mkdir -p "$INSTALL_DIR"
ok=""
for url in "${TARBALL_URLS[@]}"; do
  log "Trying $url"
  if curl -fsSL "$url" | tar xz -C "$INSTALL_DIR" --strip-components=1; then ok=1; break; fi
done
[ -n "$ok" ] || { rmdir "$INSTALL_DIR" 2>/dev/null || true; die "Could not download source from any mirror."; }
[ -f "${INSTALL_DIR}/infrastructure/docker-compose.prod.yml" ] || die "Source incomplete (compose file missing)."

cd "$INSTALL_DIR"

if [ ! -f .env ]; then
  log "Generating .env"
  cat > .env <<EOF
CVX_ENVIRONMENT=production
CVX_SECRET_KEY=$(openssl rand -hex 48)
CVX_DB_USER=cvx
CVX_DB_PASSWORD=$(openssl rand -hex 24)
CVX_DB_NAME=cvx
CVX_BOOTSTRAP_OWNER_EMAIL=admin@example.com
CVX_BOOTSTRAP_OWNER_PASSWORD=$(openssl rand -hex 12)
CVX_BEHIND_PROXY=true
CVX_SESSION_COOKIE_SECURE=false
CVX_HTTP_PORT=${HTTP_PORT}
EOF
  chmod 600 .env
else
  log ".env already exists, keeping it"
fi

log "Building and starting containers (this takes several minutes)"
docker compose --env-file .env -f infrastructure/docker-compose.prod.yml up -d --build

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${HTTP_PORT}/api/v1/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${HTTP_PORT}/api/v1/health" >/dev/null 2>&1 \
  && log "API healthy on port ${HTTP_PORT}" \
  || echo "WARNING: API not responding yet; check: docker compose logs api"

log "Starting temporary Cloudflare quick tunnel"
if ! pgrep -x cloudflared >/dev/null 2>&1; then
  curl -fsSL -o /usr/local/bin/cloudflared \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    || die "cloudflared download failed"
  chmod +x /usr/local/bin/cloudflared
  nohup /usr/local/bin/cloudflared tunnel --url "http://127.0.0.1:${HTTP_PORT}" --no-autoupdate >/var/log/cloudflared.log 2>&1 &
fi
URL=""
for _ in $(seq 1 20); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /var/log/cloudflared.log | tail -1)
  [ -n "$URL" ] && break
  sleep 2
done

OWNER_EMAIL=$(grep CVX_BOOTSTRAP_OWNER_EMAIL .env | cut -d= -f2)
OWNER_PASS=$(grep CVX_BOOTSTRAP_OWNER_PASSWORD .env | cut -d= -f2)

cat <<EOF

============================================================
  CVX Panel is deployed (nodes-only mode).

  Login email:     ${OWNER_EMAIL}
  Login password:  ${OWNER_PASS}

  Public URL:      ${URL:-NOT READY - rerun: grep trycloudflare /var/log/cloudflared.log}

  NOTE: This quick-tunnel URL changes if the process restarts.
  For a permanent domain, set CVX_CF_TUNNEL_TOKEN and re-run
  the standard install on a host that supports systemd.
============================================================
EOF
