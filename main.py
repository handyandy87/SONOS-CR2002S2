#!/usr/bin/env python3
"""
CR200 Bridge — Main Entry Point (S1 device monitor backend)

Boot order:
  1. SonosClient  — connects to node-sonos-http-api, discovers all rooms
                    (both the S1 device and the S2 speakers)
  2. S1Monitor    — polls the S1 device room for state changes driven by the
                    CR200 and mirrors them to the target S2 room
  3. StatusServer — web UI at http://localhost:8080

Hardware flow:
  CR200 (SonosNet) → real S1 device (Sonos Bridge / Connect / Play:1 etc.)
                          ↕ node-sonos-http-api polling
                   [this bridge — Pi / Mac / Linux]
                          ↓ play / pause / volume / next / prev
                      S2 speakers

Requirements:
  - A real S1 Sonos device on the same network as your S2 system.
    The CR200 pairs with this device naturally over SonosNet.
    Supported S1 devices: Sonos Bridge, Connect, Connect:Amp,
    Play:1 Gen 1, Play:3 Gen 1, Play:5 Gen 1.
  - node-sonos-http-api running (discovers both S1 and S2 devices).
  - config.json with s1_room_name and s2_room_name set (run setup.py).

Usage:
  # Terminal 1 — start the Sonos HTTP API
  node /usr/local/lib/node_modules/sonos-http-api/server.js

  # Terminal 2
  cd SONOS-CR2002S2 && python3 main.py
"""

import logging
import os
import signal
import sys
import time

from config import BRIDGE_CONFIG

# Ensure logs/ exists before any FileHandler is created
os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)
from sonos_client import SonosClient
from s1_monitor import S1Monitor
from status_server import StatusServer
from discovery import discover_sonos_devices

logging.basicConfig(
    level=getattr(logging, BRIDGE_CONFIG["log_level"], logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bridge.log"),
    ]
)
logger = logging.getLogger(__name__)


def main():
    s1_room = BRIDGE_CONFIG.get("s1_room_name", "")
    s2_room = BRIDGE_CONFIG.get("s2_room_name", "")
    api_base = BRIDGE_CONFIG["sonos_http_api_base"]

    logger.info("=" * 60)
    logger.info("  CR200 Bridge (S1 device monitor)")
    logger.info(f"  S1 device room : {s1_room or '(not set — run setup.py)'}")
    logger.info(f"  S2 target room : {s2_room or '(not set — run setup.py)'}")
    logger.info(f"  Sonos HTTP API : {api_base}")
    logger.info(f"  Status UI      : http://localhost:{BRIDGE_CONFIG['status_port']}")
    logger.info("=" * 60)

    if not s1_room or not s2_room:
        logger.error(
            "s1_room_name and s2_room_name must both be set in config.json. "
            "Run  python3 setup.py  to configure."
        )
        # Run a quick SSDP scan to help the user identify their S1 device
        logger.info("Scanning for Sonos devices on the network …")
        devices = discover_sonos_devices(timeout=3.0)
        s1_hits = [d for d in devices if d["likely_s1"]]
        if s1_hits:
            logger.info("Detected S1 device(s):")
            for d in s1_hits:
                logger.info(f"  {d['ip']:16s}  {d['model_name']}  \"{d['friendly_name']}\"")
        else:
            logger.info(
                "No S1 devices found via SSDP. "
                "Ensure the S1 device is powered on and on the same network."
            )
        sys.exit(1)

    sonos_client = SonosClient()
    sonos_client.start()

    logger.info("Waiting for node-sonos-http-api room discovery...")
    time.sleep(4)

    rooms = sonos_client.get_room_list()
    if rooms:
        logger.info(f"Found {len(rooms)} room(s):")
        for r in rooms:
            tag = ""
            if r["name"] == s1_room:
                tag = "  ← S1 device (CR200 target)"
            elif r["name"] == s2_room:
                tag = "  ← S2 speaker (playback target)"
            logger.info(f"    {r['name']} ({r['state']}, vol {r['volume']}){tag}")
    else:
        logger.warning(
            "No rooms found. Is node-sonos-http-api running? "
            f"Try: curl {api_base}/zones"
        )

    # Warn if the configured rooms weren't discovered
    room_names = {r["name"] for r in rooms}
    if s1_room not in room_names:
        logger.warning(
            f"S1 room '{s1_room}' not found in discovered rooms. "
            "Check that the S1 device is powered on and on the same network."
        )
    if s2_room not in room_names:
        logger.warning(
            f"S2 room '{s2_room}' not found in discovered rooms. "
            "Check that the S2 speaker is powered on and reachable."
        )

    s1_monitor = S1Monitor(sonos_client, s1_room, s2_room)
    status_server = StatusServer(sonos_client)

    s1_monitor.start()
    status_server.start()

    logger.info("Bridge running. CR200 commands on the S1 device will be mirrored to S2.")
    logger.info("Press Ctrl+C to stop.")

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        s1_monitor.stop()
        status_server.stop()
        sonos_client.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
