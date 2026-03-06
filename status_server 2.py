"""
Status Server
Serves a simple web UI on a separate port (default 8080) showing:
  - Bridge health / uptime
  - Discovered S2 speakers
  - Active speaker selection
  - Recent SOAP command log
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


STATUS_HTML = """<!DOCTYPE html>
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
  .card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; padding: 16px; }
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
  .badge-play { background: #14532d; color: #4ade80; }
  .badge-pause { background: #1c1c00; color: #facc15; }
  .badge-stop { background: #1f1f1f; color: #555; }
  .log-entry { font-size: 0.78rem; padding: 6px 0; border-bottom: 1px solid #1f1f1f;
               display: flex; gap: 10px; }
  .log-time { color: #444; min-width: 56px; }
  .log-action { color: #60a5fa; min-width: 160px; }
  .log-speaker { color: #a78bfa; }
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
<h1>🔊 CR200 Bridge</h1>
<p class="subtitle">Sonos CR200 → S2 Translation Layer</p>

<div class="grid">
  <div class="card">
    <h2>Bridge Status</h2>
    <div id="bridge-status">Loading...</div>
    <button class="btn btn-primary" onclick="rediscover()">↺ Rediscover Speakers</button>
  </div>
  <div class="card">
    <h2>S2 Speakers</h2>
    <div id="speakers">Loading...</div>
  </div>
</div>

<div class="card">
  <h2>Recent Commands</h2>
  <div id="command-log">Loading...</div>
</div>

<script>
async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const data = await r.json();
    renderStatus(data);
  } catch(e) {}
}

function stateDot(state) {
  if (state === 'PLAYING') return '<span class="status-dot dot-green"></span>';
  if (state === 'PAUSED_PLAYBACK') return '<span class="status-dot dot-yellow"></span>';
  return '<span class="status-dot dot-red"></span>';
}

function stateBadge(state) {
  if (state === 'PLAYING') return '<span class="badge badge-play">Playing</span>';
  if (state === 'PAUSED_PLAYBACK') return '<span class="badge badge-pause">Paused</span>';
  return '<span class="badge badge-stop">' + (state || 'Stopped') + '</span>';
}

function renderStatus(data) {
  // Bridge stats
  document.getElementById('bridge-status').innerHTML = `
    <div class="stat"><span>Uptime</span><span class="stat-val">${data.uptime}</span></div>
    <div class="stat"><span>Commands handled</span><span class="stat-val">${data.command_count}</span></div>
    <div class="stat"><span>Speakers found</span><span class="stat-val">${data.speakers.length}</span></div>
    <div class="stat"><span>UPnP port</span><span class="stat-val">${data.upnp_port}</span></div>
  `;

  // Speakers
  const speakersEl = document.getElementById('speakers');
  if (data.speakers.length === 0) {
    speakersEl.innerHTML = '<p style="color:#666;font-size:0.85rem">No speakers found. Try rediscover.</p>';
  } else {
    speakersEl.innerHTML = data.speakers.map(s => `
      <div class="speaker ${s.active ? 'active' : ''}" onclick="setActive('${s.name}')">
        <div style="display:flex;align-items:center;gap:10px">
          ${s.artwork ? `<img src="${s.artwork}" style="width:40px;height:40px;border-radius:4px;object-fit:cover" onerror="this.style.display='none'">` : ''}
          <div>
            <div class="speaker-name">${stateDot(s.state)}${s.name}</div>
            <div class="speaker-meta">${s.track ? `${s.track}${s.artist ? ' — ' + s.artist : ''}` : 'Nothing playing'} · Vol ${s.volume}</div>
          </div>
        </div>
        ${stateBadge(s.state)}
      </div>
    `).join('');
  }

  // Command log
  const logEl = document.getElementById('command-log');
  if (data.log.length === 0) {
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

async function setActive(name) {
  await fetch('/api/set-active', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name})
  });
  fetchStatus();
}

async function rediscover() {
  await fetch('/api/rediscover', { method: 'POST' });
  setTimeout(fetchStatus, 3000);
}

fetchStatus();
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
        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/status":
            self._serve_status_json()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if path == "/api/set-active":
            data = json.loads(body)
            # SonosClient uses room name; fall back to uuid for compat
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
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(STATUS_HTML.encode())

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
            "upnp_port": BRIDGE_CONFIG["http_port"],
            "speakers": self.zone_manager.get_speaker_list(),
            "log": log_copy,
        }
        self._json_response(data)

    def _json_response(self, data: dict):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class StatusServer:
    def __init__(self, sonos_client):
        StatusRequestHandler.zone_manager = sonos_client  # duck-typed: get_room_list, set_active_speaker->set_active_room, force_rediscover
        StatusRequestHandler.start_time = time.time()
        self._server = None
        self._thread = None

    def start(self):
        self._server = HTTPServer(("0.0.0.0", BRIDGE_CONFIG["status_port"]), StatusRequestHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"Status UI available at http://localhost:{BRIDGE_CONFIG['status_port']}")

    def stop(self):
        if self._server:
            self._server.shutdown()
