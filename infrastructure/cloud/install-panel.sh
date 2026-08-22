#!/usr/bin/env bash
# ============================================================================
# CVX Panel — one-click installer for any VPS (Ubuntu/Debian)
#
# Installs Docker, deploys the full panel stack, and wires a Cloudflare
# Tunnel so the panel gets HTTPS without opening ports or touching DNS.
#
# Quick start (managed tunnel — recommended):
#
#   1. Cloudflare Dashboard -> Zero Trust -> Networks -> Tunnels -> Create
#   2. Copy the tunnel token
#   3. Run on your VPS:
#
#   curl -fsSL https://raw.githubusercontent.com/FaaizJohar/CVX-VPS/main/infrastructure/cloud/install-panel.sh \
#     | sudo CVX_CF_TUNNEL_TOKEN=<token> CVX_PANEL_DOMAIN=panel.example.com bash
#
#   4. In the tunnel's Public Hostname settings add:
#        subdomain: panel.example.com  ->  Service: HTTP -> localhost:8080
#
# No token? A temporary trycloudflare.com URL is issued instead (testing only).
#
# Env vars:
#   CVX_CF_TUNNEL_TOKEN   Cloudflare Tunnel token (managed tunnel)
#   CVX_PANEL_DOMAIN      Public hostname (sets CVX_PUBLIC_BASE_URL)
#   CVX_OWNER_EMAIL       Bootstrap owner email    (default: admin@cvx.local)
#   CVX_OWNER_PASSWORD    Bootstrap owner password (default: random, saved to .env)
#   REPO_URL              Source repo              (default: this project)
#   CVX_INSTALL_DIR       Install location         (default: /opt/cvx-panel)
#
# Re-running repairs/updates an existing install.  '--uninstall' removes it.
# ============================================================================
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/FaaizJohar/CVX-VPS.git}"
INSTALL_DIR="${CVX_INSTALL_DIR:-/opt/cvx-panel}"
CF_TOKEN="${CVX_CF_TUNNEL_TOKEN:-}"
PANEL_DOMAIN="${CVX_PANEL_DOMAIN:-}"
OWNER_EMAIL="${CVX_OWNER_EMAIL:-admin@cvx.local}"
OWNER_PASSWORD="${CVX_OWNER_PASSWORD:-}"
BIND="127.0.0.1:8080"
CLOUDFLARED_BIN=/usr/local/bin/cloudflared
QUICK_TUNNEL_UNIT=/etc/systemd/system/cvx-quicktunnel.service

