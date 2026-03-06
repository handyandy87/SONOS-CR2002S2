"""
Sonos HTTP API Client
Wraps node-sonos-http-api (https://github.com/jishi/node-sonos-http-api)
running locally, giving us access to:
  - Full playback control
  - Rich now-playing metadata (title, artist, album, artwork URL)
  - Music service browsing (Spotify, Apple Music, etc.) via the speaker's
    own authenticated SMAPI client — no re-auth needed
  - Search across services
  - Favorites, playlists, queues

node-sonos-http-api must be running before the bridge starts.
Default: http://localhost:5005

Setup:
  npm install -g node-sonos-http-api
  node-sonos-http-api
  # or: npx node-sonos-http-api
"""

import logging
import urllib.request
import urllib.parse
import urllib.error
import json
import threading
import time
from typing import Optional
from config import BRIDGE_CONFIG

logger = logging.getLogger(__name__)

API_BASE = BRIDGE_CONFIG.get("sonos_http_api_base", "http://localhost:5005")


def _get(path: str, timeout: float = 4.0) -> Optional[dict | list]:
    url = f"{API_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        logger.warning(f"HTTP {e.code} from {url}")
    except urllib.error.URLError as e:
        logger.error(f"Cannot reach node-sonos-http-api at {url}: {e.reason}")
    except Exception as e:
        logger.error(f"GET {url} failed: {e}")
    return None


def _get_raw(path: str, timeout: float = 4.0) -> Optional[str]:
    url = f"{API_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        logger.error(f"GET {url} failed: {e}")
    return None


