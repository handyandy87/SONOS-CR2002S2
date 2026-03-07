# CR200 Bridge

Bridges a **Sonos CR200** remote into an **S2-only** Sonos setup.

Runs a fake S1-compatible UPnP device on your network that the CR200 pairs with.
All commands are translated via **node-sonos-http-api**, which uses each speaker's
own authenticated SMAPI client — meaning Spotify, Apple Music, Tidal, favorites,
playlists, search, and now-playing metadata all work without any re-authentication.

```
CR200 (SonosNet Wi-Fi)
    │  UPnP/SOAP (port 1400)
    ▼
[Raspberry Pi — this bridge]   ← fake S1 Sonos device
    │  HTTP REST (port 5005)
    ▼
node-sonos-http-api
    │  Sonos local HTTP API + SMAPI
    ▼
Real S2 Speakers
```

---

## Requirements

### Hardware

- **At least one S1-generation Sonos device wired via Ethernet** to your router.
  The CR200 connects over **SonosNet** — Sonos's proprietary wireless mesh — not
  standard Wi-Fi. SonosNet is only broadcast when at least one Sonos device is
  wired; an all-S2 system where every speaker is on Wi-Fi may not broadcast a
  SonosNet that the CR200 can join.

  > **Note:** This requirement is based on how SonosNet works and has not yet been
  > fully validated in an S1+S2 mixed environment. If you can confirm behaviour
  > either way, please open an issue.

- A machine (Raspberry Pi etc.) on the **same LAN subnet** as your Sonos speakers

### Software

- **Node.js 14+** and npm
- **Python 3.10+** (stdlib only — no pip packages needed)
- Free ports: **1400** TCP, **1900** UDP multicast, **5005** TCP, **8080** TCP

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/handyandy87/SONOS-CR2002S2.git
cd SONOS-CR2002S2
```

### 2. Confirm Python 3.10+

```bash
python3 --version
# Python 3.10.x or higher required
```

On Raspberry Pi OS (Bullseye or later) Python 3.11 is included. On older images:

```bash
sudo apt update && sudo apt install -y python3
```

### 3. Run the setup wizard

```bash
python3 setup.py
```

The wizard installs Node.js and node-sonos-http-api if they are missing, probes
your Sonos network, and writes `config.json`. Follow the prompts — pressing Enter
accepts the suggested default for each field.

### 4. Start the bridge

```bash
python3 main.py
# If port 1400 is refused: sudo python3 main.py
```

### 5. Pair the CR200

Put the CR200 into Wi-Fi setup mode (hold the Dock button until the display shows
the setup screen). It will discover and join the SonosNet broadcast by your wired
speaker, then find the bridge via UPnP automatically.

---

## Setup (detailed)

### Quick start — interactive wizard (recommended)

Run the setup wizard once after cloning the repo:

```bash
python3 setup.py
```

The wizard walks you through every step interactively:

| Step | What it does |
|---|---|
| Python check | Confirms Python 3.10+ is present |
| Node.js | Detects `node`/`npm`; offers `sudo apt install -y nodejs npm` if missing |
| node-sonos-http-api | Detects existing install; offers `npm install -g node-sonos-http-api` if missing |
| API connectivity | Probes `http://localhost:5005/zones`; offers to start the API in the background if installed but not running |
| Speaker discovery | Auto-discovers your Household ID and lists all Sonos rooms |
| Configuration | Prompts for friendly name, ports, log level, etc. — with sensible defaults |
| `config.json` | Writes (or updates) the bridge config file |
| `logs/` | Creates the log directory if absent |
| Autostart | Optionally installs systemd services for Pi boot launch |

After the wizard finishes, start the bridge:

```bash
python3 main.py   # may need sudo for port 1400
```

Then put the CR200 into Wi-Fi setup mode and connect it to your network as normal — it will discover the bridge via UPnP and pair with it.

---

### Manual setup (advanced)

If you prefer to configure things by hand:

**1. Install and start node-sonos-http-api**

```bash
npm install -g node-sonos-http-api
node-sonos-http-api
```

Verify:
```bash
curl http://localhost:5005/zones
# Should return JSON with your Sonos rooms
```

**2. Get your Household ID**

```bash
curl http://localhost:5005/zones | python3 -m json.tool | grep -i household
```

**3. Create `config.json`**

```json
{
  "uuid": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
  "household_id": "Sonos_REPLACE_ME",
  "friendly_name": "CR200 Bridge",
  "http_port": 1400,
  "sonos_http_api_base": "http://localhost:5005",
  "status_port": 8080,
  "log_level": "INFO"
}
```

**4. Run the bridge**

```bash
mkdir -p logs
python3 main.py   # may need sudo for port 1400
```

**5. Connect the CR200**

Put the CR200 into Wi-Fi setup mode and connect it to your network as normal.
It will discover the bridge via UPnP and pair with it.

---

## Feature Status

| Feature | Status |
|---|---|
| Play / Pause / Stop / Next / Prev | ✅ |
| Volume, Mute | ✅ |
| Seek by time or track number | ✅ |
| Shuffle / Repeat modes | ✅ |
| Now Playing — title, artist, album | ✅ |
| Album artwork on CR200 screen | ✅ |
| Queue browsing | ✅ |
| Sonos Favorites | ✅ |
| Playlists | ✅ |
| Music service browsing (Spotify, Apple Music, etc.) | ✅ via node-sonos-http-api |
| Search | ✅ |
| Zone switching via Status UI | ✅ |
| Real-time state push to CR200 | 🔄 Planned |

---

## Status UI

Open `http://<pi-ip>:8080` in a browser to see live now-playing with artwork,
switch which room the CR200 controls, and view a log of every command received.

---

## Project Structure

```
bridge/
  main.py            — Entry point
  config.py          — Edit before running
  sonos_client.py    — node-sonos-http-api wrapper
  soap_handler.py    — CR200 SOAP → SonosClient
  didl_builder.py    — DIDL-Lite XML (now-playing + artwork)
  ssdp_server.py     — Fake S1 UPnP presence (SSDP)
  upnp_server.py     — UPnP HTTP server
  status_server.py   — Web UI on port 8080
logs/
  bridge.log
```

---

## Troubleshooting

**CR200 can't find any Wi-Fi network to join**
The CR200 connects over **SonosNet**, not standard Wi-Fi. SonosNet is only
broadcast when at least one Sonos device is wired via Ethernet to your router.
If your entire system is S2 and wireless, plug one speaker in via cable — the
CR200 should then see the SonosNet SSID during its Wi-Fi setup.

> This behaviour is suspected but not yet fully validated. See the Hardware
> requirements note above.

**No rooms found on startup**
Run `curl http://localhost:5005/zones` — if empty, node-sonos-http-api can't
see your speakers. Ensure it's on the same subnet.

**CR200 doesn't discover the bridge**
Port 1400 may need elevated privileges: `sudo python3 main.py`. Check
`logs/bridge.log` for incoming SSDP M-SEARCH lines.

**Blank now-playing on CR200 screen**
Set `log_level: "DEBUG"` and verify `GetPositionInfo` SOAP calls appear in
the log. Also check `curl http://localhost:5005/<RoomName>/state` returns
track data.
