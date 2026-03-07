"""
S1 Monitor

Watches a real S1 Sonos device (Sonos Bridge, Connect, Connect:Amp,
Play:1 Gen 1, Play:3 Gen 1, Play:5 Gen 1, etc.) that the CR200 is paired with.

The CR200 communicates natively with the S1 device over SonosNet — no fake
device or UPnP server needed. This module polls the S1 device's state through
node-sonos-http-api and mirrors CR200-driven changes to the target S2 room.

Synced actions:
  - Play / Pause / Stop
  - Volume changes
  - Mute / Unmute
  - Next / Previous track (detected via queue position change)
"""

import logging
import threading
import time
from typing import Optional

from config import BRIDGE_CONFIG

logger = logging.getLogger(__name__)

# S1 device examples shown in logs and errors
S1_DEVICE_EXAMPLES = (
    "Sonos Bridge, Connect, Connect:Amp, "
    "Play:1 Gen 1, Play:3 Gen 1, Play:5 Gen 1"
)


class S1Monitor:
    """
    Polls the S1 room via SonosClient and mirrors CR200-driven state
    changes to the configured S2 room.

    Usage:
        monitor = S1Monitor(sonos_client, "Bridge", "Living Room")
        monitor.start()
        ...
        monitor.stop()
    """

    def __init__(self, sonos_client, s1_room_name: str, s2_room_name: str):
        self.client = sonos_client
        self.s1_room_name = s1_room_name
        self.s2_room_name = s2_room_name
        self._poll_interval: float = float(BRIDGE_CONFIG.get("poll_interval", 1.0))
        self._last_state: dict = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info(
            f"S1Monitor started — "
            f"watching '{self.s1_room_name}' → mirroring to '{self.s2_room_name}' "
            f"(poll every {self._poll_interval}s)"
        )

    def stop(self):
        self._running = False
        logger.info("S1Monitor stopped")

    # -------------------------------------------------------------------------
    # Poll loop
    # -------------------------------------------------------------------------

    def _poll_loop(self):
        while self._running:
            try:
                state = self._fetch_s1_state()
                if state is not None:
                    self._sync(state)
                    self._last_state = state
                else:
                    if self._last_state:
                        # S1 room disappeared — log once
                        logger.warning(
                            f"S1 room '{self.s1_room_name}' not found. "
                            f"Is the S1 device ({S1_DEVICE_EXAMPLES}) reachable?"
                        )
                    self._last_state = {}
            except Exception as e:
                logger.debug(f"S1Monitor poll error: {e}")
            time.sleep(self._poll_interval)

    # -------------------------------------------------------------------------
    # State fetch
    # -------------------------------------------------------------------------

    def _fetch_s1_state(self) -> Optional[dict]:
        with self.client._lock:
            room = self.client._rooms.get(self.s1_room_name)
        if room is None:
            return None
        room.refresh()
        raw = room.raw_state()
        return {
            "playback_state": raw.get("playbackState", "STOPPED"),
            "volume":         raw.get("volume", 0),
            "muted":          raw.get("muted", False),
            "track_uri":      (raw.get("currentTrack") or {}).get("uri", ""),
            "track_no":       raw.get("trackNo", 1),
        }

    # -------------------------------------------------------------------------
    # Sync: mirror S1 changes to S2
    # -------------------------------------------------------------------------

    def _get_s2_room(self):
        with self.client._lock:
            return self.client._rooms.get(self.s2_room_name)

    def _sync(self, new: dict):
        old = self._last_state
        if not old:
            # First successful poll — establish baseline, don't send commands.
            logger.info(
                f"S1 baseline: state={new['playback_state']} "
                f"vol={new['volume']} track_no={new['track_no']}"
            )
            return

        s2 = self._get_s2_room()
        if s2 is None:
            logger.warning(
                f"S2 room '{self.s2_room_name}' not found — cannot mirror commands. "
                f"Check that node-sonos-http-api can see your S2 speaker."
            )
            return

        # -- Playback state ---------------------------------------------------
        old_ps = old.get("playback_state", "STOPPED")
        new_ps = new.get("playback_state", "STOPPED")
        if new_ps != old_ps:
            logger.info(f"CR200 → S1 playback: {old_ps} → {new_ps} | mirroring to S2")
            if new_ps == "PLAYING":
                s2.play()
            elif new_ps == "PAUSED_PLAYBACK":
                s2.pause()
            elif new_ps == "STOPPED":
                s2.stop()

        # -- Volume -----------------------------------------------------------
        old_vol = old.get("volume", 0)
        new_vol = new.get("volume", 0)
        if new_vol != old_vol:
            logger.info(f"CR200 → S1 volume: {old_vol} → {new_vol} | mirroring to S2")
            s2.set_volume(new_vol)

        # -- Mute -------------------------------------------------------------
        old_mute = old.get("muted", False)
        new_mute = new.get("muted", False)
        if new_mute != old_mute:
            logger.info(f"CR200 → S1 mute: {old_mute} → {new_mute} | mirroring to S2")
            s2.set_mute(new_mute)

        # -- Track navigation (next / previous / seek-to-track) ---------------
        old_no = old.get("track_no", 1)
        new_no = new.get("track_no", 1)
        if new_no != old_no:
            delta = new_no - old_no
            logger.info(
                f"CR200 → S1 track: {old_no} → {new_no} (delta {delta:+d}) "
                f"| mirroring to S2"
            )
            if delta == 1:
                s2.next()
            elif delta == -1:
                s2.previous()
            else:
                # Large jump — seek directly to that track number
                s2.seek_to_track(new_no)
