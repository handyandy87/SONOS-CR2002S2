#!/usr/bin/env python3
"""
CR200 Bridge — Main Entry Point

Boot order:
  1. SonosClient  — connects to node-sonos-http-api, discovers all rooms
                    (S1 device + S2 speakers)
  2. S1Monitor    — polls the S1 device for CR200-driven state changes and
                    mirrors them to the S2 room (play/pause/vol/next/prev)
  3. SSDPServer   — announces the bridge as a ZonePlayer on the network so
                    the CR200 can discover it for ContentDirectory browsing
  4. UPnPServer   — serves the device description and handles CR200 SOAP:
                      AVTransport / RenderingControl → forwarded to S2
                      ContentDirectory Browse/Search → proxied to S2 speaker
                      ZoneGroupTopology → reflects real S2 zone structure
  5. StatusServer — web UI at http://localhost:8080

Hardware flow:
  CR200 (SonosNet via S1 device) ──────────────────────────────┐
      │  SSDP discovery + SOAP (port 1400)                      │ SonosNet WiFi
      ▼                                                          │
  Bridge (Pi / Mac / Linux)               S1 device (Bridge /   │
      │  ContentDirectory → S2 speaker     Connect / Play:1 etc.)
      │  AVTransport → S2 via node-sonos-http-api
      ▼
  S2 speakers (Era 100/300, Arc, Beam Gen 2, Five, Move 2, etc.)

Requirements:
  - A real S1 device (see README for supported models) on the same network.
    The CR200 connects to it over SonosNet; the bridge uses it as the
    SonosNet beacon without intercepting the CR200's WiFi layer.
  - node-sonos-http-api running (discovers S1 + S2 devices).
  - config.json set up (run setup.py).
  - sudo required on Linux (port 1400 < 1024).

Usage:
  # Terminal 1 — start the Sonos HTTP API
  node /usr/local/lib/node_modules/sonos-http-api/server.js

  # Terminal 2
  cd SONOS-CR2002S2 && sudo python3 main.py
"""

import logging
import os
import signal
import socket
import sys
import time

from config import BRIDGE_CONFIG

# Ensure logs/ exists before any FileHandler is created
os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)
from sonos_client import SonosClient
from s1_monitor import S1Monitor
from soap_handler import SOAPHandler
from ssdp_server import SSDPServer
from upnp_server import UPnPServer
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


def _local_ip() -> str:
    """Best-effort local IP address detection."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"


def main():
    s1_room  = BRIDGE_CONFIG.get("s1_room_name", "")
    s2_room  = BRIDGE_CONFIG.get("s2_room_name", "")
    api_base = BRIDGE_CONFIG["sonos_http_api_base"]
    local_ip = _local_ip()

    logger.info("=" * 60)
    logger.info("  CR200 Bridge")
    logger.info(f"  S1 device room : {s1_room or '(not set — run setup.py)'}")
    logger.info(f"  S2 target room : {s2_room or '(not set — run setup.py)'}")
    logger.info(f"  Friendly name  : {BRIDGE_CONFIG['friendly_name']}")
    logger.info(f"  Bridge IP      : {local_ip}")
    logger.info(f"  UPnP port      : {BRIDGE_CONFIG['http_port']}")
    logger.info(f"  Sonos HTTP API : {api_base}")
    logger.info(f"  Status UI      : http://localhost:{BRIDGE_CONFIG['status_port']}")
    logger.info("=" * 60)

    if not s1_room or not s2_room:
        logger.error(
            "s1_room_name and s2_room_name must both be set in config.json. "
            "Run  python3 setup.py  to configure."
        )
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

    # -------------------------------------------------------------------------
    # 1. SonosClient — discover rooms
    # -------------------------------------------------------------------------
    sonos_client = SonosClient()
    sonos_client.start()

    logger.info("Waiting for node-sonos-http-api room discovery...")
    time.sleep(4)

    # Auto-discover household_id if not configured
    if not BRIDGE_CONFIG.get("household_id"):
        hid = sonos_client.get_household_id()
        if hid:
            BRIDGE_CONFIG["household_id"] = hid
            logger.info(f"Household ID auto-discovered: {hid}")
        else:
            logger.warning(
                "Could not auto-discover household_id. "
                "Set it manually in config.json (run setup.py)."
            )

    rooms = sonos_client.get_room_list()
    if rooms:
        logger.info(f"Found {len(rooms)} room(s):")
        for r in rooms:
            tag = ""
            if r["name"] == s1_room:
                tag = "  ← S1 device (SonosNet beacon)"
            elif r["name"] == s2_room:
                tag = "  ← S2 speaker (content + playback target)"
            logger.info(f"    {r['name']} ({r['state']}, vol {r['volume']}){tag}")
    else:
        logger.warning(
            "No rooms found. Is node-sonos-http-api running? "
            f"Try: curl {api_base}/zones"
        )

    room_names = {r["name"] for r in rooms}
    if s1_room not in room_names:
        logger.warning(
            f"S1 room '{s1_room}' not found. "
            "Check the S1 device is on and reachable."
        )
    if s2_room not in room_names:
        logger.warning(
            f"S2 room '{s2_room}' not found. "
            "Check the S2 speaker is on and reachable."
        )

    # Set the S2 room as the active room so ContentDirectory proxies to it
    sonos_client.set_active_room(s2_room)

    # -------------------------------------------------------------------------
    # 2. S1Monitor — mirrors CR200→S1 state changes to S2
    # -------------------------------------------------------------------------
    s1_monitor = S1Monitor(sonos_client, s1_room, s2_room)

    # -------------------------------------------------------------------------
    # 3 & 4. SSDP + UPnP — makes bridge discoverable; serves S2 content to CR200
    # -------------------------------------------------------------------------
    soap_handler  = SOAPHandler(sonos_client)
    ssdp_server   = SSDPServer(local_ip)
    upnp_server   = UPnPServer(local_ip, soap_handler)

    # -------------------------------------------------------------------------
    # 5. Status web UI
    # -------------------------------------------------------------------------
    status_server = StatusServer(sonos_client)

    # Start everything
    s1_monitor.start()
    ssdp_server.start()
    upnp_server.start()
    status_server.start()

    logger.info(
        "Bridge running.\n"
        f"  CR200 ContentDirectory (music services) → S2 '{s2_room}' speaker\n"
        f"  CR200 commands on S1 '{s1_room}' → mirrored to S2 '{s2_room}'"
    )
    logger.info("Press Ctrl+C to stop.")

    def shutdown(sig, frame):
        logger.info("Shutting down...")
        s1_monitor.stop()
        ssdp_server.stop()
        upnp_server.stop()
        status_server.stop()
        sonos_client.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
