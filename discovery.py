"""
Sonos Device Discovery

Finds Sonos ZonePlayer devices on the local network via SSDP (UPnP multicast
M-SEARCH), then fetches each device's UPnP description from port 1400 to
identify its model name and room name.

Used by setup.py to help the user identify which device is the S1 unit
their CR200 will pair with.

S1 devices (cannot run Sonos S2 firmware):
  Sonos Bridge         — BRIDGE  — no audio output; dedicated SonosNet hub
  Sonos Connect        — ZP90   — line-level audio output
  Sonos Connect:Amp    — ZP120  — built-in amplifier
  Sonos Play:1 Gen 1   — S1     — compact speaker
  Sonos Play:3 Gen 1   — S3     — mid-size speaker
  Sonos Play:5 Gen 1   — S5     — large speaker (oval shape, older design)
  Sonos PLAYBAR        — PLAYBAR — soundbar (S1 era)
  Sonos Sub (Gen 1/2)  — SUB    — subwoofer

S2 devices (Era 100/300, Arc, Beam Gen 2, Five, Move 2, etc.) are also
discovered but labelled as S2 so the user can distinguish them.

Usage:
    from discovery import discover_sonos_devices
    devices = discover_sonos_devices(timeout=3.0)
    for d in devices:
        print(d["ip"], d["room_name"], d["model_name"], d["generation"])
"""

import socket
import struct
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Optional

# ---------------------------------------------------------------------------
# Known S1 model identifiers
# (modelNumber values from device_description.xml)
# ---------------------------------------------------------------------------

_S1_MODEL_NUMBERS = {
    "BRIDGE",
    "ZP90",
    "ZP120",
    "S1",
    "S3",
    "S5",
    "PLAYBAR",
    "SUB",
    "ZP80",   # old Connect
    "ZP100",  # old Connect:Amp
}

# Friendly label overrides so users see familiar names
_MODEL_LABELS = {
    "BRIDGE":  "Sonos Bridge",
    "ZP90":    "Sonos Connect",
    "ZP80":    "Sonos Connect (old)",
    "ZP120":   "Sonos Connect:Amp",
    "ZP100":   "Sonos Connect:Amp (old)",
    "S1":      "Sonos Play:1 Gen 1",
    "S3":      "Sonos Play:3 Gen 1",
    "S5":      "Sonos Play:5 Gen 1",
    "PLAYBAR": "Sonos PLAYBAR",
    "SUB":     "Sonos Sub (Gen 1/2)",
}


# ---------------------------------------------------------------------------
# SSDP discovery
# ---------------------------------------------------------------------------

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MX   = 2   # maximum wait seconds (UPnP spec)

MSEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
    "MAN: \"ssdp:discover\"\r\n"
    f"MX: {SSDP_MX}\r\n"
    "ST: urn:schemas-upnp-org:device:ZonePlayer:1\r\n"
    "\r\n"
)


def _ssdp_search(timeout: float) -> list[str]:
    """
    Send an SSDP M-SEARCH and collect unique LOCATION URLs from responses.
    Returns a list of LOCATION header values (device description URLs).
    """
    locations: set[str] = set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.settimeout(0.5)

    try:
        sock.sendto(MSEARCH.encode(), (SSDP_ADDR, SSDP_PORT))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, _ = sock.recvfrom(4096)
                msg = data.decode("utf-8", errors="ignore")
                for line in msg.splitlines():
                    if line.upper().startswith("LOCATION:"):
                        loc = line.split(":", 1)[1].strip()
                        locations.add(loc)
                        break
            except socket.timeout:
                continue
    finally:
        sock.close()

    return list(locations)


# ---------------------------------------------------------------------------
# Device description fetch + parse
# ---------------------------------------------------------------------------

def _fetch_description(location_url: str, timeout: float = 3.0) -> Optional[dict]:
    """
    Fetch and parse a UPnP device description XML.
    Returns a dict with keys: ip, uuid, model_number, model_name, friendly_name.
    Returns None on any error.
    """
    try:
        with urllib.request.urlopen(location_url, timeout=timeout) as resp:
            xml_bytes = resp.read()
    except Exception:
        return None

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    # Strip namespace for simpler tag matching
    def _text(tag: str) -> str:
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == tag and el.text:
                return el.text.strip()
        return ""

    # Extract IP from the location URL (http://<ip>:1400/...)
    try:
        ip = location_url.split("//")[1].split(":")[0]
    except IndexError:
        ip = ""

    return {
        "ip":            ip,
        "uuid":          _text("UDN").replace("uuid:", ""),
        "model_number":  _text("modelNumber"),
        "model_name":    _text("modelName"),
        "friendly_name": _text("friendlyName"),
    }


# ---------------------------------------------------------------------------
# Room name lookup (Sonos device status endpoint)
# ---------------------------------------------------------------------------

def _fetch_room_name(ip: str, timeout: float = 2.0) -> str:
    """
    Fetch the Sonos-specific /status/topology page and extract the room name,
    or fall back to the UPnP friendlyName.
    """
    try:
        url = f"http://{ip}:1400/xml/device_description.xml"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            xml = resp.read().decode("utf-8", errors="ignore")
        root = ET.fromstring(xml)
        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local == "roomName" and el.text:
                return el.text.strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_sonos_devices(timeout: float = 3.0) -> list[dict]:
    """
    Discover all Sonos ZonePlayer devices on the local network via SSDP.

    Returns a list of dicts, each with:
        ip           — device IP address
        uuid         — device UUID
        model_number — e.g. "BRIDGE", "ZP90", "S1"
        model_name   — friendly model label
        friendly_name — room name from UPnP (may differ from node-sonos-http-api)
        generation   — "S1" or "S2"
        likely_s1    — True if this device is a known S1-only model
    """
    locations = _ssdp_search(timeout)

    results = []
    lock = threading.Lock()

    def fetch_one(loc):
        info = _fetch_description(loc, timeout=2.0)
        if not info:
            return
        model_num = info["model_number"].upper()
        is_s1 = model_num in _S1_MODEL_NUMBERS
        info["model_name"] = _MODEL_LABELS.get(model_num, info["model_name"])
        info["generation"] = "S1" if is_s1 else "S2"
        info["likely_s1"] = is_s1
        with lock:
            results.append(info)

    threads = [threading.Thread(target=fetch_one, args=(loc,), daemon=True)
               for loc in locations]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)

    # Sort: S1 devices first, then by IP
    results.sort(key=lambda d: (not d["likely_s1"], d["ip"]))
    return results


def print_discovered_devices(devices: list[dict]):
    """Pretty-print a list of discovered devices to stdout."""
    if not devices:
        print("  No Sonos devices found on the network.")
        return

    s1_devs = [d for d in devices if d["likely_s1"]]
    s2_devs = [d for d in devices if not d["likely_s1"]]

    if s1_devs:
        print("  S1 devices (CR200-compatible):")
        for d in s1_devs:
            print(f"    {d['ip']:16s}  {d['model_name']:30s}  \"{d['friendly_name']}\"")

    if s2_devs:
        print("  S2 devices:")
        for d in s2_devs:
            print(f"    {d['ip']:16s}  {d['model_name']:30s}  \"{d['friendly_name']}\"")
