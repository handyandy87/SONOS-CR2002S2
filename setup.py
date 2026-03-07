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
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid as _uuid_mod

from discovery import discover_sonos_devices, print_discovered_devices

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_JSON = os.path.join(HERE, "config.json")

DEFAULTS = {
    "sonos_http_api_base": "http://localhost:5005",
    "s1_room_name": "",
    "s2_room_name": "",
    "poll_interval": 1.0,
    "uuid": "",
    "household_id": "",
    "friendly_name": "CR200 Bridge",
    "http_port": 1400,
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


def prompt_from_list(label, options, default=""):
    """Prompt user to pick from a numbered list, or type a name manually."""
    if options:
        print(f"    Available rooms:")
        for i, opt in enumerate(options, 1):
            print(f"      {i}. {opt}")
        print(f"    Enter a number or type a room name manually.")
    val = input(f"  {label} [{default}]: ").strip()
    if not val:
        return default
    # Check if it's a number
    try:
        idx = int(val) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except ValueError:
        pass
    return val


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
# Step 2 — Node.js + npm (with optional install)
# ---------------------------------------------------------------------------

def _run(cmd, timeout=30):
    """Run a command quietly, return CompletedProcess. Never raises on failure."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        class _Fake:
            returncode = 1
            stdout = stderr = ""
        return _Fake()


def _apt_available():
    return shutil.which("apt") is not None


def _install_nodejs_apt():
    """Try to install nodejs+npm via apt. Returns True on success."""
    print("  Running: sudo apt install -y nodejs npm")
    result = subprocess.run(["sudo", "apt", "install", "-y", "nodejs", "npm"], timeout=180)
    return result.returncode == 0


def check_node():
    """Check for node and npm; offer apt install if absent. Returns (node_path, npm_path)."""
    section("Node.js")
    node = shutil.which("node")

    if not node:
        warn("node not found in PATH.")
        if _apt_available():
            answer = input("  Install nodejs + npm via apt now? [Y/n] ").strip().lower()
            if answer != "n":
                if _install_nodejs_apt():
                    node = shutil.which("node")
                    if node:
                        ok(f"node installed: {node}")
                    else:
                        warn("node still not found after install. You may need to open a new shell.")
                        return None, None
                else:
                    warn("apt install failed.")
                    return None, None
        else:
            print("  Install Node.js from https://nodejs.org or via your package manager.")
            return None, None

    try:
        r = _run([node, "--version"])
        ok(f"node {r.stdout.strip()}  ({node})")
    except Exception as e:
        warn(f"Could not query node version: {e}")

    npm = shutil.which("npm")
    if npm:
        r = _run([npm, "--version"])
        ok(f"npm  {r.stdout.strip()}  ({npm})")
    else:
        warn("npm not found in PATH.")

    return node, npm


# ---------------------------------------------------------------------------
# Step 3 — node-sonos-http-api: detect, install, start
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


def ensure_node_api(npm):
    """Check if node-sonos-http-api is installed; offer npm install if not.
    Returns the server.js path, or "" if unavailable."""
    section("node-sonos-http-api package")

    path = find_node_api_path()
    if path:
        ok(f"Already installed: {path}")
        return path

    warn("node-sonos-http-api not found.")

    gh_url = "https://github.com/jishi/node-sonos-http-api"
    install_spec = f"{gh_url}"

    if npm is None:
        print("  npm is not available — cannot install automatically.")
        print(f"  Install manually:  sudo npm install -g {gh_url}")
        return ""

    answer = input(f"  Install now? (npm install -g {gh_url}) [Y/n] ").strip().lower()
    if answer == "n":
        print(f"  Skipped. Install later:  sudo npm install -g {gh_url}")
        return ""

    print("  Installing from GitHub … (this may take a minute)")
    result = subprocess.run([npm, "install", "-g", install_spec], timeout=300)
    if result.returncode != 0:
        print("  Retrying with sudo …")
        result = subprocess.run(
            ["sudo", npm, "install", "-g", install_spec], timeout=300
        )

    if result.returncode != 0:
        warn(f"npm install failed. Try manually:  sudo npm install -g {gh_url}")
        return ""

    path = find_node_api_path()
    if path:
        ok(f"Installed: {path}")
    else:
        warn("Installed, but path not auto-detected. You may need to set it manually.")
    return path


def start_api_for_discovery(node_api_path):
    """Start node-sonos-http-api in the background for discovery. Returns Popen or None."""
    node = shutil.which("node")
    if not node or not node_api_path:
        return None
    try:
        proc = subprocess.Popen(
            [node, node_api_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except Exception as e:
        warn(f"Could not start node-sonos-http-api: {e}")
        return None


def check_api(api_base, node_api_path=""):
    """Probe the API; if unreachable and we have the path, offer to start it."""
    section("node-sonos-http-api connectivity")
    print(f"  Trying {api_base}/zones …")
    household_id, rooms = discover_api(api_base)

    if rooms:
        ok(f"Connected — {len(rooms)} room(s) found: {', '.join(rooms)}")
        if household_id:
            ok(f"Household ID auto-discovered: {household_id}")
        return household_id, rooms, None   # (household_id, rooms, background_proc)

    warn("Could not reach node-sonos-http-api.")

    if not node_api_path:
        print("  Start it with:  node /usr/local/lib/node_modules/sonos-http-api/server.js")
        return None, [], None

    answer = input("  Start it now for room discovery? [Y/n] ").strip().lower()
    if answer == "n":
        return None, [], None

    proc = start_api_for_discovery(node_api_path)
    if proc is None:
        return None, [], None

    print("  Waiting for API to start …", end="", flush=True)
    household_id = None
    rooms = []
    for _ in range(8):
        time.sleep(1)
        print(".", end="", flush=True)
        household_id, rooms = discover_api(api_base)
        if rooms:
            break
    print()

    if rooms:
        ok(f"Connected — {len(rooms)} room(s) found: {', '.join(rooms)}")
        if household_id:
            ok(f"Household ID auto-discovered: {household_id}")
        print("  (node-sonos-http-api is running in the background — leave it running.)")
    else:
        warn("API started but could not discover rooms. Check that your Sonos system is on the same network.")
        proc.terminate()
        proc = None

    return household_id, rooms, proc


# ---------------------------------------------------------------------------
# Step 4 — Detect node-sonos-http-api server.js path (for systemd unit)
# ---------------------------------------------------------------------------

_COMMON_NODE_PATHS = [
    "/usr/local/lib/node_modules/sonos-http-api/server.js",
    "/usr/lib/node_modules/sonos-http-api/server.js",
    os.path.expanduser("~/.config/yarn/global/node_modules/sonos-http-api/server.js"),
    os.path.expanduser("~/.npm-global/lib/node_modules/sonos-http-api/server.js"),
    "/usr/local/lib/node_modules/node-sonos-http-api/server.js",
    "/usr/lib/node_modules/node-sonos-http-api/server.js",
    os.path.expanduser("~/.config/yarn/global/node_modules/node-sonos-http-api/server.js"),
    os.path.expanduser("~/.npm-global/lib/node_modules/node-sonos-http-api/server.js"),
]


def find_node_api_path():
    """Try to locate the sonos-http-api server.js automatically."""
    for module_name in ("sonos-http-api/server.js", "node-sonos-http-api/server.js"):
        try:
            result = subprocess.run(
                ["node", "-e", f"console.log(require.resolve('{module_name}'))"],
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

def configure(existing, rooms, discovered_household):
    section("Configuration")
    print("  Press Enter to keep the current value shown in [brackets].\n")

    cfg = {}

    # API base URL
    cfg["sonos_http_api_base"] = prompt(
        "node-sonos-http-api base URL",
        existing.get("sonos_http_api_base", DEFAULTS["sonos_http_api_base"]),
    )

    # S1 room name
    print()
    print("  The S1 device is the physical Sonos unit the CR200 connects to over SonosNet.")
    print("  Supported: Sonos Bridge, Connect, Connect:Amp,")
    print("             Play:1 Gen 1, Play:3 Gen 1, Play:5 Gen 1")
    cfg["s1_room_name"] = prompt_from_list(
        "S1 device room name (as shown in node-sonos-http-api)",
        rooms,
        existing.get("s1_room_name", DEFAULTS["s1_room_name"]),
    )

    # S2 room name
    print()
    print("  The S2 room is the speaker(s) the CR200 will browse and control.")
    print("  ContentDirectory Browse/Search will be proxied from this speaker.")
    cfg["s2_room_name"] = prompt_from_list(
        "S2 target room name",
        rooms,
        existing.get("s2_room_name", DEFAULTS["s2_room_name"]),
    )

    # Poll interval
    cfg["poll_interval"] = float(prompt(
        "Poll interval (seconds)",
        existing.get("poll_interval", DEFAULTS["poll_interval"]),
        hint="How often to check the S1 device for state changes. 1.0 is recommended.",
    ))

    # UUID — keep existing (CR200 memorises it); generate if absent
    existing_uuid = existing.get("uuid", "")
    if existing_uuid and existing_uuid not in ("", "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"):
        cfg["uuid"] = existing_uuid
        ok(f"UUID kept: {existing_uuid}")
    else:
        cfg["uuid"] = str(_uuid_mod.uuid4())
        ok(f"UUID generated: {cfg['uuid']}")
        print("    (The CR200 memorises this — avoid changing it after pairing.)")

    # Household ID
    hid_default = (
        discovered_household
        or existing.get("household_id", "")
        or "Sonos_REPLACE_WITH_YOUR_HOUSEHOLD_ID"
    )
    hid_hint = (
        "Auto-discovered from your S2 speakers."
        if discovered_household
        else "Not auto-discovered. Find it with:  curl http://localhost:5005/zones | python3 -m json.tool"
    )
    cfg["household_id"] = prompt("Household ID", hid_default, hint=hid_hint)

    # Friendly name
    cfg["friendly_name"] = prompt(
        "Friendly name (shown on CR200 screen)",
        existing.get("friendly_name", DEFAULTS["friendly_name"]),
    )

    # UPnP HTTP port
    cfg["http_port"] = int(prompt(
        "UPnP HTTP port",
        existing.get("http_port", DEFAULTS["http_port"]),
        hint="1400 is the standard Sonos port. Requires sudo on Linux for ports < 1024.",
    ))

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
    node, npm = check_node()

    # Load existing config.json if present
    existing = {}
    if os.path.isfile(CONFIG_JSON):
        try:
            with open(CONFIG_JSON) as f:
                existing = json.load(f)
            print(f"  Existing config.json found: {CONFIG_JSON}")
        except Exception as e:
            warn(f"Could not read existing config.json: {e}")

    # Ensure node-sonos-http-api is installed
    node_api_path = existing.get("node_api_path", "") or find_node_api_path()
    if not node_api_path:
        node_api_path = ensure_node_api(npm)

    # Probe the API; start it temporarily if installed but not running
    api_base = existing.get("sonos_http_api_base", DEFAULTS["sonos_http_api_base"])
    discovered_household, rooms, _bg_proc = check_api(api_base, node_api_path)

    # SSDP scan — find Sonos devices and flag S1 units
    section("Scanning for Sonos devices (SSDP)")
    print("  Scanning network for Sonos ZonePlayer devices …")
    ssdp_devices = discover_sonos_devices(timeout=3.0)
    print_discovered_devices(ssdp_devices)

    if rooms:
        section("Discovered rooms (node-sonos-http-api)")
        for room in rooms:
            print(f"    • {room}")
        print()
        print("  Identify which room is your S1 device and which is your S2 speaker.")
        print("  (S1 devices: Bridge, Connect, Connect:Amp, Play:1/3/5 Gen 1)")

    # Walk through config prompts
    cfg = configure(existing, rooms, discovered_household)

    # Persist node_api_path so install-service.sh can use it
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
