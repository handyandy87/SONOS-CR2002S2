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

## Platform requirement — Raspberry Pi (or wired Linux host)

**The bridge must run on a Raspberry Pi (or other Linux machine) connected via
Ethernet to the same switch as your wired Sonos speaker.**

macOS was tested during development and the software layer works, but macOS
cannot be used for actual CR200 pairing. When the CR200 sends SSDP M-SEARCH
packets it uses a **169.254.x.x link-local source address** (SonosNet
addressing). A Mac on Wi-Fi cannot route packets back to that address — the OS
drops them before they leave the NIC. The SSDP response never arrives, the CR200
never discovers the bridge, and pairing fails. This is a network topology
limitation, not a software bug.

A Raspberry Pi wired to the same switch as a Sonos speaker sits on the correct
network segment and reaches the CR200's link-local address without issue.

---

## Requirements

### Hardware

- **Raspberry Pi** (any model with Ethernet) — connected via Ethernet cable to
  the same switch/router as your Sonos speakers.
- **At least one Sonos device wired via Ethernet** to your router.
  The CR200 connects over **SonosNet** — Sonos's proprietary 5 GHz wireless
  mesh — which is only broadcast when at least one speaker is wired. An
  all-Wi-Fi setup will not broadcast a SonosNet that the CR200 can join.

  > **Note:** This requirement is based on how SonosNet works and has not yet
  > been fully validated in an all-S2 environment. If you can confirm behaviour
  > either way, please open an issue.

### Software (installed on the Pi)

- **Node.js 18+** and npm
- **Python 3.10+** (stdlib only — no pip packages needed)
- Free ports: **1400** TCP, **1900** UDP multicast, **5005** TCP, **8080** TCP

---

## Getting Started (Raspberry Pi)

### 1. Clone the repo

```bash
git clone https://github.com/handyandy87/SONOS-CR2002S2.git
cd SONOS-CR2002S2
```

### 2. Install Node.js

```bash
sudo apt update && sudo apt install -y nodejs npm
node --version   # should be 18.x or later
npm --version
```

If `apt` gives you an old Node version, install the current LTS via NodeSource:

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
```

### 3. Install node-sonos-http-api

The package is not on the npm registry — install from GitHub:

```bash
sudo npm install -g https://github.com/jishi/node-sonos-http-api
```

Find the installed path (you'll need it in step 5):

```bash
find /usr/local/lib/node_modules /usr/lib/node_modules \
     -name server.js -path "*/sonos-http-api/*" 2>/dev/null
# Typical result: /usr/local/lib/node_modules/sonos-http-api/server.js
```

### 4. Run the setup wizard

```bash
python3 setup.py
```

The wizard probes your Sonos network, auto-discovers your Household ID and
rooms, and writes `config.json`. Follow the prompts — Enter accepts the default
shown in brackets.

### 5. Start node-sonos-http-api

Open a dedicated terminal (or use `screen`/`tmux`) and run:

```bash
node /usr/local/lib/node_modules/sonos-http-api/server.js
```

Verify it can see your speakers:

```bash
curl http://localhost:5005/zones
# Should return JSON with your Sonos rooms
```

### 6. Start the bridge

In a second terminal:

```bash
sudo python3 main.py
```

`sudo` is required for port 1400 (a privileged port on Linux).

### 7. Pair the CR200

Put the CR200 into Wi-Fi setup mode (hold the Dock button until the display
shows the setup screen). It will join the SonosNet broadcast by your wired
speaker, then discover the bridge via UPnP and pair automatically.

---

## Setup (detailed)

### Interactive wizard (recommended)

```bash
python3 setup.py
```

| Step | What it does |
|---|---|
| Python check | Confirms Python 3.10+ is present |
| Node.js | Detects `node`/`npm`; offers `sudo apt install -y nodejs npm` if missing |
| node-sonos-http-api | Detects existing install; offers `npm install -g https://github.com/jishi/node-sonos-http-api` if missing |
| API connectivity | Probes `http://localhost:5005/zones`; offers to start the API in the background if installed but not running |
| Speaker discovery | Auto-discovers your Household ID and lists all Sonos rooms |
| Configuration | Prompts for friendly name, ports, default room, log level, etc. |
| `config.json` | Writes (or updates) the bridge config file |
| `logs/` | Creates the log directory if absent |
| Autostart | Optionally installs systemd services for Pi boot launch |