log() { printf '\n\033[1;36m[cvx]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[cvx] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run as root (use sudo)."

if [ "${1:-}" = "--uninstall" ]; then
  log "Uninstalling CVX Panel..."
  systemctl disable --now cvx-quicktunnel.service 2>/dev/null || true
  rm -f "$QUICK_TUNNEL_UNIT"
  cloudflared service uninstall 2>/dev/null || true
  if [ -d "$INSTALL_DIR" ]; then
    (cd "$INSTALL_DIR" && docker compose down -v) || true
  fi
  rm -rf "$INSTALL_DIR"
  log "Removed (Docker itself left intact)."
  exit 0
fi

# ---------------------------------------------------------------- docker ---
if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker..."
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null 2>&1 || die "Docker Compose plugin missing."

# ------------------------------------------------------------------- repo --
if [ -d "$INSTALL_DIR/.git" ]; then
  log "Updating existing checkout..."
  git -C "$INSTALL_DIR" fetch --depth 1 origin main
  git -C "$INSTALL_DIR" reset --hard origin/main
else
  log "Cloning $REPO_URL ..."
  rm -rf "$INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# -------------------------------------------------------------------- env --
rand() { openssl rand -hex 24; }
if [ ! -f .env ] || ! grep -q "^CVX_SECRET_KEY=" .env 2>/dev/null; then
  log "Generating .env (secrets are created once and kept)..."
  [ -n "$OWNER_PASSWORD" ] || OWNER_PASSWORD="$(rand)"
  {
    echo "CVX_ENVIRONMENT=production"
    [ -n "$PANEL_DOMAIN" ] && echo "CVX_PUBLIC_BASE_URL=https://$PANEL_DOMAIN"
    cat <<EOF
CVX_SECRET_KEY=$(openssl rand -hex 48)
CVX_SESSION_COOKIE_SECURE=true
CVX_DB_USER=cvx
CVX_DB_PASSWORD=$(rand)
CVX_DB_NAME=cvx
CVX_BOOTSTRAP_OWNER_EMAIL=$OWNER_EMAIL
CVX_BOOTSTRAP_OWNER_PASSWORD=$OWNER_PASSWORD
CVX_BEHIND_PROXY=true
CVX_TRUSTED_PROXIES=
CVX_HTTP_PORT=$BIND
EOF
  } > .env
  chmod 600 .env
fi
set -a; . ./.env; set +a

# ------------------------------------------------------------------- stack --
log "Building and starting the stack (first build takes a few minutes)..."
docker compose -f infrastructure/docker-compose.prod.yml up -d --build

log "Waiting for the control plane to become ready..."
for i in $(seq 1 60); do
  if docker compose -f infrastructure/docker-compose.prod.yml exec -T api \
      python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/readyz',timeout=3)" \
      >/dev/null 2>&1; then
    break
  fi
  [ "$i" -eq 60 ] && { docker compose -f infrastructure/docker-compose.prod.yml logs --tail 40 api; die "API did not become ready."; }
  sleep 5
done
log "Control plane is READY."

# ------------------------------------------------------------- cloudflared --
cf_quick_url() {
  journalctl -u cvx-quicktunnel.service --no-pager -n 200 2>/dev/null \
    | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -n1
}

install_cloudflared() {
  command -v "$CLOUDFLARED_BIN" >/dev/null 2>&1 && return 0
  log "Installing cloudflared..."
  ARCH=$(uname -m); case "$ARCH" in x86_64) CFARCH=amd64;; aarch64) CFARCH=arm64;; *) die "Unsupported arch: $ARCH";; esac
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CFARCH}" \
    -o "$CLOUDFLARED_BIN"
  chmod +x "$CLOUDFLARED_BIN"
}

if [ -n "$CF_TOKEN" ]; then
  install_cloudflared
  log "Registering Cloudflare Tunnel (token mode)..."
  cloudflared service install "$CF_TOKEN" >/dev/null
  systemctl enable --now cloudflared >/dev/null 2>&1 || true
  echo
  echo "============================================================"
  echo " CVX Panel is up. Finish the public hostname in Cloudflare:"
  echo "   Zero Trust -> Networks -> Tunnels -> your tunnel ->"
  echo "   Public Hostname:"
  echo "     ${PANEL_DOMAIN:-<your-subdomain>.<your-domain>}  ->  HTTP -> localhost:8080"
  echo "============================================================"
else
  install_cloudflared
  log "No tunnel token given — starting an ephemeral trycloudflare tunnel..."
  cat > "$QUICK_TUNNEL_UNIT" <<UNIT
[Unit]
Description=CVX Panel quick tunnel
After=network-online.target docker.service
Wants=network-online.target

[Service]
ExecStart=$CLOUDFLARED_BIN tunnel --url http://$BIND --no-autoupdate
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now cvx-quicktunnel.service
  QUICK_URL=""
  for i in $(seq 1 12); do QUICK_URL="$(cf_quick_url)" && [ -n "$QUICK_URL" ] && break; sleep 5; done
  echo
  echo "============================================================"
  echo " CVX Panel (temporary URL — changes on restart):"
  echo "   ${QUICK_URL:-<see: journalctl -u cvx-quicktunnel>}"
  echo " For a permanent domain, re-run with CVX_CF_TUNNEL_TOKEN."
  echo "============================================================"
fi

echo
echo " Owner login:   $OWNER_EMAIL"
grep -q '^CVX_BOOTSTRAP_OWNER_PASSWORD=' .env && echo " Owner password: stored in $INSTALL_DIR/.env (chmod 600)"
echo " Manage:        cd $INSTALL_DIR && docker compose -f infrastructure/docker-compose.prod.yml logs -f api"
echo " Uninstall:     sudo bash $INSTALL_DIR/infrastructure/cloud/install-panel.sh --uninstall"
