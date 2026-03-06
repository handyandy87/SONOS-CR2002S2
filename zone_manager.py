"""
Zone Manager
Discovers S2 Sonos speakers on the network using SoCo and maintains
a model of zones/groups that the SOAP handler can query.

Also handles "active speaker" selection — which speaker the CR200
is currently controlling.
"""

import logging
import threading
import time
from typing import Optional
import soco
from soco import SoCo

logger = logging.getLogger(__name__)


class ZoneManager:
    def __init__(self):
        self._speakers: dict[str, SoCo] = {}   # uuid -> SoCo instance
        self._active_uuid: Optional[str] = None
        self._lock = threading.Lock()
        self._running = False
        self._discovery_thread = None

    # -------------------------------------------------------------------------
    # Discovery
    # -------------------------------------------------------------------------

    def start(self):
        self._running = True
        self._discovery_thread = threading.Thread(
            target=self._discovery_loop, daemon=True
        )
        self._discovery_thread.start()
        logger.info("ZoneManager started — discovering speakers...")

    def stop(self):
        self._running = False

    def _discovery_loop(self):
        """Periodically rediscover speakers in case topology changes."""
        while self._running:
            self._discover()
            time.sleep(60)  # Rediscover every 60 seconds

    def _discover(self):
        try:
            discovered = soco.discover(timeout=5)
            if not discovered:
                logger.warning("No Sonos speakers found on network")
                return

            with self._lock:
                self._speakers = {s.uid: s for s in discovered}

            names = [s.player_name for s in discovered]
            logger.info(f"Discovered {len(discovered)} speaker(s): {names}")

            # Auto-select first speaker if none selected
            if self._active_uuid is None and self._speakers:
                first_uuid = next(iter(self._speakers))
                self._active_uuid = first_uuid
                logger.info(
                    f"Auto-selected active speaker: "
                    f"{self._speakers[first_uuid].player_name}"
                )

        except Exception as e:
            logger.error(f"Discovery error: {e}")

    # -------------------------------------------------------------------------
    # Speaker access
    # -------------------------------------------------------------------------

    def get_active_speaker(self) -> Optional[SoCo]:
        with self._lock:
            if self._active_uuid and self._active_uuid in self._speakers:
                return self._speakers[self._active_uuid]
            # Fallback to first available
            if self._speakers:
                return next(iter(self._speakers.values()))
            return None

    def set_active_speaker(self, uuid: str) -> bool:
        with self._lock:
            if uuid in self._speakers:
                self._active_uuid = uuid
                logger.info(f"Active speaker set to: {self._speakers[uuid].player_name}")
                return True
            return False

    def get_all_speakers(self) -> list[SoCo]:
        with self._lock:
            return list(self._speakers.values())

    def get_speaker_list(self) -> list[dict]:
        """Return a serializable list of speakers for the status UI."""
        with self._lock:
            result = []
            for uuid, speaker in self._speakers.items():
                try:
                    vol = speaker.volume
                    info = speaker.get_current_transport_info()
                    state = info.get("current_transport_state", "UNKNOWN")
                except Exception:
                    vol = 0
                    state = "UNKNOWN"
                result.append({
                    "uuid": uuid,
                    "name": speaker.player_name,
                    "ip": speaker.ip_address,
                    "volume": vol,
                    "state": state,
                    "active": uuid == self._active_uuid,
                })
            return result

    # -------------------------------------------------------------------------
    # Zone topology (for ZoneGroupTopology SOAP responses)
    # -------------------------------------------------------------------------

    def get_all_zones(self) -> list[dict]:
        """
        Build a zone topology structure from discovered speakers.
        Groups speakers by their coordinator (i.e. who's leading a group).
        """
        with self._lock:
            zones: dict[str, dict] = {}

            for uuid, speaker in self._speakers.items():
                try:
                    coordinator = speaker.group.coordinator
                    coord_uuid = coordinator.uid
                except Exception:
                    coord_uuid = uuid
                    coordinator = speaker

                if coord_uuid not in zones:
                    zones[coord_uuid] = {
                        "coordinator_uuid": coord_uuid,
                        "members": []
                    }

                zones[coord_uuid]["members"].append({
                    "uuid": uuid,
                    "name": speaker.player_name,
                    "ip": speaker.ip_address,
                })

            return list(zones.values())

    def force_rediscover(self):
        """Trigger an immediate rediscovery (called from status API)."""
        threading.Thread(target=self._discover, daemon=True).start()
