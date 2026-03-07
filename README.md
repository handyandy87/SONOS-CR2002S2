# CR200 Bridge

Bridges a **Sonos CR200** remote into an **S2-only** Sonos setup using a
**real S1 Sonos device** as the network intermediary.

The CR200 pairs with the S1 device natively over SonosNet (as it was designed to).
The bridge code runs on any machine on the same network — Pi, Mac, or Linux — polls
the S1 device via **node-sonos-http-api**, and mirrors every CR200-driven action
(play, pause, volume, skip) to your S2 speakers.

```
CR200 (SonosNet)
    │  UPnP/SOAP — native CR200 protocol
    ▼
Real S1 Device  (Sonos Bridge / Connect / Connect:Amp / Play:1 Gen 1 / etc.)
    │
    │          [Pi / Mac / Linux — this bridge]
    │          polls S1 state via node-sonos-http-api
    │          mirrors play / pause / vol / next / prev
    │                        ↓
    └─────────────→  S2 Speakers  (Era 100/300, Arc, Beam Gen 2, Five, Move 2, etc.)
```

---

## Requirements

### Hardware

**S1 device** — one of the following (must be on the same network as your S2 system):

| Device | Notes |
|---|---|
| **Sonos Bridge** | Ideal — no speakers, purpose-built SonosNet hub |
| **Sonos Connect** (ZP90) | Line-level audio output |
| **Sonos Connect:Amp** (ZP120) | Built-in amplifier |
| **Sonos Play:1 Gen 1** | Compact speaker |
| **Sonos Play:3 Gen 1** | Mid-size speaker |
| **Sonos Play:5 Gen 1** | Large speaker (oval shape) |
| **Sonos PLAYBAR** | Soundbar |

> The S1 device must be powered on, connected to your network via Ethernet or
> Wi-Fi, and **not** updated to S2 firmware. It acts purely as a control
> intermediary — you don't need to play audio from it.

**Bridge host** — any machine on the same LAN as the S1 device and S2 speakers:

- Raspberry Pi (any model with Ethernet) — recommended
- Mac or Linux laptop/desktop

**S2 speakers** — Era 100, Era 300, Arc, Beam Gen 2, Five, Move 2, or any
other Sonos S2 device.

---

### Network

- S1 device, S2 speakers, and bridge host must all be on the **same LAN subnet**.
- The CR200 connects to the S1 device over **SonosNet** — Sonos's proprietary
  5 GHz mesh network. SonosNet broadcasts when at least one Sonos device is
  wired via Ethernet.
- Multicast to `239.255.255.250` (SSDP/UPnP) must not be filtered by your
  router or switch.
- If devices are on **different VLANs**, you will need multicast routing or an
  SSDP/mDNS proxy (`avahi-daemon` reflector, `udp-proxy-2020`, etc.).

---

### Software (on the bridge host)

- **Node.js 18+** and npm
- **Python 3.10+** (stdlib only — no pip packages needed)
- Free ports: **5005** TCP, **8080** TCP

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/handyandy87/SONOS-CR2002S2.git
cd SONOS-CR2002S2
```

### 2. Install Node.js (if needed)

```bash
sudo apt update && sudo apt install -y nodejs npm
node --version   # should be 18.x or later
```

If `apt` gives you an old Node version, install the current LTS via NodeSource:

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
```

### 3. Install node-sonos-http-api

```bash
sudo npm install -g https://github.com/jishi/node-sonos-http-api
```

### 4. Start node-sonos-http-api

Open a dedicated terminal (or use `screen`/`tmux`):

```bash
node /usr/local/lib/node_modules/sonos-http-api/server.js
```

Verify it can see your speakers (both S1 and S2 devices should appear):

```bash
curl http://localhost:5005/zones
```

### 5. Discover your S1 device

Run the discovery utility to see all Sonos devices on the network and
identify which one is your S1 device:

```bash
python3 -c "from discovery import discover_sonos_devices, print_discovered_devices; print_discovered_devices(discover_sonos_devices())"
```

Example output:
```
  S1 devices (CR200-compatible):
    192.168.1.42     Sonos Bridge                    "Bridge"
  S2 devices:
    192.168.1.55     Sonos Era 100                   "Living Room"
    192.168.1.56     Sonos Arc                       "TV Room"
```

Note the **room names** — you'll need them in the next step.

### 6. Run the setup wizard

```bash
python3 setup.py
```

The wizard will:
- Run an SSDP scan to show discovered S1 and S2 devices
- List all rooms from node-sonos-http-api
- Prompt you to select your S1 device room and your S2 target room
- Write `config.json`

### 7. Start the bridge

```bash
python3 main.py
```

No `sudo` required — the bridge no longer listens on privileged ports.

### 8. Pair the CR200

Put the CR200 into Wi-Fi setup mode (hold the Dock button until the setup
screen appears). It will join the SonosNet broadcast by the S1 device and
pair with it. Once paired, any playback commands on the CR200 are mirrored
to your S2 speakers by the bridge.

---

## Setup (detailed)

### Interactive wizard (recommended)

```bash
python3 setup.py
```

