"""
Status Server
Serves a web UI on a separate port (default 8080) with:
  - Bridge health / uptime
  - Discovered rooms (S1 + S2)
  - Active S2 room selection
  - Playback controls — play, pause, next, previous, volume
  - Sonos Favorites and Playlists browser
  - Music services browser + search (Spotify, Apple Music, etc.)
  - Recent command log
  - Manual rediscovery trigger
"""

import threading
import logging
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from config import BRIDGE_CONFIG

logger = logging.getLogger(__name__)

# Circular buffer of recent commands for the UI
_command_log: list[dict] = []
_command_log_lock = threading.Lock()
MAX_LOG_ENTRIES = 50

def log_command(action: str, params: dict, speaker: str):
    with _command_log_lock:
        _command_log.append({
            "time": time.strftime("%H:%M:%S"),
            "action": action,
            "params": params,
            "speaker": speaker,
        })
        if len(_command_log) > MAX_LOG_ENTRIES:
            _command_log.pop(0)


STATUS_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CR200 Bridge</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f0f; color: #e0e0e0; padding: 24px; }
  h1 { font-size: 1.4rem; font-weight: 600; margin-bottom: 4px; color: #fff; }
  .subtitle { font-size: 0.85rem; color: #666; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }
  .card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px;
          padding: 16px; margin-bottom: 16px; }
  .card h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em;
              color: #555; margin-bottom: 12px; }
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
                margin-right: 6px; }
  .dot-green { background: #22c55e; }
  .dot-yellow { background: #eab308; }
  .dot-red { background: #ef4444; }
  .speaker { display: flex; align-items: center; justify-content: space-between;
             padding: 10px 12px; background: #111; border-radius: 8px; margin-bottom: 8px;
             border: 1px solid #222; cursor: pointer; transition: border-color 0.15s; }
  .speaker:hover { border-color: #444; }
  .speaker.active { border-color: #3b82f6; background: #0d1a2e; }
  .speaker-name { font-size: 0.9rem; font-weight: 500; }
  .speaker-meta { font-size: 0.75rem; color: #666; margin-top: 2px; }
  .badge { font-size: 0.65rem; padding: 2px 7px; border-radius: 4px; font-weight: 600;
           text-transform: uppercase; letter-spacing: 0.05em; }
  .badge-play  { background: #14532d; color: #4ade80; }
  .badge-pause { background: #1c1c00; color: #facc15; }
  .badge-stop  { background: #1f1f1f; color: #555; }
  /* Playback controls */
  .controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
  .ctrl-btn { background: #222; border: 1px solid #333; color: #ccc; border-radius: 7px;
              padding: 8px 16px; font-size: 1rem; cursor: pointer; transition: background 0.12s; }
  .ctrl-btn:hover { background: #2e2e2e; }
  .ctrl-btn.primary { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
  .ctrl-btn.primary:hover { background: #2563eb; }
  .vol-row { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
  .vol-row input[type=range] { flex: 1; accent-color: #3b82f6; }
  .vol-label { font-size: 0.8rem; color: #666; min-width: 36px; text-align: right; }
  /* Tabs */
  .tab-row { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
  .tab { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 6px;
         padding: 5px 12px; font-size: 0.78rem; cursor: pointer; color: #888; }
  .tab.active { background: #1d4ed8; border-color: #1d4ed8; color: #fff; }
  /* Media items */
  .media-item { display: flex; align-items: center; justify-content: space-between;
                padding: 8px 10px; background: #111; border-radius: 7px; margin-bottom: 6px;
                border: 1px solid #222; gap: 8px; }
  .media-item-title { font-size: 0.85rem; flex: 1; }
  .media-item-meta  { font-size: 0.72rem; color: #666; }
  .play-btn { background: #14532d; color: #4ade80; border: none; border-radius: 5px;
              padding: 4px 10px; font-size: 0.78rem; cursor: pointer; flex-shrink: 0; }
  .play-btn:hover { background: #166534; }
  /* Search */
  .search-row { display: flex; gap: 8px; margin-bottom: 12px; }
  .search-row input { flex: 1; background: #111; border: 1px solid #333; color: #e0e0e0;
                      border-radius: 6px; padding: 7px 10px; font-size: 0.85rem; }
  .search-row input:focus { outline: none; border-color: #3b82f6; }
  .search-row button { background: #1d4ed8; color: #fff; border: none; border-radius: 6px;
                       padding: 7px 14px; font-size: 0.85rem; cursor: pointer; }
  .service-select { background: #111; border: 1px solid #333; color: #e0e0e0;
                    border-radius: 6px; padding: 7px 10px; font-size: 0.85rem; }
  /* Log */
  .log-entry { font-size: 0.78rem; padding: 6px 0; border-bottom: 1px solid #1f1f1f;
               display: flex; gap: 10px; }
  .log-time   { color: #444; min-width: 56px; }
  .log-action { color: #60a5fa; min-width: 160px; }
  .log-speaker{ color: #a78bfa; }
  .btn { display: inline-block; padding: 8px 14px; border-radius: 7px; border: none;
         font-size: 0.82rem; cursor: pointer; font-weight: 500; margin-top: 12px; }
  .btn-primary { background: #1d4ed8; color: #fff; }
  .btn-primary:hover { background: #2563eb; }
  .stat { display: flex; justify-content: space-between; padding: 6px 0;
          border-bottom: 1px solid #1f1f1f; font-size: 0.85rem; }
  .stat-val { color: #60a5fa; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<h1>&#128266; CR200 Bridge</h1>
<p class="subtitle">CR200 &rarr; S1 device &rarr; S2 Translation Bridge</p>

<div class="grid">
  <div class="card" style="margin-bottom:0">
    <h2>Bridge Status</h2>
    <div id="bridge-status">Loading...</div>
    <button class="btn btn-primary" onclick="rediscover()">&#8635; Rediscover Rooms</button>
  </div>
  <div class="card" style="margin-bottom:0">
    <h2>Rooms (S1 + S2)</h2>
    <div id="speakers">Loading...</div>
  </div>
</div>

<div class="card">
  <h2>Playback Controls &mdash; Active S2 Room</h2>
  <div id="now-playing" style="font-size:0.85rem;color:#888;margin-bottom:10px">
    Select a room above to control it.
  </div>
  <div class="controls">
    <button class="ctrl-btn" onclick="cmd('previous')" title="Previous">&#9664;&#9664;</button>
    <button class="ctrl-btn primary" onclick="cmd('playpause')" title="Play/Pause">&#9654;&#10073;&#10073;</button>
    <button class="ctrl-btn" onclick="cmd('next')" title="Next">&#9654;&#9654;</button>
    <button class="ctrl-btn" onclick="cmd('stop')" title="Stop">&#9632;</button>
  </div>
  <div class="vol-row">
    <span style="font-size:0.8rem;color:#666">Vol</span>
    <input type="range" id="vol-slider" min="0" max="100" value="0"
           oninput="document.getElementById('vol-label').textContent=this.value"
           onchange="setVol(this.value)">
    <span class="vol-label" id="vol-label">0</span>
  </div>
</div>

<div class="card">
  <h2>Music</h2>
  <div class="tab-row">
    <button class="tab active" id="tab-fav"  onclick="showTab('fav')">Favorites</button>
    <button class="tab"        id="tab-pl"   onclick="showTab('pl')">Playlists</button>
    <button class="tab"        id="tab-svc"  onclick="showTab('svc')">Services</button>
  </div>

  <!-- Favorites & Playlists list -->
  <div id="media-list"></div>

  <!-- Services search (hidden until "Services" tab active) -->
  <div id="svc-panel" style="display:none">
    <div class="search-row">
      <select class="service-select" id="svc-select">
        <option value="spotify">Spotify</option>
        <option value="apple">Apple Music</option>
        <option value="tidal">Tidal</option>
        <option value="library">Local Library</option>
      </select>
      <input type="text" id="svc-query" placeholder="Search songs, artists, albums&hellip;"
             onkeydown="if(event.key==='Enter') searchService()">
      <button onclick="searchService()">Search</button>
    </div>
    <div id="svc-results"></div>
  </div>
</div>

<div class="card">
  <h2>Recent Commands</h2>
  <div id="command-log">Loading...</div>
</div>

<script>
let activeRoom = null;
let currentTab = 'fav';

// ---- Status polling ----

async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const data = await r.json();
    renderStatus(data);
  } catch(e) {}
}

function stateDot(s) {
  if (s === 'PLAYING')         return '<span class="status-dot dot-green"></span>';
  if (s === 'PAUSED_PLAYBACK') return '<span class="status-dot dot-yellow"></span>';
  return '<span class="status-dot dot-red"></span>';
}

function stateBadge(s) {
  if (s === 'PLAYING')         return '<span class="badge badge-play">Playing</span>';
  if (s === 'PAUSED_PLAYBACK') return '<span class="badge badge-pause">Paused</span>';
  return '<span class="badge badge-stop">' + (s || 'Stopped') + '</span>';
}

function renderStatus(data) {
  document.getElementById('bridge-status').innerHTML = `
    <div class="stat"><span>Uptime</span><span class="stat-val">${data.uptime}</span></div>
    <div class="stat"><span>Commands handled</span><span class="stat-val">${data.command_count}</span></div>
    <div class="stat"><span>Rooms found</span><span class="stat-val">${data.speakers.length}</span></div>
    <div class="stat"><span>Poll interval</span><span class="stat-val">${data.poll_interval}s</span></div>
  `;

  const speakersEl = document.getElementById('speakers');
  if (!data.speakers.length) {
    speakersEl.innerHTML = '<p style="color:#666;font-size:0.85rem">No rooms found. Try rediscover.</p>';
  } else {
    speakersEl.innerHTML = data.speakers.map(s => `
      <div class="speaker ${s.active ? 'active' : ''}" onclick="setActive('${s.name}')">
        <div style="display:flex;align-items:center;gap:10px">
          ${s.artwork ? `<img src="${s.artwork}" style="width:40px;height:40px;border-radius:4px;object-fit:cover" onerror="this.style.display='none'">` : ''}
          <div>
            <div class="speaker-name">${stateDot(s.state)}${s.name}</div>
            <div class="speaker-meta">${s.track ? s.track + (s.artist ? ' \u2014 ' + s.artist : '') : 'Nothing playing'} &middot; Vol ${s.volume}</div>
          </div>
        </div>
        ${stateBadge(s.state)}
      </div>
    `).join('');

    const active = data.speakers.find(s => s.active);
    if (active) {
      activeRoom = active.name;
      const slider = document.getElementById('vol-slider');
      const label  = document.getElementById('vol-label');
      if (document.activeElement !== slider) {
        slider.value    = active.volume;
        label.textContent = active.volume;
      }
      const np = active.track
        ? `<strong>${active.track}</strong>${active.artist ? ' &mdash; ' + active.artist : ''} &middot; Vol ${active.volume}`
        : 'Nothing playing';
      document.getElementById('now-playing').innerHTML =
        `<em>${active.name}</em> &nbsp; ${np}`;
    }
  }

  const logEl = document.getElementById('command-log');
  if (!data.log.length) {
    logEl.innerHTML = '<p style="color:#666;font-size:0.85rem">No commands received yet.</p>';
  } else {
    logEl.innerHTML = [...data.log].reverse().map(e => `
      <div class="log-entry">
        <span class="log-time">${e.time}</span>
        <span class="log-action">${e.action}</span>
        <span class="log-speaker">${e.speaker}</span>
      </div>
    `).join('');
  }
}

// ---- Room / controls ----

async function setActive(name) {
  await fetch('/api/set-active', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name})
  });
  fetchStatus();
}

async function rediscover() {
  await fetch('/api/rediscover', { method: 'POST' });
  setTimeout(fetchStatus, 3000);
}

async function cmd(action) {
  if (!activeRoom) return;
  await fetch('/api/control', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room: activeRoom, action})
  });
  setTimeout(fetchStatus, 600);
}

async function setVol(vol) {
  if (!activeRoom) return;
  await fetch('/api/control', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room: activeRoom, action: 'volume', value: parseInt(vol)})
  });
}

// ---- Music browser ----

function showTab(tab) {
  currentTab = tab;
  ['fav','pl','svc'].forEach(t => {
    document.getElementById('tab-' + t).className = 'tab' + (t === tab ? ' active' : '');
  });
  document.getElementById('media-list').style.display = tab !== 'svc' ? '' : 'none';
  document.getElementById('svc-panel').style.display  = tab === 'svc' ? '' : 'none';
  if (tab !== 'svc') loadMedia();
}

async function loadMedia() {
  const endpoint = currentTab === 'fav' ? '/api/favorites' : '/api/playlists';
  const el = document.getElementById('media-list');
  el.innerHTML = '<p style="color:#666;font-size:0.85rem">Loading\u2026</p>';
  try {
    const r = await fetch(endpoint);
    const items = await r.json();
    if (!items.length) {
      el.innerHTML = '<p style="color:#666;font-size:0.85rem">None found.</p>';
      return;
    }
    el.innerHTML = items.map((item, i) => `
      <div class="media-item">
        <div>
          <div class="media-item-title">${item.title || item.name || '(untitled)'}</div>
          ${item.type ? `<div class="media-item-meta">${item.type}</div>` : ''}
        </div>
        <button class="play-btn" onclick="playMedia('${currentTab}', ${i})">&#9654; Play</button>
      </div>
    `).join('');
  } catch(e) {
    el.innerHTML = '<p style="color:#666;font-size:0.85rem">Error loading.</p>';
  }
}

async function playMedia(type, index) {
  if (!activeRoom) { alert('Select a room first.'); return; }
  await fetch('/api/play-media', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room: activeRoom, type, index})
  });
  setTimeout(fetchStatus, 1000);
}

// ---- Music service search ----

async function searchService() {
  const service = document.getElementById('svc-select').value;
  const query   = document.getElementById('svc-query').value.trim();
  if (!query) return;
  if (!activeRoom) { alert('Select a room first.'); return; }

  const el = document.getElementById('svc-results');
  el.innerHTML = '<p style="color:#666;font-size:0.85rem">Searching\u2026</p>';

  try {
    const r = await fetch('/api/search', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({room: activeRoom, service, query})
    });
    const items = await r.json();
    if (!items.length) {
      el.innerHTML = '<p style="color:#666;font-size:0.85rem">No results.</p>';
      return;
    }
    el.innerHTML = items.map((item, i) => `
      <div class="media-item">
        <div>
          <div class="media-item-title">${item.title || item.name || item.track || '(untitled)'}</div>
          <div class="media-item-meta">${[item.artist, item.album].filter(Boolean).join(' &middot; ')}</div>
        </div>
        <button class="play-btn"
          onclick='playSearchResult(${JSON.stringify(JSON.stringify(item))})'>&#9654; Play</button>
      </div>
    `).join('');
  } catch(e) {
    el.innerHTML = '<p style="color:#666;font-size:0.85rem">Search error.</p>';
  }
}

async function playSearchResult(itemJson) {
  if (!activeRoom) { alert('Select a room first.'); return; }
  const item = JSON.parse(itemJson);
  await fetch('/api/play-uri', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({room: activeRoom, uri: item.uri || '', metadata: item.metadata || ''})
  });
  setTimeout(fetchStatus, 1000);
}

fetchStatus();
loadMedia();
setInterval(fetchStatus, 3000);
</script>
</body>
</html>"""


class StatusRequestHandler(BaseHTTPRequestHandler):
    zone_manager = None
    start_time = time.time()
    command_count = 0

    def log_message(self, format, *args):
        pass  # Suppress access logs for status server

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_html()
        elif path == "/api/status":
            self._serve_status_json()
        elif path == "/api/favorites":
            self._json_response(self.zone_manager.get_favorites())
        elif path == "/api/playlists":
            self._json_response(self.zone_manager.get_playlists())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body) if body else {}

        if path == "/api/set-active":
            key = data.get("name") or data.get("uuid", "")
            success = (
                self.zone_manager.set_active_room(key)
                if hasattr(self.zone_manager, "set_active_room")
                else self.zone_manager.set_active_speaker(key)
            )
            self._json_response({"success": success})

        elif path == "/api/rediscover":
            self.zone_manager.force_rediscover()
            self._json_response({"triggered": True})

        elif path == "/api/control":
            self._handle_control(data)

        elif path == "/api/play-media":
            self._handle_play_media(data)

        elif path == "/api/search":
            self._handle_search(data)

        elif path == "/api/play-uri":
            self._handle_play_uri(data)

        else:
            self.send_response(404)
            self.end_headers()

    # -------------------------------------------------------------------------
    # Playback control
    # -------------------------------------------------------------------------

    def _handle_control(self, data: dict):
        room = self._get_room(data.get("room", ""))
        if room is None:
            self._json_response({"error": "room not found"})
            return

        action = data.get("action", "")
        if action == "play":            room.play()
        elif action == "pause":         room.pause()
        elif action == "playpause":     room.toggle_playback()
        elif action == "stop":          room.stop()
        elif action == "next":          room.next()
        elif action == "previous":      room.previous()
        elif action == "volume":        room.set_volume(int(data.get("value", 0)))
        elif action == "mute":          room.set_mute(True)
        elif action == "unmute":        room.set_mute(False)

        StatusRequestHandler.command_count += 1
        log_command(f"UI:{action}", {}, data.get("room", ""))
        self._json_response({"ok": True})

    # -------------------------------------------------------------------------
    # Play Favorites / Playlists
    # -------------------------------------------------------------------------

    def _handle_play_media(self, data: dict):
        room = self._get_room(data.get("room", ""))
        if room is None:
            self._json_response({"error": "room not found"})
            return

        media_type = data.get("type", "fav")
        index = int(data.get("index", 0))

        if media_type == "fav":
            items = self.zone_manager.get_favorites()
            if 0 <= index < len(items):
                name = items[index].get("title") or items[index].get("name", "")
                room.play_favorite(name)
                log_command("UI:play-fav", {"name": name}, data.get("room", ""))
        elif media_type == "pl":
            items = self.zone_manager.get_playlists()
            if 0 <= index < len(items):
                name = items[index].get("title") or items[index].get("name", "")
                room.play_playlist(name)
                log_command("UI:play-playlist", {"name": name}, data.get("room", ""))

        StatusRequestHandler.command_count += 1
        self._json_response({"ok": True})

    # -------------------------------------------------------------------------
    # Music service search
    # -------------------------------------------------------------------------

    def _handle_search(self, data: dict):
        room_name = data.get("room", "")
        service   = data.get("service", "spotify")
        query     = data.get("query", "")

        if not query:
            self._json_response([])
            return

        results = self.zone_manager.search(room_name, service, query)
        self._json_response(results)

    # -------------------------------------------------------------------------
    # Play a URI directly (from search results)
    # -------------------------------------------------------------------------

    def _handle_play_uri(self, data: dict):
        room = self._get_room(data.get("room", ""))
        if room is None:
            self._json_response({"error": "room not found"})
            return

        uri      = data.get("uri", "")
        metadata = data.get("metadata", "")
        if uri:
            room.play_uri(uri, metadata)
            log_command("UI:play-uri", {"uri": uri[:80]}, data.get("room", ""))
            StatusRequestHandler.command_count += 1

        self._json_response({"ok": True})

    # -------------------------------------------------------------------------
    # Status JSON
    # -------------------------------------------------------------------------

    def _serve_status_json(self):
        uptime_sec = int(time.time() - self.start_time)
        h, rem = divmod(uptime_sec, 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

        with _command_log_lock:
            log_copy = list(_command_log)

        data = {
            "uptime": uptime_str,
            "command_count": StatusRequestHandler.command_count,
            "poll_interval": BRIDGE_CONFIG.get("poll_interval", 1.0),
            "speakers": self.zone_manager.get_room_list(),
            "log": log_copy,
        }
        self._json_response(data)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_room(self, room_name: str):
        with self.zone_manager._lock:
            return self.zone_manager._rooms.get(room_name)

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(STATUS_HTML.encode())

    def _json_response(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class StatusServer:
    def __init__(self, sonos_client):
        StatusRequestHandler.zone_manager = sonos_client
        StatusRequestHandler.start_time = time.time()
        self._server = None
        self._thread = None

    def start(self):
        self._server = HTTPServer(
            ("0.0.0.0", BRIDGE_CONFIG["status_port"]),
            StatusRequestHandler,
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"Status UI available at http://localhost:{BRIDGE_CONFIG['status_port']}")

    def stop(self):
        if self._server:
            self._server.shutdown()
