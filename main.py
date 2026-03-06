#!/usr/bin/env python3
"""
CR200 Bridge — Main Entry Point (node-sonos-http-api backend)

Boot order:
  1. SonosClient   — connects to node-sonos-http-api, discovers rooms
  2. SSDPServer    — broadcasts fake S1 device presence on LAN
  3. UPnPServer    — handles CR200 HTTP/SOAP commands
  4. StatusServer  — web UI at http://localhost:8080

Requirements:
  node-sonos-http-api running on localhost:5005 (see config.py)
  pip install  (no extra Python deps — stdlib only + node-sonos-http-api)

Usage:
  # Terminal 1
  node-sonos-http-api

  # Terminal 2
  cd bridge && python3 main.py
"""

import logging
import signal
import socket
import sys
import time

from config import BRIDGE_CONFIG
from sonos_client import SonosClient
from ssdp_server import SSDPServer
from upnp_server import UPnPServer
from soap_handler import SOAPHandler
from status_server import StatusServer

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
    api_base = BRIDGE_CONFIG["sonos_http_api_base"]

    logger.info("=" * 60)
    logger.info("  CR200 Bridge (node-sonos-http-api backend)")
    logger.info(f"  Local IP       : {local_ip}")
    logger.info(f"  UPnP port      : {BRIDGE_CONFIG['http_port']}")
    logger.info(f"  Sonos HTTP API : {api_base}")
    logger.info(f"  Status UI      : http://{local_ip}:{BRIDGE_CONFIG['status_port']}")
    logger.info("=" * 60)

    sonos_client = SonosClient()
    sonos_client.start()

    logger.info("Waiting for node-sonos-http-api room discovery...")
    time.sleep(4)

    soap_handler  = SOAPHandler(sonos_client)
    ssdp_server   = SSDPServer(local_ip)
    upnp_server   = UPnPServer(local_ip, soap_handler)
    status_server = StatusServer(sonos_client)

    ssdp_server.start()
    upnp_server.start()
    status_server.start()

    rooms = sonos_client.get_room_list()
    if rooms:
        logger.info(f"Ready — {len(rooms)} room(s) available:")
        for r in rooms:
            active_marker = "→" if r["active"] else " "
            logger.info(f"  {active_marker} {r['name']} ({r['state']}, vol {r['volume']})")
    else:
        logger.warning(
            "No rooms found. Is node-sonos-http-api running? "
            f"Try: curl {api_base}/zones"
        )

    logger.info("Bridge running. Press Ctrl+C to stop.")

    def shutdown(sig, frame):
        logger.info("Shutting down...")
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
