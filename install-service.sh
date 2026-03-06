#!/usr/bin/env bash
# install-service.sh — Install CR200 Bridge systemd services for Pi boot autostart.
#
# Usage:
#   sudo bash install-service.sh
#
# What it does:
#   1. Reads config.json (written by setup.py) for the node-sonos-http-api path.
#   2. Substitutes __USER__, __WORKDIR__, and __NODE_API_PATH__ in the service templates.
#   3. Copies the filled-in unit files to /etc/systemd/system/.
#   4. Enables and starts both services.
#
# Run setup.py first to generate config.json.

set -euo pipefail

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
SERVICES_DIR="$WORKDIR/services"
CONFIG_JSON="$WORKDIR/config.json"

# ---------------------------------------------------------------------------
# Must run as root
# ---------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: this script must be run as root (sudo bash install-service.sh)" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Determine the real (non-root) user
# ---------------------------------------------------------------------------
if [ -n "${SUDO_USER:-}" ]; then
    RUN_USER="$SUDO_USER"
elif command -v logname &>/dev/null && logname 2>/dev/null; then
    RUN_USER="$(logname)"
else
    RUN_USER="$(whoami)"
fi

echo "Installing CR200 Bridge services"
echo "  Working directory : $WORKDIR"
echo "  Service user      : $RUN_USER"

# ---------------------------------------------------------------------------
# Read node_api_path from config.json or from env (set by setup.py)
# ---------------------------------------------------------------------------
NODE_API_PATH="${NODE_API_PATH:-}"

if [ -f "$CONFIG_JSON" ]; then
    # Extract node_api_path with python3 (stdlib, no jq needed)
    EXTRACTED="$(python3 -c "
import json, sys
try:
    d = json.load(open('$CONFIG_JSON'))
    print(d.get('node_api_path', ''))
except Exception as e:
    print('', file=sys.stderr)
" 2>/dev/null || true)"
    if [ -n "$EXTRACTED" ]; then
        NODE_API_PATH="$EXTRACTED"
    fi
fi

# Fallback: probe common install locations
if [ -z "$NODE_API_PATH" ] || [ ! -f "$NODE_API_PATH" ]; then
    CANDIDATES=(
        "/usr/lib/node_modules/node-sonos-http-api/server.js"
        "/usr/local/lib/node_modules/node-sonos-http-api/server.js"
        "$HOME/.npm-global/lib/node_modules/node-sonos-http-api/server.js"
    )
    for c in "${CANDIDATES[@]}"; do
        if [ -f "$c" ]; then
            NODE_API_PATH="$c"
            break
        fi
    done
fi

if [ -z "$NODE_API_PATH" ] || [ ! -f "$NODE_API_PATH" ]; then
    echo ""
    echo "Error: node-sonos-http-api server.js not found." >&2
    echo "Install it with:  npm install -g node-sonos-http-api" >&2
    echo "Then re-run setup.py to record its path, or set NODE_API_PATH:" >&2
    echo "  sudo NODE_API_PATH=/path/to/server.js bash install-service.sh" >&2
    exit 1
fi

echo "  node-sonos-http-api: $NODE_API_PATH"
echo ""

# ---------------------------------------------------------------------------
# Install each service file (substitute placeholders)
# ---------------------------------------------------------------------------
install_service() {
    local name="$1"
    local template="$SERVICES_DIR/$name.service"
    local dest="/etc/systemd/system/$name.service"

    if [ ! -f "$template" ]; then
        echo "Error: template not found: $template" >&2
        exit 1
    fi

    sed \
        -e "s|__USER__|$RUN_USER|g" \
        -e "s|__WORKDIR__|$WORKDIR|g" \
        -e "s|__NODE_API_PATH__|$NODE_API_PATH|g" \
        "$template" > "$dest"

    echo "  Written: $dest"
}

install_service "node-sonos-http-api"
install_service "cr200-bridge"

# ---------------------------------------------------------------------------
# Enable and start
# ---------------------------------------------------------------------------
systemctl daemon-reload

systemctl enable node-sonos-http-api.service cr200-bridge.service
echo "  Enabled both services for boot."

systemctl start node-sonos-http-api.service
# Give the API a moment before starting the bridge
sleep 3
systemctl start cr200-bridge.service

echo ""
echo "── Service status ──────────────────────────────────────────"
systemctl status node-sonos-http-api.service cr200-bridge.service \
    --no-pager --lines=5 || true

echo ""
echo "Installation complete."
echo ""
echo "Useful commands:"
echo "  sudo systemctl status  cr200-bridge          # check status"
echo "  sudo journalctl -fu    cr200-bridge          # live logs"
echo "  sudo systemctl restart cr200-bridge          # restart after config change"
echo "  sudo systemctl disable cr200-bridge node-sonos-http-api  # remove autostart"