class SonosRoom:
    """
    Represents a single Sonos room/zone as exposed by node-sonos-http-api.
    All playback commands are scoped to this room.
    """

    def __init__(self, name: str, state: dict):
        self.name = name
        self._state = state

    # -- Identity --------------------------------------------------------------

    @property
    def uuid(self) -> str:
        return self._state.get("uuid", "")

    @property
    def coordinator(self) -> str:
        return self._state.get("coordinator", self.name)

    # -- Playback state --------------------------------------------------------

    @property
    def playback_state(self) -> str:
        """Returns PLAYING, PAUSED_PLAYBACK, or STOPPED."""
        raw = self._state.get("playbackState", "STOPPED")
        # node-sonos uses "PLAYING", "PAUSED_PLAYBACK", "STOPPED"
        return raw

    @property
    def volume(self) -> int:
        return self._state.get("volume", 0)

    @property
    def mute(self) -> bool:
        return self._state.get("muted", False)

    # -- Current track ---------------------------------------------------------

    @property
    def current_track(self) -> dict:
        return self._state.get("currentTrack", {})

    @property
    def track_title(self) -> str:
        return self.current_track.get("title", "")

    @property
    def track_artist(self) -> str:
        return self.current_track.get("artist", "")

    @property
    def track_album(self) -> str:
        return self.current_track.get("album", "")

    @property
    def track_duration(self) -> int:
        """Duration in seconds."""
        return self.current_track.get("duration", 0)

    @property
    def track_position(self) -> int:
        """Current position in seconds."""
        return self._state.get("elapsedTime", 0)

    @property
    def track_uri(self) -> str:
        return self.current_track.get("uri", "")

    @property
    def artwork_url(self) -> str:
        """
        Absolute URL to album art. node-sonos-http-api provides this
        either as a full URL (streaming service) or a relative path
        served through its own proxy (local library / radio).
        """
        art = self.current_track.get("absoluteAlbumArtUri", "")
        if not art:
            art = self.current_track.get("albumArtUri", "")
        if art and art.startswith("/"):
            art = f"{API_BASE}{art}"
        return art

    @property
    def next_track(self) -> dict:
        return self._state.get("nextTrack", {})

    @property
    def play_mode(self) -> dict:
        return self._state.get("playMode", {})

    @property
    def queue_position(self) -> int:
        return self._state.get("trackNo", 1)

    # -- Commands --------------------------------------------------------------

    def play(self):           _get(f"/{_enc(self.name)}/play")
    def pause(self):          _get(f"/{_enc(self.name)}/pause")
    def stop(self):           _get(f"/{_enc(self.name)}/stop")
    def next(self):           _get(f"/{_enc(self.name)}/next")
    def previous(self):       _get(f"/{_enc(self.name)}/previous")
    def toggle_playback(self):_get(f"/{_enc(self.name)}/playpause")

    def set_volume(self, vol: int):
        vol = max(0, min(100, vol))
        _get(f"/{_enc(self.name)}/volume/{vol}")

    def set_mute(self, muted: bool):
        _get(f"/{_enc(self.name)}/mute" if muted else f"/{_enc(self.name)}/unmute")

    def seek(self, seconds: int):
        _get(f"/{_enc(self.name)}/seek/{seconds}")

    def seek_to_track(self, track_num: int):
        _get(f"/{_enc(self.name)}/trackseek/{track_num}")

    def set_repeat(self, mode: str):
        # mode: none | all | one
        _get(f"/{_enc(self.name)}/repeat/{mode}")

    def set_shuffle(self, on: bool):
        _get(f"/{_enc(self.name)}/shuffle/{'on' if on else 'off'}")

    def play_favorite(self, name: str):
        _get(f"/{_enc(self.name)}/favorite/{_enc(name)}")

    def play_playlist(self, name: str):
        _get(f"/{_enc(self.name)}/playlist/{_enc(name)}")

    def play_uri(self, uri: str, metadata: str = ""):
        encoded_uri = _enc(uri)
        if metadata:
            _get(f"/{_enc(self.name)}/setavtransporturi/{encoded_uri}/{_enc(metadata)}")
        else:
            _get(f"/{_enc(self.name)}/setavtransporturi/{encoded_uri}")
        self.play()

    def queue_uri(self, uri: str):
        _get(f"/{_enc(self.name)}/add/{_enc(uri)}")

    def clear_queue(self):
        _get(f"/{_enc(self.name)}/clearqueue")

    def say(self, text: str, language: str = "en-us"):
        _get(f"/{_enc(self.name)}/say/{_enc(text)}/{language}")

    # -- Queue -----------------------------------------------------------------

    def get_queue(self) -> list[dict]:
        data = _get(f"/{_enc(self.name)}/queue")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("items", [])
        return []

    # -- Refresh state from API ------------------------------------------------

    def refresh(self):
        data = _get(f"/{_enc(self.name)}/state")
        if data:
            self._state = data

    def raw_state(self) -> dict:
        return self._state


def _enc(s: str) -> str:
    return urllib.parse.quote(s, safe="")


