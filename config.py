"""
Bridge Configuration
Defaults are defined below. To override, run setup.py — it writes
config.json next to this file, which is loaded at import time.
"""

import json as _json
import os as _os

BRIDGE_CONFIG = {
    # node-sonos-http-api base URL
    # Install: npm install -g https://github.com/jishi/node-sonos-http-api
    # Run:     node /usr/local/lib/node_modules/sonos-http-api/server.js
    "sonos_http_api_base": "http://localhost:5005",

    # Room name of the S1 device as it appears in node-sonos-http-api /zones.
    # The physical S1 device the CR200 connects to over SonosNet.
    # Supported: Sonos Bridge, Connect, Connect:Amp, Play:1/3/5 Gen 1, PLAYBAR.
    # The S1 monitor watches this device for CR200-driven state changes.
    "s1_room_name": "",

    # Room name of the S2 speaker(s) to control.
    # Must match a room name returned by node-sonos-http-api /zones.
    "s2_room_name": "",

    # How often (in seconds) to poll the S1 device for state changes.
    "poll_interval": 1.0,

    # -------------------------------------------------------------------------
    # UPnP / SSDP — bridge presents itself as a ZonePlayer to the CR200.
    # The CR200 discovers the bridge alongside the S1 device and uses it for
    # ContentDirectory browsing (Sonos Favorites, Playlists, music services,
    # search) — all content is proxied from the configured S2 speaker.
    # -------------------------------------------------------------------------

    # Stable UUID for the bridge device. The CR200 memorises this UUID after
    # pairing — do not change it once set, or the CR200 must be re-paired.
    # Generated automatically by setup.py if absent.
    "uuid": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",

    # Sonos Household ID — must match your S2 system's household so the CR200
    # treats the bridge and S2 speakers as part of the same household.
    # Auto-discovered from node-sonos-http-api by setup.py.
    "household_id": "",

    # Friendly name shown on the CR200 display.
    "friendly_name": "CR200 Bridge",

    # Port for the UPnP HTTP server (device description + SOAP endpoint).
    # 1400 is the standard Sonos port; requires sudo on Linux for ports < 1024.
    "http_port": 1400,

    # Logging level: DEBUG, INFO, WARNING, ERROR
    "log_level": "INFO",

    # Status web UI port
    "status_port": 8080,
}

# Load runtime overrides from config.json (written by setup.py).
# If the file is absent or unreadable, the hardcoded defaults above remain active.
_CONFIG_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "config.json")
if _os.path.isfile(_CONFIG_FILE):
    try:
        with open(_CONFIG_FILE) as _f:
            BRIDGE_CONFIG.update(_json.load(_f))
    except (_json.JSONDecodeError, OSError) as _e:
        import sys as _sys
        print(f"[config] Warning: could not load config.json: {_e}", file=_sys.stderr)
