# CR200 Bridge

Bridges a **Sonos CR200** remote into an **S2-only** Sonos setup using a
**real S1 Sonos device** as the SonosNet beacon.

The CR200 connects to the network over SonosNet (broadcast by the S1 device),
discovers the bridge via UPnP/SSDP, and uses it for full playback control and
music service browsing — all content comes from the **S2 speaker's** registered
services (Spotify, Apple Music, Tidal, local library, favorites, playlists).

```
CR200 (SonosNet WiFi via S1 device)
    │
    │  SSDP discovery
    │  UPnP SOAP port 1400
    ▼
Bridge (Pi / Mac / Linux)
    ├── ContentDirectory Browse/Search ──→ S2 speaker at port 1400
    │     (music services, library, favorites, playlists)
    │
    ├── AVTransport / RenderingControl ──→ S2 via node-sonos-http-api
    │     (play, pause, stop, next, prev, volume)
    │
    └── S1Monitor (fallback) ──→ mirrors CR200→S1 state changes to S2

S1 device (Sonos Bridge / Connect / Play:1 Gen 1 / etc.)
    └── provides SonosNet WiFi beacon only
```

---

## Requirements

### Hardware

**S1 device** — one of the following, on the same LAN as your S2 system:

| Device | Notes |
|---|---|
| **Sonos Bridge** | Ideal — no speakers, purpose-built SonosNet hub |
| **Sonos Connect** (ZP90) | Line-level audio output |
| **Sonos Connect:Amp** (ZP120) | Built-in amplifier |
| **Sonos Play:1 Gen 1** | Compact speaker |
| **Sonos Play:3 Gen 1** | Mid-size speaker |
| **Sonos Play:5 Gen 1** | Large speaker (oval shape, older design) |
| **Sonos PLAYBAR** | Soundbar |

> The S1 device must be powered on and on the network. It acts purely as the
> SonosNet beacon — the CR200's WiFi. You don't need to play audio from it.

**Bridge host** — any machine on the same LAN:
- Raspberry Pi wired via Ethernet — **recommended**
- Mac or Linux laptop/desktop (content browsing works; CR200 pairing requires
  the host to be able to respond to the CR200's 169.254.x.x link-local address
  — works reliably on a wired Pi, may fail on Mac Wi-Fi)

**S2 speakers** — Era 100/300, Arc, Beam Gen 2, Five, Move 2, etc.

---

### Network

- S1 device, S2 speakers, and bridge host must all be on the **same LAN subnet**.
- SonosNet is only broadcast when at least one Sonos device is wired via Ethernet.
- Multicast to `239.255.255.250` (SSDP) must not be filtered.
- Port **1400** TCP must be open on the bridge host (UPnP server for CR200 SOAP).

---

### Software (on the bridge host)

- **Node.js 18+** and npm
- **Python 3.10+** (stdlib only — no pip packages needed)
- Free ports: **1400** TCP (UPnP), **5005** TCP (node-sonos-http-api), **8080** TCP (status UI)

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/handyandy87/SONOS-CR2002S2.git
cd SONOS-CR2002S2
```

### 2. Install Node.js (Raspberry Pi)

```bash
sudo apt update && sudo apt install -y nodejs npm
node --version   # should be 18.x or later
```

For older distros, install via NodeSource:

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

Verify it can see your speakers:

```bash
curl http://localhost:5005/zones
```

Both S1 and S2 devices should appear.

### 5. Discover your S1 device

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

Note the **room names** shown in quotes — you'll need them in the next step.

### 6. Run the setup wizard

```bash
python3 setup.py
```

The wizard:
- Runs an SSDP scan to show S1 and S2 devices
- Lists rooms from node-sonos-http-api
- Prompts for your S1 room, S2 target room, friendly name, UUID, etc.
- Writes `config.json`

### 7. Start the bridge

```bash
sudo python3 main.py
```

`sudo` is required on Linux for port 1400 (UPnP server for the CR200).

### 8. Pair the CR200

Put the CR200 into Wi-Fi setup mode (hold the Dock button until the setup
screen appears). It will join SonosNet via the S1 device, discover the bridge
via UPnP, and pair with it. After pairing:

- **Browsing**: the CR200's ContentDirectory browse/search is served from the
  S2 speaker — it will see the S2's registered music services, favorites,
  playlists, and local library.
- **Playback**: play/pause/vol/skip commands are forwarded to the S2 speaker.

---

## Configuration reference (`config.json`)

| Key | Description | Default |
|---|---|---|
| `sonos_http_api_base` | node-sonos-http-api URL | `http://localhost:5005` |
| `s1_room_name` | Room name of the S1 device | `""` |
| `s2_room_name` | Room name of the S2 speaker | `""` |
| `poll_interval` | S1 state poll rate in seconds | `1.0` |
| `uuid` | Stable UUID for the bridge (memorised by CR200) | auto-generated |
| `household_id` | Sonos household ID (must match S2 system) | auto-discovered |
| `friendly_name` | Name shown on the CR200 display | `CR200 Bridge` |
| `http_port` | UPnP HTTP server port | `1400` |
| `log_level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `status_port` | Status web UI port | `8080` |

---

## Feature Status

| Feature | Status |
|---|---|
| CR200 discovers bridge via SSDP | ✅ |
| CR200 ContentDirectory Browse → S2 speaker (music services, library) | ✅ |
| CR200 ContentDirectory Search → S2 speaker | ✅ |
| CR200 Favorites browse → S2 favorites | ✅ |
| CR200 Playlists browse → S2 playlists | ✅ |
| CR200 Queue browse → S2 active queue | ✅ |
| CR200 Play / Pause / Stop / Next / Prev → S2 | ✅ |
| CR200 Volume, Mute → S2 | ✅ |
| CR200 Seek by time / track number → S2 | ✅ |
| CR200 Shuffle / Repeat modes → S2 | ✅ |
| CR200 Now Playing (title, artist, album, artwork) | ✅ |
| S1 Monitor — mirrors CR200→S1 commands to S2 (fallback) | ✅ |
| SSDP-based S1 device discovery in setup.py and on misconfiguration | ✅ |
| Status web UI — live room list, now-playing | ✅ |
| Status web UI — playback controls (play/pause/stop/next/prev/vol) | ✅ |
| Status web UI — Favorites and Playlists browser | ✅ |
| Status web UI — S2 ContentDirectory tree browser (breadcrumbs) | ✅ |
| Status web UI — S2 ContentDirectory search | ✅ |
| Systemd service install (Pi autostart) | ✅ |

---

## Status UI

Open `http://<host-ip>:8080` in a browser:

