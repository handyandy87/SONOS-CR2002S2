"""
Bridge Configuration
Defaults are defined below. To override, run setup.py — it writes
config.json next to this file, which is loaded at import time.
"""

import json as _json
import os as _os

BRIDGE_CONFIG = {
    # A stable UUID for the fake Sonos device we're advertising.
    # Generate once and keep consistent — the CR200 remembers it.
    # You can regenerate with: python3 -c "import uuid; print(uuid.uuid4())"
    "uuid": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",

    # Sonos household ID — the CR200 uses this to group devices.
    # Should look like "Sonos_xxxxxxxxxxxx". You can use any consistent string,
    # or sniff the real one from your S2 speakers via:
    #   python3 -c "import soco; s = list(soco.discover())[0]; print(s.household_id)"
    "household_id": "Sonos_REPLACE_WITH_YOUR_HOUSEHOLD_ID",

    # Friendly name shown on the CR200 screen for this "player"
    "friendly_name": "CR200 Bridge",

    # Port for the UPnP HTTP server (1400 is standard Sonos, use it if available)
    "http_port": 1400,

    # node-sonos-http-api base URL
    # Install: npm install -g node-sonos-http-api
    # Run:     node-sonos-http-api  (default port 5005)
    "sonos_http_api_base": "http://localhost:5005",

    # Logging level: DEBUG, INFO, WARNING, ERROR
    "log_level": "INFO",

    # Status web UI port (separate from UPnP port)
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
