#!/usr/bin/env python3
"""
CR200 Bridge — Main Entry Point

Wires together:
  - ZoneManager    (discovers S2 speakers via SoCo)
  - SSDPServer     (broadcasts fake S1 device presence)
  - UPnPServer     (handles CR200 HTTP/SOAP commands)
  - StatusServer   (web UI at http://localhost:8080)

Usage:
  python3 main.py

Requirements:
  pip install soco

Before running:
  1. Edit bridge/config.py — set your household_id
  2. Ensure this machine is on the same subnet as your Sonos speakers
  3. Port 1400 must be free (or change http_port in config.py)
  4. Port 1900 (UDP) must be accessible for SSDP
"""

import logging
import signal
import socket
import sys
import time

from config import BRIDGE_CONFIG
from zone_manager import ZoneManager
from ssdp_server import SSDPServer
from upnp_server import UPnPServer
from soap_handler import SOAPHandler
from status_server import StatusServer

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, BRIDGE_CONFIG["log_level"], logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bridge.log"),
    ]
)
logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    """Get the local IP address of this machine on the LAN."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def main():
    local_ip = get_local_ip()
    logger.info("=" * 60)
    logger.info("  CR200 Bridge starting up")
    logger.info(f"  Local IP  : {local_ip}")
    logger.info(f"  UPnP port : {BRIDGE_CONFIG['http_port']}")
    logger.info(f"  Status UI : http://{local_ip}:{BRIDGE_CONFIG['status_port']}")
    logger.info(f"  Device UUID: {BRIDGE_CONFIG['uuid']}")
    logger.info("=" * 60)

    # ── Boot sequence ──────────────────────────────────────────────────────────
    zone_manager = ZoneManager()
    zone_manager.start()

    soap_handler = SOAPHandler(zone_manager)
    ssdp_server = SSDPServer(local_ip)
    upnp_server = UPnPServer(local_ip, soap_handler)
    status_server = StatusServer(zone_manager)

    # Give discovery a moment before we start advertising
    logger.info("Waiting for initial speaker discovery...")
    time.sleep(5)

    ssdp_server.start()
    upnp_server.start()
    status_server.start()

    speakers = zone_manager.get_speaker_list()
    if speakers:
        logger.info(f"Ready! Controlling {len(speakers)} speaker(s).")
        for s in speakers:
            logger.info(f"  {'→' if s['active'] else ' '} {s['name']} ({s['ip']})")
    else:
        logger.warning("No speakers found yet — is SoCo installed and are speakers on the network?")

    logger.info("CR200 Bridge is running. Press Ctrl+C to stop.")

    # ── Graceful shutdown ──────────────────────────────────────────────────────
    def shutdown(sig, frame):
        logger.info("Shutting down...")
        ssdp_server.stop()
        upnp_server.stop()
        status_server.stop()
        zone_manager.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep main thread alive
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
