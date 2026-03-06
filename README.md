# CR200 Bridge

Connects a **Sonos CR200** remote to an **S2-only** Sonos setup by running a
fake S1-compatible UPnP device on a Raspberry Pi (or any Linux machine on your
LAN). The CR200 pairs with the bridge; the bridge translates commands to your
real S2 speakers via SoCo.

```
CR200 (Wi-Fi)
    │  UPnP/SOAP
    ▼
[Raspberry Pi — this bridge]
    │  SoCo (S2 local HTTP API)
    ▼
Real S2 Speakers
```

---

## Requirements

- Python 3.10+
- Raspberry Pi (or any machine) on the **same LAN subnet** as your Sonos speakers
- Port **1400** (TCP) and **1900** (UDP multicast) available

```bash
pip install soco
```

---

## Setup

### 1. Get your Sonos Household ID

```bash
python3 -c "import soco; s = list(soco.discover())[0]; print(s.household_id)"
```

### 2. Edit `bridge/config.py`

```python
BRIDGE_CONFIG = {
    "uuid": "1a2b3c4d-...",          # Keep the default or generate a new one
    "household_id": "Sonos_abc123",  # ← Paste your household ID here
    "friendly_name": "CR200 Bridge",
    "http_port": 1400,
    "status_port": 8080,
    "log_level": "INFO",
}
```

### 3. Run the bridge

```bash
cd bridge
python3 main.py
```

### 4. Connect the CR200

Put the CR200 into setup mode (hold the button on the back until the screen
shows setup instructions), then connect it to your Wi-Fi network as normal.
It will perform UPnP discovery and should find the bridge.

---

## Status UI

Open `http://<pi-ip>:8080` in a browser to see:
- Discovered speakers + their playback state
- Active speaker selector (click to switch which speaker CR200 controls)
- Live command log showing what the CR200 is sending
- Manual rediscovery button

---

## Project Structure

```
bridge/
  main.py           — Entry point, wires everything together
  config.py         — Edit this before running
  ssdp_server.py    — Broadcasts fake S1 UPnP presence (SSDP)
  upnp_server.py    — HTTP server: device description XML + SOAP endpoint
  soap_handler.py   — Translates CR200 SOAP actions → SoCo API calls
  zone_manager.py   — Discovers & tracks S2 speakers via SoCo
  status_server.py  — Web status UI on port 8080
logs/
  bridge.log        — Persistent log file
```

---

## Troubleshooting

**CR200 doesn't find the bridge**
- Ensure the Pi and CR200 are on the same subnet
- Check that port 1400 (TCP) isn't blocked by a firewall
- Try `sudo python3 main.py` — port 1400 may need elevated privileges
- Check `logs/bridge.log` for SSDP M-SEARCH activity

**CR200 finds the bridge but commands don't work**
- Check the Status UI command log to confirm commands are arriving
- Ensure SoCo can discover your speakers: `python3 -c "import soco; print(soco.discover())"`
- Try setting `log_level: "DEBUG"` in config.py for verbose output

**Volume/transport state not updating on CR200 screen**
- The bridge doesn't yet push UPnP NOTIFY events back to the CR200
  (it only responds to queries). The CR200 polls periodically so state
  will update — just not instantly. Event subscription push is a future enhancement.

---

## Known Limitations / Future Work

- [ ] UPnP event subscription push (real-time state updates to CR200)
- [ ] Multi-room / group switching via CR200 UI
- [ ] Music library browsing (ContentDirectory currently returns queue only)
- [ ] Alarm / sleep timer passthrough
- [ ] Auto-detect household ID without manual config step
