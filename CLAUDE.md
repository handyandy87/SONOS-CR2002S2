# CLAUDE.md

This file provides guidance to AI assistants (Claude Code and similar tools) working in this repository.

## Repository Overview

**Repository**: SONOS-CR2002S2
**Remote**: handyandy87/SONOS-CR2002S2
**Purpose**: A Python bridge application that lets a legacy **Sonos CR200** remote control modern **S2-only** Sonos speakers, using a real S1 device (Bridge, Connect, Play:1 Gen 1, etc.) as the SonosNet beacon.

**How it works:**
1. The CR200 discovers the bridge via SSDP (multicast) and connects over SOAP/UPnP on port 1400.
2. The bridge proxies AVTransport/RenderingControl SOAP commands to an S2 speaker via `node-sonos-http-api`.
3. A poller monitors the S1 device for CR200-driven state changes (play/pause/volume/track) and mirrors them to the S2 room.
4. A web status UI is served on port 8080.

---

## Project Type

- **Primary language**: Python 3.10+
- **External runtime dependency**: Node.js + [`node-sonos-http-api`](https://github.com/jishi/node-sonos-http-api) (HTTP wrapper for Sonos)
- **Python dependencies**: stdlib only — no `pip install` required
- **Deployment target**: Raspberry Pi (or any Linux/macOS host) on the same LAN as the Sonos system

---

## Directory Structure

```
SONOS-CR2002S2/
├── main.py              # Entry point; starts all servers in order
├── config.py            # Loads defaults + merges config.json at import time
├── setup.py             # Interactive CLI wizard that writes config.json
├── discovery.py         # SSDP-based Sonos device scanner
├── sonos_client.py      # Wrapper around node-sonos-http-api HTTP API
├── s1_monitor.py        # Polls S1 device; mirrors state changes to S2
├── soap_handler.py      # Maps CR200 SOAP actions → S2 commands
├── ssdp_server.py       # Announces the bridge via UPnP SSDP multicast
├── upnp_server.py       # HTTP server: device description XML + SOAP endpoint
├── status_server.py     # Web UI on port 8080
├── didl_builder.py      # Builds DIDL-Lite XML metadata for track/album info
├── install-service.sh   # Installs systemd services for autostart on Pi
├── services/
│   ├── cr200-bridge.service           # Systemd unit for the Python bridge
│   └── node-sonos-http-api.service    # Systemd unit for Node.js API
├── config.json          # Runtime config written by setup.py (gitignored)
├── logs/bridge.log      # Runtime log file (gitignored)
├── README.md            # End-user guide
└── CLAUDE.md            # This file
```

---

## Build & Run

### Prerequisites

```bash
# Install node-sonos-http-api (Node.js required)
npm install -g https://github.com/jishi/node-sonos-http-api

# Start it (keep running in background or as a service)
node /usr/local/lib/node_modules/sonos-http-api/server.js
```

### First-time setup

```bash
python3 setup.py      # Interactive wizard; writes config.json
```

### Run the bridge

```bash
python3 main.py       # Starts SSDP, UPnP, S1 monitor, and status UI
```

Requires elevated privileges on Linux if using port 1400 (< 1024):

```bash
sudo python3 main.py
```

### Install as systemd services (Raspberry Pi)

```bash
sudo bash install-service.sh   # Substitutes paths from config.json into unit files
sudo systemctl enable cr200-bridge node-sonos-http-api
sudo systemctl start cr200-bridge
```

---

## Configuration

Configuration lives in `config.json` (written by `setup.py`). The file is gitignored. `config.py` merges it with these defaults at import time:

| Key | Default | Description |
|-----|---------|-------------|
| `sonos_http_api_base` | `"http://localhost:5005"` | URL of node-sonos-http-api |
| `s1_room_name` | `""` | Room name of the S1 device in node-sonos-http-api |
| `s2_room_name` | `""` | Room name of the target S2 speaker |
| `poll_interval` | `1.0` | Seconds between S1 state polls |
| `uuid` | auto-generated | Stable UUID advertised to the CR200 |
| `household_id` | auto-discovered | Sonos household ID |
| `friendly_name` | `"CR200 Bridge"` | Name shown on CR200 display |
| `http_port` | `1400` | UPnP HTTP server port |
| `status_port` | `8080` | Web UI port |
| `log_level` | `"INFO"` | Logging verbosity (DEBUG/INFO/WARNING/ERROR) |

---

## Code Conventions

### Style
- Module-level docstrings explain purpose and usage for every file.
- Class-based architecture; each server runs in its own daemon thread.
- No external libraries — use stdlib only (`socket`, `threading`, `urllib`, `http.server`, `xml.etree.ElementTree`, `json`, `logging`, `subprocess`).
- Type hints are used inconsistently; don't add them retroactively unless changing the function.

### Architecture patterns
- **Daemon threads** for long-running servers; main thread blocks on `signal.pause()` or `Event.wait()`.
- **Polling** (`s1_monitor.py`): periodic HTTP calls to detect CR200 state changes.
- **Proxy**: `soap_handler.py` parses incoming SOAP XML and translates to node-sonos-http-api REST calls.
- **Shared state**: `SonosClient` is the central room-discovery and control hub; pass it as a dependency.

### Logging
- Logging is configured once in `main.py` (stdout + `logs/bridge.log`).
- Use the module-level logger: `logger = logging.getLogger(__name__)`.
- Do not call `logging.basicConfig()` in submodules.

### Error handling
- `sonos_client.py` helper `_get()` returns `None` on HTTP errors — callers must null-check.
- Log warnings for expected-but-recoverable failures (e.g., room not found); log errors for unexpected exceptions.
- Do not catch broad `Exception` silently.

### XML / SOAP
- Parse SOAP requests with `xml.etree.ElementTree`; never use regex for XML.
- Build response bodies with string templates, not DOM construction — keep it readable.
- Use `html.escape()` for any user-facing string inserted into XML/DIDL-Lite.

### Ports
- Port 1400: UPnP/SOAP — requires sudo on Linux (port < 1024).
- Port 1900 UDP: SSDP multicast (`239.255.255.250`).
- Port 5005: node-sonos-http-api (local only).
- Port 8080: Status web UI.

---

## Testing Status

> **WARNING: This project has not been fully tested yet.**

All code should be considered **unverified** until validated against real hardware.

### Hardware Requirements

- **S1 device** (one of): Sonos Bridge, Connect, Connect:Amp, Play:1 Gen 1, Play:3 Gen 1, Play:5 Gen 1, PLAYBAR
- **S2 speaker** (one of): Era 100, Era 300, Arc, Beam Gen 2, Five, Move 2, or any current-generation Sonos speaker
- **CR200 remote** with SonosNet connectivity to the S1 device
- **Bridge host**: Raspberry Pi (recommended, wired Ethernet) or macOS/Linux machine

### Network Requirements

- All devices on the same LAN subnet (no VLAN boundaries without multicast routing)
- Multicast to `239.255.255.250:1900` (SSDP) must not be filtered by the router or switch
- If VLANs are in use, configure `avahi-daemon` reflector mode or `udp-proxy-2020`
- At least one wired Sonos speaker must have SonosNet enabled

### What Still Needs Testing

- [ ] End-to-end CR200 ContentDirectory browse (Spotify, Apple Music, etc.)
- [ ] CR200 search returning results from S2 music services
- [ ] Volume/seek mirroring accuracy
- [ ] Multiple S2 speakers in a group (zone coordinator selection)
- [ ] Bridge restart while CR200 is active (reconnection behaviour)
- [ ] Behaviour when S1 device is temporarily unreachable
- [ ] Pi receiving packets across a managed switch vs. unmanaged switch
- [ ] Any code paths that depend on specific S2 firmware versions

---

## Linting & Formatting

No linter or formatter is currently configured. Follow PEP 8 conventions manually. If you add a linter, update this section and add a config file (e.g., `pyproject.toml`).

---

## CI/CD

No CI/CD pipeline is configured. All validation is manual and requires real hardware. If you add GitHub Actions, update this section.

---

## Git Workflow

### Branch Naming
- Feature branches: `feature/<short-description>`
- Bug fixes: `fix/<short-description>`
- Documentation: `docs/<short-description>`
- AI/Claude branches: `claude/<description>-<session-id>`

### Commit Messages
Write clear, imperative commit messages:
```
Add ContentDirectory proxy for S2 speakers
Fix SSDP announcement interval off-by-one
Update README with macOS troubleshooting steps
```

Avoid vague messages like "fix stuff" or "WIP".

### Push Protocol
Always use:
```bash
git push -u origin <branch-name>
```

On network failure, retry with exponential backoff: 2s → 4s → 8s → 16s (max 4 retries).

### Pull Requests
- Keep PRs focused on a single concern.
- Write a clear description of what changed and why.
- Reference any related issues.

---

## AI Assistant Guidelines

### General Principles
1. **Read before editing**: Always read a file fully before modifying it.
2. **Minimal changes**: Only change what is necessary for the task at hand.
3. **No unnecessary files**: Do not create files unless they are clearly needed.
4. **Security first**: Never introduce command injection, XSS, or other OWASP vulnerabilities — this code runs on a network-connected Pi.
5. **No over-engineering**: Avoid premature abstractions, unused error handling, or speculative features.
6. **Stdlib only**: Do not add external Python dependencies without explicit user approval.

### Before Making Changes
- Understand the existing module's role in the boot sequence (`main.py`) before changing it.
- Check `sonos_client.py` for existing Sonos API wrappers before adding new HTTP calls.
- Verify that SOAP response templates match the UPnP spec; the CR200 is strict about envelope format.

### Commits
- Commit frequently with descriptive messages.
- Do not amend published commits — create new commits instead.
- Never skip commit hooks (`--no-verify`) unless explicitly instructed.

### Risky Operations
Always confirm with the user before:
- Deleting files or branches
- Force-pushing (`git push --force`)
- Changing the UPnP device UUID in config (the CR200 caches it and must be re-paired)
- Modifying systemd service files (affects Pi autostart)
- Changing port numbers (may break CR200 discovery)
