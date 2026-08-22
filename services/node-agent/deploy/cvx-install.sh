#!/usr/bin/env bash
# CVX Node Agent installer.
#
# Remote usage (recommended):
#   curl -fsSL https://<panel>/deploy/cvx-install.sh -o cvx-install.sh
#   sudo CVX_ENROLL_TOKEN=<token> CVX_CONTROL_PLANE=<panel-url> bash cvx-install.sh
#
# Local checkout usage:
#   sudo CVX_ENROLL_TOKEN=<token> CVX_CONTROL_PLANE=<url> bash services/node-agent/deploy/cvx-install.sh --local .
#
# Other verbs:
#   sudo bash cvx-install.sh uninstall
set -euo pipefail

AGENT_USER=cvx
INSTALL_DIR=/opt/cvx-agent
VENV_DIR="$INSTALL_DIR/venv"
BIN_LINK=/usr/local/bin/cvx-agent
UNIT_FILE=/etc/systemd/system/cvx-agent.service
SERVICE_NAME=cvx-agent

log()  { echo "[*] $*"; }
ok()   { echo "[+] $*"; }
die()  { echo "[!] ERROR: $*" >&2; exit 1; }

require_root() {
  [[ $EUID -eq 0 ]] || die "run as root (sudo)."
}

# ---------------------------------------------------------------------------
# uninstall verb
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "uninstall" ]]; then
  require_root
  log "Stopping and disabling $SERVICE_NAME..."
  systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
  rm -f "$UNIT_FILE"
  systemctl daemon-reload 2>/dev/null || true
  rm -f "$BIN_LINK"
  rm -rf "$INSTALL_DIR"
  log "Enrollment data left in place (/etc/cvx-agent). Remove manually if desired."
  ok "CVX agent uninstalled."
  exit 0
fi

# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------
require_root

CVX_ENROLL_TOKEN="${CVX_ENROLL_TOKEN:-}"
CVX_CONTROL_PLANE="${CVX_CONTROL_PLANE:-}"
[[ -n "$CVX_ENROLL_TOKEN" ]]    || die "CVX_ENROLL_TOKEN is required."
[[ -n "$CVX_CONTROL_PLANE" ]]   || die "CVX_CONTROL_PLANE is required."

LOCAL_SRC=""
if [[ "${1:-}" == "--local" ]]; then
  LOCAL_SRC="${2:-}"
  [[ -n "$LOCAL_SRC" && -f "$LOCAL_SRC/pyproject.toml" ]] || die "--local <path-to-node-agent-repo> required."
fi

# --- LXD --------------------------------------------------------------------
install_lxd() {
  if command -v lxd >/dev/null 2>&1 && lxd --version >/dev/null 2>&1; then
    ok "LXD already installed: $(lxd --version)"
    return 0
  fi
  log "Installing LXD..."
  if command -v snap >/dev/null 2>&1; then
    # snap is the canonical channel; only fall back to apt when snap fails.
    if snap install lxd; then
      ok "LXD installed via snap."
      return 0
    fi
    log "snap install failed; falling back to apt."
  fi
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y lxd
  ok "LXD installed via apt."
}

install_lxd
lxd --version >/dev/null 2>&1 || die "LXD installation did not produce a working binary."

# Initialize LXD non-interactively if it has no storage pool yet.
if ! lxc storage list 2>/dev/null | grep -q '^| default'; then
  log "Initializing LXD (default profile)..."
  lxd init --auto || log "lxd init --auto failed; continuing (may already be initialized)."
fi

# --- agent code -------------------------------------------------------------
install_agent_code() {
  mkdir -p "$INSTALL_DIR"
  if [[ -n "$LOCAL_SRC" ]]; then
    log "Installing agent from local source: $LOCAL_SRC"
    rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' \
      "$LOCAL_SRC/cvx_agent" "$LOCAL_SRC/pyproject.toml" "$INSTALL_DIR/"
  else
    TARBALL_URL="${CVX_AGENT_TARBALL_URL:-$CVX_CONTROL_PLANE/downloads/cvx-agent-latest.tar.gz}"
    log "Downloading agent release from $TARBALL_URL"
    tmp="$(mktemp -d)"
    curl -fsSL "$TARBALL_URL" -o "$tmp/agent.tar.gz" \
      || die "download failed ($TARBALL_URL). Host the release tarball there or use --local."
    tar -xzf "$tmp/agent.tar.gz" -C "$INSTALL_DIR" --strip-components=1
    rm -rf "$tmp"
  fi
}

install_agent_code

# --- python env -------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip
fi

log "Creating venv at $VENV_DIR..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$INSTALL_DIR" \
  || die "pip install of the agent failed."
ln -sf "$VENV_DIR/bin/cvx-agent" "$BIN_LINK"

# --- systemd unit -----------------------------------------------------------
log "Writing systemd unit..."
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=CVX Node Agent
After=network-online.target snap.lxd.daemon.service
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=$VENV_DIR/bin/cvx-agent serve
Restart=always
RestartSec=5
# Hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/etc/cvx-agent /var/lib/lxd /var/snap/lxd
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$UNIT_FILE"

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

# --- enroll -----------------------------------------------------------------
if [[ -f /etc/cvx-agent/credential ]]; then
  log "Existing credential found — skipping enrollment (re-enroll manually to rotate)."
else
  log "Enrolling with control plane $CVX_CONTROL_PLANE..."
  cvx-agent enroll --control-plane "$CVX_CONTROL_PLANE" --token "$CVX_ENROLL_TOKEN"
fi

systemctl restart "$SERVICE_NAME"
sleep 2
systemctl --no-pager --lines=0 status "$SERVICE_NAME" \
  || die "service failed to start; check: journalctl -u $SERVICE_NAME -e"

ok "CVX agent installed, enrolled, and running."
echo "    Verify from the panel: Nodes → this node should show ONLINE."