---

### Manual setup (advanced)

**1. Install and start node-sonos-http-api**

```bash
sudo npm install -g https://github.com/jishi/node-sonos-http-api
node /usr/local/lib/node_modules/sonos-http-api/server.js
```

Verify:
```bash
curl http://localhost:5005/zones
```

**2. Get your Household ID**

```bash
curl http://localhost:5005/zones | python3 -m json.tool | grep -i household
```

If that returns nothing, use the coordinator's UUID from the zones output as
the household ID.

**3. Create `config.json`**

```json
{
  "uuid": "generate-with-python3-c-import-uuid-print-uuid.uuid4()",
  "household_id": "RINCON_xxxxxxxxxxxx",
  "friendly_name": "CR200 Bridge",
  "http_port": 1400,
  "sonos_http_api_base": "http://localhost:5005",
  "default_room": "Kitchen",
  "status_port": 8080,
  "log_level": "INFO"
}
```

Generate a UUID:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

**4. Run the bridge**

```bash
sudo python3 main.py
```

**5. Connect the CR200**

Put the CR200 into Wi-Fi setup mode. It will join SonosNet and discover the
bridge via UPnP.

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
SONOS-CR2002S2/
  main.py            — Entry point; starts all servers
  config.py          — Default config; overridden by config.json at runtime
  config.json        — Your local settings (gitignored; written by setup.py)
  setup.py           — Interactive setup wizard
  sonos_client.py    — node-sonos-http-api wrapper
  soap_handler.py    — CR200 SOAP → SonosClient translation
  didl_builder.py    — DIDL-Lite XML (now-playing + artwork)
  ssdp_server.py     — Fake S1 UPnP presence (SSDP multicast)
  upnp_server.py     — UPnP HTTP server (port 1400)
  status_server.py   — Status web UI (port 8080)
logs/
  bridge.log         — Runtime log (gitignored)
```

---

## Troubleshooting

**CR200 can't find any Wi-Fi network to join**
The CR200 connects over SonosNet, not standard Wi-Fi. SonosNet is only
broadcast when at least one Sonos device is wired via Ethernet to your router.
If your entire system is Wi-Fi only, plug one speaker in via Ethernet — the
CR200 should then see the SonosNet SSID during its Wi-Fi setup.

**CR200 discovers SonosNet but doesn't find the bridge**
Verify the bridge is running on the Pi (`sudo python3 main.py`) and that
`logs/bridge.log` shows incoming `M-SEARCH` lines from the CR200's IP.
If it only shows `Failed to send SSDP response to 169.254.x.x` errors, the
bridge is not running on a host that can reach the CR200's link-local address —
see the [Platform requirement](#platform-requirement--raspberry-pi-or-wired-linux-host)
section above.

**Bridge fails to start: "Address already in use" on port 1400**
Another process is using port 1400. Find and stop it:
```bash
sudo lsof -i :1400
```

**No rooms found on startup**
Run `curl http://localhost:5005/zones`. If it returns an empty array or
connection refused, node-sonos-http-api is not running or can't see your
speakers. Ensure both the Pi and your Sonos speakers are on the same LAN subnet.

**node-sonos-http-api command not found**
The bare `node-sonos-http-api` binary is not linked after a GitHub install.
Run it with the full path instead:
```bash
node /usr/local/lib/node_modules/sonos-http-api/server.js
```

**Blank now-playing on CR200 screen**
Set `log_level: "DEBUG"` in `config.json` and verify `GetPositionInfo` SOAP
calls appear in `logs/bridge.log`. Also check:
```bash
curl http://localhost:5005/<RoomName>/state
```
