#!/usr/bin/env python3
"""
CR200 Bridge — Interactive Setup Wizard

Run once (or any time you need to reconfigure):
    python3 setup.py

Writes config.json next to this file. The bridge (main.py) loads it
automatically at startup; re-running this wizard updates it in place.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(HERE, "config.json")

# Defaults that mirror the hardcoded dict in config.py
DEFAULTS = {
    "uuid": None,               # auto-generated if absent
    "household_id": "",
    "friendly_name": "CR200 Bridge",
    "http_port": 1400,
    "sonos_http_api_base": "http://localhost:5005",
    "log_level": "INFO",
    "status_port": 8080,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner():
    print()
    print("=" * 60)
    print("  CR200 Bridge — Setup Wizard")
    print("  Configures the bridge and (optionally) Pi boot autostart")
    print("=" * 60)
    print()


def prompt(label, default, hint=""):
    """Print an optional hint, then prompt for a value. Enter keeps the default."""
    if hint:
        print(f"    {hint}")
    val = input(f"  {label} [{default}]: ").strip()
    return val if val else str(default)


def prompt_choice(label, choices, default):
    """Prompt for a value restricted to a set of choices."""
    choices_str = "/".join(choices)
    while True:
        val = prompt(label, default, hint=f"    Choices: {choices_str}")
        if val.upper() in [c.upper() for c in choices]:
            return val.upper()
        print(f"    Invalid choice. Please enter one of: {choices_str}")


def section(title):
    print()
    print(f"── {title} {'─' * max(0, 54 - len(title))}")


def ok(msg):
    print(f"  ✓ {msg}")


def warn(msg):
    print(f"  ! {msg}")


# ---------------------------------------------------------------------------
# Step 1 — Python version check
# ---------------------------------------------------------------------------

def check_python():
    section("Python version")
    if sys.version_info < (3, 10):
        print(f"  ERROR: Python 3.10+ required. Found: {sys.version}")
        sys.exit(1)
    ok(f"Python {sys.version.split()[0]}")


# ---------------------------------------------------------------------------
# Step 2 — Node.js check
# ---------------------------------------------------------------------------

def check_node():
    section("Node.js")
    node = shutil.which("node")
    if not node:
        warn("node not found in PATH.")
        print("    Install Node.js: https://nodejs.org  or  sudo apt install nodejs npm")
        print("    Then install the API:  npm install -g node-sonos-http-api")
        return None
    try:
        result = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5)
        ok(f"node {result.stdout.strip()}  ({node})")
    except Exception as e:
        warn(f"Could not query node version: {e}")
    return node


# ---------------------------------------------------------------------------
# Step 3 — node-sonos-http-api connectivity & auto-discovery
# ---------------------------------------------------------------------------

def discover_api(api_base):
    """Try to reach the API and return (household_id, rooms) or (None, [])."""
    try:
        url = api_base.rstrip("/") + "/zones"
        with urllib.request.urlopen(url, timeout=4) as resp:
            zones = json.loads(resp.read())
        household_id = None
        rooms = []
        for zone in zones:
            if household_id is None:
                household_id = zone.get("householdId") or zone.get("household_id")
            coord = zone.get("coordinator", {})
            name = coord.get("roomName") or coord.get("name")
            if name:
                rooms.append(name)
        return household_id, rooms
    except urllib.error.URLError:
        return None, []
    except Exception:
        return None, []


def check_api(api_base):
    section("node-sonos-http-api connectivity")
    print(f"  Trying {api_base}/zones …")
    household_id, rooms = discover_api(api_base)
    if rooms:
        ok(f"Connected — {len(rooms)} room(s) found: {', '.join(rooms)}")
        if household_id:
            ok(f"Household ID auto-discovered: {household_id}")
    else:
        warn("Could not reach node-sonos-http-api.")
        print("    Make sure it is running:  node-sonos-http-api")
        print("    Or install it:            npm install -g node-sonos-http-api")
    return household_id, rooms


# ---------------------------------------------------------------------------
# Step 4 — Detect node-sonos-http-api server.js path (for systemd unit)
# ---------------------------------------------------------------------------

_COMMON_NODE_PATHS = [
    "/usr/lib/node_modules/node-sonos-http-api/server.js",
    "/usr/local/lib/node_modules/node-sonos-http-api/server.js",
    os.path.expanduser("~/.config/yarn/global/node_modules/node-sonos-http-api/server.js"),
    os.path.expanduser("~/.npm-global/lib/node_modules/node-sonos-http-api/server.js"),
]


def find_node_api_path():
    """Try to locate the node-sonos-http-api server.js automatically."""
    # Ask node itself first
    try:
        result = subprocess.run(
            ["node", "-e", "console.log(require.resolve('node-sonos-http-api/server.js'))"],
            capture_output=True, text=True, timeout=5,
        )
        p = result.stdout.strip()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass

    for p in _COMMON_NODE_PATHS:
        if os.path.isfile(p):
            return p

    return ""


# ---------------------------------------------------------------------------
# Step 5 — Interactive config prompts
# ---------------------------------------------------------------------------

def configure(existing, discovered_household, api_base_default):
    section("Configuration")
    print("  Press Enter to keep the current value shown in [brackets].\n")

    cfg = {}

    # UUID — keep existing silently (CR200 memorises it); generate if absent
    existing_uuid = existing.get("uuid", "")
    if existing_uuid and existing_uuid != "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d":
        cfg["uuid"] = existing_uuid
        ok(f"UUID kept: {existing_uuid}")
    else:
        cfg["uuid"] = str(uuid.uuid4())
        ok(f"UUID generated: {cfg['uuid']}")
        print("    (The CR200 memorises this — avoid changing it after pairing.)")

    # Household ID
    hid_default = (
        discovered_household
        or existing.get("household_id", "")
        or "Sonos_REPLACE_WITH_YOUR_HOUSEHOLD_ID"
    )
    hid_hint = (
        "Auto-discovered from your speakers."
        if discovered_household
        else "Not auto-discovered. Find it by running:  curl http://localhost:5005/zones | python3 -m json.tool"
    )
    cfg["household_id"] = prompt("Household ID", hid_default, hint=hid_hint)

    # Friendly name
    cfg["friendly_name"] = prompt(
        "Friendly name (shown on CR200 screen)",
        existing.get("friendly_name", DEFAULTS["friendly_name"]),
    )

    # HTTP port
    cfg["http_port"] = int(prompt(
        "UPnP HTTP port",
        existing.get("http_port", DEFAULTS["http_port"]),
        hint="1400 is the standard Sonos port. Ports <1024 need elevated privileges.",
    ))

    # API base URL
    cfg["sonos_http_api_base"] = prompt(
        "node-sonos-http-api base URL",
        existing.get("sonos_http_api_base", DEFAULTS["sonos_http_api_base"]),
    )

    # Log level
    cfg["log_level"] = prompt_choice(
        "Log level",
        ["DEBUG", "INFO", "WARNING", "ERROR"],
        existing.get("log_level", DEFAULTS["log_level"]),
    )

    # Status port
    cfg["status_port"] = int(prompt(
        "Status web UI port",
        existing.get("status_port", DEFAULTS["status_port"]),
    ))

    return cfg


# ---------------------------------------------------------------------------
# Step 6 — Write config.json
# ---------------------------------------------------------------------------

def write_config(cfg):
    section("Writing config.json")
    if os.path.exists(CONFIG_JSON):
        answer = input("  config.json already exists. Overwrite? [y/N] ").strip().lower()
        if answer != "y":
            print("  Aborted — existing config.json was not modified.")
            sys.exit(0)

    with open(CONFIG_JSON, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    ok(f"Written: {CONFIG_JSON}")


# ---------------------------------------------------------------------------
# Step 7 — Create logs/ directory
# ---------------------------------------------------------------------------

def ensure_logs_dir():
    logs = os.path.join(HERE, "logs")
    if not os.path.isdir(logs):
        os.makedirs(logs, exist_ok=True)
        ok(f"Created logs/ directory: {logs}")
    else:
        ok(f"logs/ directory already exists: {logs}")


# ---------------------------------------------------------------------------
# Step 8 — Optional systemd service install
# ---------------------------------------------------------------------------

def offer_service_install(node_api_path):
    section("Pi boot autostart (systemd)")
    answer = input("  Install systemd services for automatic Pi boot launch? [y/N] ").strip().lower()
    if answer != "y":
        print("  Skipped. Run  sudo bash install-service.sh  any time to set this up.")
        return

    installer = os.path.join(HERE, "install-service.sh")
    if not os.path.isfile(installer):
        warn(f"install-service.sh not found at {installer}")
        return

    # Pass node_api_path as env var so install-service.sh can substitute it
    env = os.environ.copy()
    if node_api_path:
        env["NODE_API_PATH"] = node_api_path

    if os.geteuid() == 0:
        subprocess.run(["bash", installer], check=False, env=env)
    else:
        print("  Sudo is required to install systemd services.")
        result = subprocess.run(
            ["sudo", "bash", installer],
            check=False,
            env=env,
        )
        if result.returncode != 0:
            warn("Service install failed or was cancelled.")
            print(f"  You can run it manually:  sudo bash {installer}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    banner()

    check_python()
    check_node()

    # Load existing config.json if present (so we preserve UUID etc.)
    existing = {}
    if os.path.isfile(CONFIG_JSON):
        try:
            with open(CONFIG_JSON) as f:
                existing = json.load(f)
            print(f"  Existing config.json found: {CONFIG_JSON}")
        except Exception as e:
            warn(f"Could not read existing config.json: {e}")

    # Auto-discover API settings
    api_base = existing.get("sonos_http_api_base", DEFAULTS["sonos_http_api_base"])
    discovered_household, rooms = check_api(api_base)

    # Show discovered rooms (informational)
    if rooms:
        section("Available Sonos rooms")
        for room in rooms:
            print(f"    • {room}")

    # Find node-sonos-http-api path for systemd unit
    node_api_path = existing.get("node_api_path", "") or find_node_api_path()

    # Walk through config prompts
    cfg = configure(existing, discovered_household, api_base)

    # Store node API path in config.json for install-service.sh to use
    if node_api_path:
        cfg["node_api_path"] = node_api_path

    # Write output
    write_config(cfg)
    ensure_logs_dir()

    # Summary
    section("Done")
    ok("Configuration complete.")
    print()
    print("  To start the bridge:")
    print("    python3 main.py")
    print()
    print("  To verify your Sonos API connection:")
    print(f"    curl {cfg['sonos_http_api_base']}/zones")
    print()

    offer_service_install(node_api_path)

    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
