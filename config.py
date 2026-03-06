"""
Bridge Configuration
Edit these values before running the bridge.
"""

import uuid as _uuid

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

    # Logging level: DEBUG, INFO, WARNING, ERROR
    "log_level": "INFO",

    # Status web UI port (separate from UPnP port)
    "status_port": 8080,
}