- See all discovered rooms and current playback state
- Select which S2 room the web UI controls
- Basic playback controls (play, pause, stop, next, prev, volume)
- Browse Favorites and Playlists
- **S2 Library & Services tab**: full tree browser of the S2 speaker's
  ContentDirectory — navigate music services (Spotify, Apple Music, Tidal,
  local library) with breadcrumb navigation, and play any item directly
- Search the S2's registered music services from the same tab

---

## Project Structure

```
SONOS-CR2002S2/
  main.py            — Entry point; starts all servers
  config.py          — Default config; overridden by config.json at runtime
  config.json        — Your local settings (gitignored; written by setup.py)
  setup.py           — Interactive setup wizard
  discovery.py       — SSDP-based Sonos device scanner (labels S1 vs S2)
  s1_monitor.py      — Polls S1 device state; mirrors CR200 commands to S2
  soap_handler.py    — CR200 SOAP → S2 actions; ContentDirectory proxy
  ssdp_server.py     — Announces bridge as ZonePlayer (CR200 discovery)
  upnp_server.py     — UPnP HTTP server (port 1400); routes SOAP to handler
  sonos_client.py    — node-sonos-http-api wrapper (room list + control)
  didl_builder.py    — DIDL-Lite XML helpers
  status_server.py   — Status web UI (port 8080) with S2 content browser
logs/
  bridge.log         — Runtime log (gitignored)
```

---

## Troubleshooting

**CR200 can't find any Wi-Fi network**
The CR200 uses SonosNet, not standard Wi-Fi. Plug the S1 device (or any
Sonos speaker) into Ethernet — SonosNet only broadcasts when a device is wired.

**CR200 discovers SonosNet but doesn't find the bridge**
Verify the bridge is running (`sudo python3 main.py`) and that `logs/bridge.log`
shows incoming `M-SEARCH` lines. If it shows `Failed to send SSDP response to
169.254.x.x`, the bridge host cannot reach the CR200's link-local address —
run the bridge on a Pi wired to the same switch as the S1 device.

**CR200 pairs but ContentDirectory is empty / "no items"**
Check that `s2_room_name` in `config.json` exactly matches the room name in
`curl http://localhost:5005/zones`. Set `log_level: "DEBUG"` and look for
`S2 Browse failed` lines in `logs/bridge.log`.

**Bridge fails to start: "Address already in use" on port 1400**
```bash
sudo lsof -i :1400
```

**No rooms found on startup**
```bash
curl http://localhost:5005/zones
```
If empty or connection refused, node-sonos-http-api is not running.

---

## Testing Prerequisites

This project has **not been fully tested**. Validate against real hardware.

### Required Hardware

- A real **S1 Sonos device** (see table above) powered on and on the network
- At least one **S2 speaker** reachable by node-sonos-http-api
- A **CR200** with working SonosNet connectivity to the S1 device

### What Still Needs Testing

- [ ] End-to-end CR200 ContentDirectory browse of Spotify, Apple Music, etc.
- [ ] CR200 search returning results from S2 music services
- [ ] Volume / seek mirroring accuracy
- [ ] Multiple S2 speakers in a group (zone coordinator selection)
- [ ] Bridge restart while CR200 is active (reconnection)
- [ ] Behaviour when S1 device is temporarily unreachable