| Step | What it does |
|---|---|
| Python check | Confirms Python 3.10+ is present |
| Node.js | Detects `node`/`npm`; offers `sudo apt install` if missing |
| node-sonos-http-api | Detects existing install; offers npm install if missing |
| SSDP scan | Scans the network and labels S1 vs S2 devices |
| API connectivity | Probes `http://localhost:5005/zones`; offers to start the API if not running |
| Room selection | Lists all discovered rooms; prompts for S1 room and S2 target room |
| `config.json` | Writes the bridge config file |
| `logs/` | Creates the log directory if absent |
| Autostart | Optionally installs systemd services for Pi boot launch |

### Manual setup (advanced)

**1. Install and start node-sonos-http-api**

```bash
sudo npm install -g https://github.com/jishi/node-sonos-http-api
node /usr/local/lib/node_modules/sonos-http-api/server.js
```

**2. Find your room names**

```bash
curl http://localhost:5005/zones | python3 -m json.tool | grep roomName
```

**3. Create `config.json`**

```json
{
  "sonos_http_api_base": "http://localhost:5005",
  "s1_room_name": "Bridge",
  "s2_room_name": "Living Room",
  "poll_interval": 1.0,
  "log_level": "INFO",
  "status_port": 8080
}
```

**4. Run the bridge**

```bash
python3 main.py
```

---

## Feature Status

| Feature | Status |
|---|---|
| Play / Pause / Stop mirrored from CR200 → S2 | ✅ |
| Volume changes mirrored | ✅ |
| Mute / Unmute mirrored | ✅ |
| Next / Previous track mirrored | ✅ |
| Large track jump (seek to track N) mirrored | ✅ |
| SSDP-based S1 device discovery | ✅ |
| Status web UI — live room list, now-playing, command log | ✅ |
| Status web UI — playback controls (play/pause/vol/next/prev) | ✅ |
| Status web UI — Sonos Favorites and Playlists browser | ✅ |
| Configurable poll interval | ✅ |
| Systemd service install (Pi autostart) | ✅ |

---

## Status UI

Open `http://<host-ip>:8080` in a browser to:
- See all discovered rooms and current playback state
- Control S2 playback directly (play, pause, next, previous, volume)
- Browse and play Sonos Favorites and Playlists
- View a live log of every synced command

---

## Project Structure

```
SONOS-CR2002S2/
  main.py            — Entry point; starts all components
  config.py          — Default config; overridden by config.json at runtime
  config.json        — Your local settings (gitignored; written by setup.py)
  setup.py           — Interactive setup wizard
  discovery.py       — SSDP-based Sonos device scanner (identifies S1 devices)
  s1_monitor.py      — Polls S1 device state; mirrors CR200 commands to S2
  sonos_client.py    — node-sonos-http-api wrapper (room list + playback control)
  didl_builder.py    — DIDL-Lite XML helpers
  status_server.py   — Status web UI (port 8080)
logs/
  bridge.log         — Runtime log (gitignored)
```

The following files are kept for reference but are **not used** in the current
S1-device-based architecture (they were needed when the bridge faked an S1 device):

```
  ssdp_server.py     — (legacy) fake SSDP broadcaster
  upnp_server.py     — (legacy) fake UPnP HTTP server
  soap_handler.py    — (legacy) CR200 SOAP command handler
```

---

## Troubleshooting

**CR200 can't find any Wi-Fi network to join**
The CR200 connects over SonosNet, not standard Wi-Fi. SonosNet is only broadcast
when at least one Sonos device is wired via Ethernet. Plug the S1 device (or any
Sonos speaker) into Ethernet — the CR200 should then see the SonosNet SSID.

**S1 room not found at startup**
Run `curl http://localhost:5005/zones` and confirm the S1 device appears.
Verify the `s1_room_name` in `config.json` exactly matches the room name in the
API output (case-sensitive). Also check that the S1 device is powered on.

**Commands aren't reaching S2**
Set `log_level: "DEBUG"` in `config.json` and check `logs/bridge.log` for
`CR200 → S1` lines. If you see state changes detected but S2 commands failing,
verify the `s2_room_name` in `config.json` matches exactly.

**Bridge fails to start: missing s1_room_name or s2_room_name**
Run `python3 setup.py` to configure the bridge. On misconfiguration, the bridge
will also run an SSDP scan and log any S1 devices it finds.

**No rooms found on startup**
Run `curl http://localhost:5005/zones`. If it returns an empty array or
connection refused, node-sonos-http-api is not running or can't see your speakers.

**node-sonos-http-api command not found**
The bare binary is not linked after a GitHub install. Run with full path:
```bash
node /usr/local/lib/node_modules/sonos-http-api/server.js
```

---

## Testing Prerequisites

This project has **not been fully tested**. Before using or contributing,
ensure the following conditions are met.

### Required Hardware

- A real **S1 Sonos device** (see table above) powered on and on the network
- At least one **S2 speaker** reachable by node-sonos-http-api
- A **CR200** to test with

### What Still Needs Testing

- [ ] End-to-end CR200 → S1 device → S2 speaker command flow
- [ ] Volume mirroring accuracy
- [ ] Next/previous detection via track number delta
- [ ] Behaviour when S1 device is temporarily unreachable
- [ ] Multiple S2 speakers in a group