class SonosClient:
    """
    Manages the list of rooms/zones from node-sonos-http-api and provides
    a clean interface for the bridge to query and control them.
    """

    def __init__(self):
        self._rooms: dict[str, SonosRoom] = {}
        self._active_room_name: Optional[str] = None
        self._lock = threading.Lock()
        self._running = False
        self._poll_thread = None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self):
        self._running = True
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True
        )
        self._poll_thread.start()
        logger.info("SonosClient started — polling node-sonos-http-api")

    def stop(self):
        self._running = False

    def _poll_loop(self):
        # Initial discovery
        self._discover_rooms()
        while self._running:
            time.sleep(5)
            self._refresh_states()

    # -------------------------------------------------------------------------
    # Discovery
    # -------------------------------------------------------------------------

    def _discover_rooms(self):
        """Fetch room list from /zones endpoint."""
        zones = _get("/zones")
        if not zones:
            logger.warning("Could not reach node-sonos-http-api — is it running?")
            return

        with self._lock:
            new_rooms = {}
            for zone in zones:
                # Each zone has a members list; coordinator is the primary
                coordinator = zone.get("coordinator", {})
                room_name = coordinator.get("roomName", "")
                state = coordinator.get("state", {})
                state["uuid"] = coordinator.get("uuid", "")
                state["coordinator"] = room_name

                # Also include members for topology reporting
                members = []
                for member in zone.get("members", []):
                    members.append({
                        "uuid": member.get("uuid", ""),
                        "name": member.get("roomName", ""),
                        "ip": member.get("ip", ""),
                    })
                state["_members"] = members
                state["_member_ips"] = {
                    m["uuid"]: m["ip"] for m in members
                }

                if room_name:
                    new_rooms[room_name] = SonosRoom(room_name, state)

            self._rooms = new_rooms

            if self._active_room_name is None and new_rooms:
                self._active_room_name = next(iter(new_rooms))
                logger.info(f"Auto-selected room: {self._active_room_name}")

        names = list(new_rooms.keys())
        logger.info(f"Found {len(names)} room(s): {names}")

    def _refresh_states(self):
        """Refresh state of all rooms without full rediscovery."""
        with self._lock:
            rooms_snapshot = dict(self._rooms)

        for name, room in rooms_snapshot.items():
            try:
                room.refresh()
            except Exception as e:
                logger.debug(f"State refresh failed for {name}: {e}")

    # -------------------------------------------------------------------------
    # Room access
    # -------------------------------------------------------------------------

    def get_active_room(self) -> Optional[SonosRoom]:
        with self._lock:
            if self._active_room_name and self._active_room_name in self._rooms:
                return self._rooms[self._active_room_name]
            if self._rooms:
                return next(iter(self._rooms.values()))
            return None

    def set_active_room(self, name: str) -> bool:
        with self._lock:
            if name in self._rooms:
                self._active_room_name = name
                logger.info(f"Active room set to: {name}")
                return True
            return False

    def get_all_rooms(self) -> list[SonosRoom]:
        with self._lock:
            return list(self._rooms.values())

    def get_room_list(self) -> list[dict]:
        """Serializable room list for the status UI."""
        rooms = self.get_all_rooms()
        result = []
        for room in rooms:
            result.append({
                "name": room.name,
                "uuid": room.uuid,
                "state": room.playback_state,
                "volume": room.volume,
                "active": room.name == self._active_room_name,
                "track": room.track_title,
                "artist": room.track_artist,
                "artwork": room.artwork_url,
            })
        return result

    def force_rediscover(self):
        threading.Thread(target=self._discover_rooms, daemon=True).start()

    # -------------------------------------------------------------------------
    # Zone topology (for ZoneGroupTopology SOAP)
    # -------------------------------------------------------------------------

    def get_zone_topology(self) -> list[dict]:
        with self._lock:
            zones = []
            for name, room in self._rooms.items():
                state = room.raw_state()
                members = state.get("_members", [{"uuid": room.uuid, "name": name, "ip": ""}])
                zones.append({
                    "coordinator_uuid": room.uuid,
                    "members": members,
                })
            return zones

    # -------------------------------------------------------------------------
    # Music services / browsing (via node-sonos-http-api)
    # -------------------------------------------------------------------------

    def get_favorites(self) -> list[dict]:
        data = _get("/favorites")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("items", [])
        return []

    def get_playlists(self) -> list[dict]:
        data = _get("/playlists")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("items", [])
        return []

    def search(self, room_name: str, service: str, query: str) -> list[dict]:
        """
        Search a music service. Services supported depend on what's
        configured in node-sonos-http-api (Spotify, Apple Music, etc.)
        """
        data = _get(f"/{_enc(room_name)}/musicsearch/{_enc(service)}/song/{_enc(query)}")
        if isinstance(data, dict):
            return data.get("items", [])
        return []

    def browse_music_service(self, room_name: str, service: str, id: str = "") -> list[dict]:
        path = f"/{_enc(room_name)}/browse/{_enc(service)}"
        if id:
            path += f"/{_enc(id)}"
        data = _get(path)
        if isinstance(data, dict):
            return data.get("items", [])
        if isinstance(data, list):
            return data
        return []
