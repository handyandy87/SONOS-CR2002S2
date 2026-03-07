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
    # This is the physical S1 device the CR200 pairs with
    # (e.g. "Sonos Bridge", "Office Connect", "Living Room Play:1").
    # The CR200 controls this device; the bridge watches it and mirrors commands to S2.
    "s1_room_name": "",

    # Room name of the S2 speaker(s) to control.
    # Must match a room name returned by node-sonos-http-api /zones.
    "s2_room_name": "",

    # How often (in seconds) to poll the S1 device for state changes.
    # Lower = more responsive; 1.0 is a good default.
    "poll_interval": 1.0,

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
