"""
SSDP Server

Announces the bridge as a Sonos ZonePlayer on the network so the CR200 can
discover it alongside the real S1 device.  The CR200 uses the bridge for:
  - ContentDirectory Browse/Search — proxied to the S2 speaker (port 1400),
    giving the CR200 access to S2 music services (Spotify, Apple Music, etc.)
  - AVTransport + RenderingControl SOAP — forwarded to S2 via node-sonos-http-api

The real S1 device (Bridge, Connect, Play:1 Gen 1, etc.) remains on the
network to provide the SonosNet WiFi beacon that the CR200 connects to.
"""

import socket
import struct
import threading
import logging
import time
from config import BRIDGE_CONFIG

logger = logging.getLogger(__name__)

SSDP_MULTICAST_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_TTL = 4

# UPnP device types the CR200 searches for
SONOS_DEVICE_TYPES = [
    "urn:schemas-upnp-org:device:ZonePlayer:1",
    "upnp:rootdevice",
    "uuid:" + BRIDGE_CONFIG["uuid"],
]

SSDP_RESPONSE_TEMPLATE = """\
HTTP/1.1 200 OK\r
CACHE-CONTROL: max-age=1800\r
DATE: {date}\r
EXT:\r
LOCATION: http://{ip}:{port}/xml/device_description.xml\r
SERVER: Linux UPnP/1.0 Sonos/29.3-87071 (ZPS3)\r
ST: {st}\r
USN: uuid:{uuid}::{st}\r
X-RINCON-BOOTSEQ: 1\r
X-RINCON-HOUSEHOLD: {household}\r
\r
"""

SSDP_NOTIFY_TEMPLATE = """\
NOTIFY * HTTP/1.1\r
HOST: 239.255.255.250:1900\r
CACHE-CONTROL: max-age=1800\r
LOCATION: http://{ip}:{port}/xml/device_description.xml\r
NT: {nt}\r
NTS: ssdp:alive\r
SERVER: Linux UPnP/1.0 Sonos/29.3-87071 (ZPS3)\r
USN: uuid:{uuid}::{nt}\r
X-RINCON-BOOTSEQ: 1\r
X-RINCON-HOUSEHOLD: {household}\r
\r
"""


class SSDPServer:
    def __init__(self, local_ip: str):
        self.local_ip = local_ip
        self.running = False
        self._threads = []

    def _make_response(self, st: str) -> str:
        from email.utils import formatdate
        return SSDP_RESPONSE_TEMPLATE.format(
            date=formatdate(usegmt=True),
            ip=self.local_ip,
            port=BRIDGE_CONFIG["http_port"],
            st=st,
            uuid=BRIDGE_CONFIG["uuid"],
            household=BRIDGE_CONFIG["household_id"],
        )

    def _make_notify(self, nt: str) -> str:
        return SSDP_NOTIFY_TEMPLATE.format(
            ip=self.local_ip,
            port=BRIDGE_CONFIG["http_port"],
            nt=nt,
            uuid=BRIDGE_CONFIG["uuid"],
            household=BRIDGE_CONFIG["household_id"],
        )

    def _listen_for_msearch(self):
        """Listen for M-SEARCH packets from the CR200 and respond."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", SSDP_PORT))

        # Join multicast group
        mreq = struct.pack("4sL", socket.inet_aton(SSDP_MULTICAST_ADDR), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)

        logger.info(f"SSDP listener started on {SSDP_MULTICAST_ADDR}:{SSDP_PORT}")

        while self.running:
            try:
                data, addr = sock.recvfrom(4096)
                message = data.decode("utf-8", errors="ignore")

                if "M-SEARCH" in message:
                    logger.debug(f"M-SEARCH from {addr[0]}: {message.strip()}")
                    self._handle_msearch(message, addr, sock)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"SSDP listener error: {e}")

        sock.close()

    def _handle_msearch(self, message: str, addr: tuple, sock: socket.socket):
        """Parse M-SEARCH and send matching responses."""
        st = None
        for line in message.splitlines():
            if line.upper().startswith("ST:"):
                st = line.split(":", 1)[1].strip()
                break

        if st is None:
            return

        # Respond to searches for our device types, or ssdp:all
        respond_to = []
        if st == "ssdp:all":
            respond_to = SONOS_DEVICE_TYPES
        elif st in SONOS_DEVICE_TYPES:
            respond_to = [st]

        # Small delay to avoid responding too fast (UPnP spec)
        time.sleep(0.1)

        for device_st in respond_to:
            response = self._make_response(device_st)
            try:
                sock.sendto(response.encode(), addr)
                logger.debug(f"Sent SSDP response for {device_st} to {addr[0]}")
            except Exception as e:
                logger.error(f"Failed to send SSDP response to {addr[0]}: {e}")
                # Note: if addr[0] is a 169.254.x.x link-local address the send
                # will always fail when the bridge is on a different network segment
                # (e.g. Mac on Wi-Fi vs CR200 on SonosNet). Run the bridge on a
                # Raspberry Pi wired to the same switch as the Sonos speaker.

    def _send_notify_loop(self):
        """Periodically broadcast NOTIFY alive packets so CR200 keeps us alive."""
        notify_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        notify_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, SSDP_TTL)

        while self.running:
            for nt in SONOS_DEVICE_TYPES:
                notify = self._make_notify(nt)
                try:
                    notify_sock.sendto(
                        notify.encode(),
                        (SSDP_MULTICAST_ADDR, SSDP_PORT)
                    )
                except Exception as e:
                    logger.error(f"NOTIFY send error: {e}")
            # Announce every 30 seconds (well within the 1800s cache)
            time.sleep(30)

        notify_sock.close()

    def start(self):
        self.running = True
        t1 = threading.Thread(target=self._listen_for_msearch, daemon=True)
        t2 = threading.Thread(target=self._send_notify_loop, daemon=True)
        t1.start()
        t2.start()
        self._threads = [t1, t2]
        logger.info("SSDP server started")

    def stop(self):
        self.running = False
        logger.info("SSDP server stopped")
