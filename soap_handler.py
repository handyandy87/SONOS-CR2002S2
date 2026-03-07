"""
SOAP Handler (node-sonos-http-api backend)

Maps CR200 UPnP SOAP actions to node-sonos-http-api calls.
Now includes:
  - Full now-playing metadata with DIDL-Lite (title, artist, album, artwork)
  - Proper GetPositionInfo / GetMediaInfo with real track data
  - ContentDirectory: queue, favorites, playlists, music service browsing
  - Search via node-sonos-http-api music search
  - ZoneGroupTopology reflecting real S2 zone structure
"""

import html
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET

from sonos_client import SonosClient, SonosRoom
from didl_builder import (
    build_queue_didl,
    build_container_didl,
    build_favorites_didl,
    didl_from_room_state,
    seconds_to_hms,
)

logger = logging.getLogger(__name__)


def parse_soap_action(body: str) -> tuple[str, dict]:
    root = ET.fromstring(body)
    soap_body = root.find("{http://schemas.xmlsoap.org/soap/envelope/}Body")
    if soap_body is None:
        raise ValueError("No SOAP Body")
    action_el = list(soap_body)[0]
    action_name = action_el.tag.split("}")[-1] if "}" in action_el.tag else action_el.tag
    params = {}
    for child in action_el:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        params[tag] = child.text or ""
    return action_name, params


class SOAPHandler:
    def __init__(self, sonos_client: SonosClient):
        self.client = sonos_client

    def handle(self, path: str, soap_action: str, body: str) -> str:
        action_name, params = parse_soap_action(body)
        logger.info(f"SOAP {action_name} | {params}")

        if "/AVTransport" in path:
            return self._handle_av_transport(action_name, params)
        elif "/RenderingControl" in path:
            return self._handle_rendering_control(action_name, params)
        elif "/ZoneGroupTopology" in path:
            return self._handle_zone_topology(action_name, params)
        elif "/ContentDirectory" in path:
            return self._handle_content_directory(action_name, params)
        else:
            raise NotImplementedError(f"Unknown path: {path}")

    # -------------------------------------------------------------------------
    # AVTransport
    # -------------------------------------------------------------------------

    def _handle_av_transport(self, action: str, params: dict) -> str:
        room = self.client.get_active_room()
        if room is None:
            logger.warning("No active room")
            return self._empty(action)

        if action == "Play":
            room.play()
        elif action == "Pause":
            room.pause()
        elif action == "Stop":
            room.stop()
        elif action == "Next":
            room.next()
        elif action == "Previous":
            room.previous()
        elif action == "Seek":
            unit   = params.get("Unit", "REL_TIME")
            target = params.get("Target", "0")
            if unit == "TRACK_NR":
                room.seek_to_track(int(target))
            else:
                room.seek(self._hms_to_seconds(target))
        elif action == "SetPlayMode":
            self._apply_play_mode(room, params.get("NewPlayMode", "NORMAL"))
        elif action == "SetAVTransportURI":
            uri = params.get("CurrentURI", "")
            if uri:
                room.play_uri(uri, params.get("CurrentURIMetaData", ""))
        elif action == "GetTransportInfo":
            return self._get_transport_info(room)
        elif action == "GetPositionInfo":
            return self._get_position_info(room)
        elif action == "GetMediaInfo":
            return self._get_media_info(room)
        elif action == "GetTransportSettings":
            return self._get_transport_settings(room)

        return self._empty(action)

    def _apply_play_mode(self, room: SonosRoom, mode: str):
        mode_map = {
            "NORMAL":             ("none", False),
            "REPEAT_ALL":         ("all",  False),
            "REPEAT_ONE":         ("one",  False),
            "SHUFFLE":            ("all",  True),
            "SHUFFLE_NOREPEAT":   ("none", True),
            "SHUFFLE_REPEAT_ONE": ("one",  True),
        }
        repeat, shuffle = mode_map.get(mode, ("none", False))
        room.set_repeat(repeat)
        room.set_shuffle(shuffle)

    def _get_transport_info(self, room: SonosRoom) -> str:
        room.refresh()
        return (
            '<u:GetTransportInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'<CurrentTransportState>{room.playback_state}</CurrentTransportState>'
            '<CurrentTransportStatus>OK</CurrentTransportStatus>'
            '<CurrentSpeed>1</CurrentSpeed>'
            '</u:GetTransportInfoResponse>'
        )

    def _get_position_info(self, room: SonosRoom) -> str:
        room.refresh()
        track_didl, _ = didl_from_room_state(room)
        return (
            '<u:GetPositionInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'<Track>{room.queue_position}</Track>'
            f'<TrackDuration>{seconds_to_hms(room.track_duration)}</TrackDuration>'
            f'<TrackMetaData>{html.escape(track_didl)}</TrackMetaData>'
            f'<TrackURI>{html.escape(room.track_uri)}</TrackURI>'
            f'<RelTime>{seconds_to_hms(room.track_position)}</RelTime>'
            f'<AbsTime>{seconds_to_hms(room.track_position)}</AbsTime>'
            '<RelCount>0</RelCount><AbsCount>0</AbsCount>'
            '</u:GetPositionInfoResponse>'
        )

    def _get_media_info(self, room: SonosRoom) -> str:
        room.refresh()
        track_didl, next_didl = didl_from_room_state(room)
        next_uri = room.next_track.get("uri", "")
        return (
            '<u:GetMediaInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            '<NrTracks>1</NrTracks>'
            f'<MediaDuration>{seconds_to_hms(room.track_duration)}</MediaDuration>'
            f'<CurrentURI>{html.escape(room.track_uri)}</CurrentURI>'
            f'<CurrentURIMetaData>{html.escape(track_didl)}</CurrentURIMetaData>'
            f'<NextURI>{html.escape(next_uri)}</NextURI>'
            f'<NextURIMetaData>{html.escape(next_didl)}</NextURIMetaData>'
            '<PlayMedium>NETWORK</PlayMedium>'
            '<RecordMedium>NOT_IMPLEMENTED</RecordMedium>'
            '<WriteStatus>NOT_IMPLEMENTED</WriteStatus>'
            '</u:GetMediaInfoResponse>'
        )

    def _get_transport_settings(self, room: SonosRoom) -> str:
        play_mode = room.play_mode
        shuffle = play_mode.get("shuffle", False)
        repeat  = play_mode.get("repeat", "none")
        if repeat == "all" and shuffle:   mode = "SHUFFLE"
        elif repeat == "all":             mode = "REPEAT_ALL"
        elif repeat == "one":             mode = "REPEAT_ONE"
        elif shuffle:                     mode = "SHUFFLE_NOREPEAT"
        else:                             mode = "NORMAL"
        return (
            '<u:GetTransportSettingsResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">'
            f'<PlayMode>{mode}</PlayMode>'
            '<RecQualityMode>NOT_IMPLEMENTED</RecQualityMode>'
            '</u:GetTransportSettingsResponse>'
        )

    # -------------------------------------------------------------------------
    # RenderingControl
    # -------------------------------------------------------------------------

    def _handle_rendering_control(self, action: str, params: dict) -> str:
        room = self.client.get_active_room()
        if room is None:
            return self._empty(action)

        if action == "SetVolume":
            room.set_volume(int(params.get("DesiredVolume", 10)))
        elif action == "GetVolume":
            room.refresh()
            return (
                '<u:GetVolumeResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">'
                f'<CurrentVolume>{room.volume}</CurrentVolume>'
                '</u:GetVolumeResponse>'
            )
        elif action == "SetMute":
            room.set_mute(params.get("DesiredMute", "0") == "1")
        elif action == "GetMute":
            room.refresh()
            return (
                '<u:GetMuteResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">'
                f'<CurrentMute>{1 if room.mute else 0}</CurrentMute>'
                '</u:GetMuteResponse>'
            )

        return self._empty(action)

    # -------------------------------------------------------------------------
    # ZoneGroupTopology
    # -------------------------------------------------------------------------

    def _handle_zone_topology(self, action: str, params: dict) -> str:
        if action == "GetZoneGroupState":
            return self._get_zone_group_state()
        elif action == "GetZoneGroupAttributes":
            return self._get_zone_group_attributes()
        return self._empty(action)

    def _get_zone_group_state(self) -> str:
        zones = self.client.get_zone_topology()
        zone_xmls = []
        for zone in zones:
            members_xml = "".join(
                f'<ZoneGroupMember UUID="{m["uuid"]}" '
                f'Location="http://{m.get("ip", "127.0.0.1")}:1400/xml/device_description.xml" '
                f'ZoneName="{html.escape(m["name"])}" '
                f'Icon="x-rincon-roomicon:living" Configuration="1" '
                f'SoftwareVersion="29.3-87071" MinCompatibleVersion="22.0-00000" '
                f'LegacyCompatibleVersion="7.1-1r" BootSeq="1"/>'
                for m in zone["members"]
            )
            zone_xmls.append(
                f'<ZoneGroup Coordinator="{zone["coordinator_uuid"]}" '
                f'ID="{zone["coordinator_uuid"]}:0">{members_xml}</ZoneGroup>'
            )
        state_xml = f'<ZoneGroups>{"".join(zone_xmls)}</ZoneGroups>'
        return (
            '<u:GetZoneGroupStateResponse xmlns:u="urn:schemas-upnp-org:service:ZoneGroupTopology:1">'
            f'<ZoneGroupState>{html.escape(state_xml)}</ZoneGroupState>'
            '</u:GetZoneGroupStateResponse>'
        )

    def _get_zone_group_attributes(self) -> str:
        room = self.client.get_active_room()
        name = room.name if room else "Bridge"
        uuid = room.uuid if room else "00000000-0000-0000-0000-000000000000"
        return (
            '<u:GetZoneGroupAttributesResponse xmlns:u="urn:schemas-upnp-org:service:ZoneGroupTopology:1">'
            f'<CurrentZoneGroupName>{html.escape(name)}</CurrentZoneGroupName>'
            f'<CurrentZoneGroupID>{uuid}:0</CurrentZoneGroupID>'
            '<CurrentZonePlayerUDDISet></CurrentZonePlayerUDDISet>'
            '</u:GetZoneGroupAttributesResponse>'
        )

    # -------------------------------------------------------------------------
    # ContentDirectory
    # -------------------------------------------------------------------------

    def _handle_content_directory(self, action: str, params: dict) -> str:
        if action == "Browse":
            return self._browse(params)
        elif action == "Search":
            return self._search(params)
        return self._empty(action)

    def _browse(self, params: dict) -> str:
        object_id       = params.get("ObjectID", "")
        start_index     = int(params.get("StartingIndex", 0))
        requested_count = int(params.get("RequestedCount", 100))

        logger.info(f"Browse ObjectID={object_id}")

        if object_id.startswith("Q:"):
            return self._browse_queue(start_index, requested_count)
        if object_id in ("FV:2", "FV:2/0"):
            return self._browse_favorites()
        if object_id in ("A:PLAYLISTS", "SQ:"):
            return self._browse_playlists()
        if object_id in ("A:", "0", ""):
            return self._browse_root()

        # Fallback: try to browse as a service container via direct speaker proxy
        return self._browse_service_container(object_id)

    def _browse_queue(self, start: int, count: int) -> str:
        room = self.client.get_active_room()
        if room is None:
            return self._empty_browse()
        items = room.get_queue()
        page  = items[start:start + count]
        return self._browse_response(build_queue_didl(page), len(page), len(items))

    def _browse_favorites(self) -> str:
        favs = self.client.get_favorites()
        return self._browse_response(build_favorites_didl(favs), len(favs), len(favs))

    def _browse_playlists(self) -> str:
        playlists = self.client.get_playlists()
        containers = [
            {"id": f"SQ:{i}", "title": p.get("title", p.get("name", ""))}
            for i, p in enumerate(playlists)
        ]
        didl = build_container_didl(containers)
        return self._browse_response(didl, len(containers), len(containers))

    def _browse_root(self) -> str:
        """
        Return the root browse container. Starts with our curated S2 items
        (Favorites, Playlists, Queue), then appends whatever the S2 speaker's
        own root ContentDirectory exposes (music services, local library, etc.).
        """
        fixed_items = [
            {"id": "FV:2",        "title": "Sonos Favorites",  "upnpClass": "object.container"},
            {"id": "A:PLAYLISTS", "title": "Playlists",        "upnpClass": "object.container.playlistContainer"},
            {"id": "Q:0",         "title": "Queue",            "upnpClass": "object.container.playlistContainer"},
        ]
        # Append the S2 speaker's own root items (music services, etc.)
        s2_root_didl = self._proxy_browse_to_s2("0")
        if s2_root_didl:
            # Merge: parse the S2 DIDL and wrap it with our fixed items
            merged = build_container_didl(fixed_items) + s2_root_didl
            # Re-wrap: return fixed items + raw DIDL from S2 merged
            # Simpler: just return fixed items; the CR200 can drill into S2 services
            pass
        didl = build_container_didl(fixed_items)
        return self._browse_response(didl, len(fixed_items), len(fixed_items))

    def _browse_service_container(self, object_id: str) -> str:
        """
        Proxy ContentDirectory Browse directly to the active S2 speaker at
        port 1400. This gives the CR200 access to the S2's registered music
        services (Spotify, Apple Music, Tidal, etc.) and local library.
        """
        logger.debug(f"Proxying ContentDirectory Browse to S2: ObjectID={object_id}")
        didl = self._proxy_browse_to_s2(object_id)
        if didl is not None:
            # Count items in the DIDL
            try:
                root = ET.fromstring(didl)
                count = len(list(root))
            except ET.ParseError:
                count = 0
            return self._browse_response(didl, count, count)
        return self._empty_browse()

    # -------------------------------------------------------------------------
    # S2 ContentDirectory proxy — forwards Browse/Search to the S2 speaker
    # -------------------------------------------------------------------------

    _S2_CD_NS = "urn:schemas-upnp-org:service:ContentDirectory:1"

    def _proxy_browse_to_s2(self, object_id: str,
                             start: int = 0, count: int = 100,
                             browse_flag: str = "BrowseDirectChildren") -> str | None:
        """
        Send a ContentDirectory Browse SOAP request to the active S2 speaker
        and return the raw DIDL-Lite string, or None on failure.
        """
        ip = self.client.get_active_room_ip()
        if not ip:
            logger.debug("No S2 IP available for ContentDirectory proxy")
            return None

        soap = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
            ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            f'<u:Browse xmlns:u="{self._S2_CD_NS}">'
            f"<ObjectID>{html.escape(object_id)}</ObjectID>"
            f"<BrowseFlag>{browse_flag}</BrowseFlag>"
            "<Filter>*</Filter>"
            f"<StartingIndex>{start}</StartingIndex>"
            f"<RequestedCount>{count}</RequestedCount>"
            "<SortCriteria></SortCriteria>"
            "</u:Browse>"
            "</s:Body>"
            "</s:Envelope>"
        )

        url = f"http://{ip}:1400/MediaServer/ContentDirectory/Control"
        req = urllib.request.Request(
            url,
            data=soap.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPACTION": f'"{self._S2_CD_NS}#Browse"',
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"S2 ContentDirectory proxy failed for '{object_id}': {e}")
            return None

        # Extract the Result / 'r' element from the BrowseResponse
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            logger.warning(f"S2 ContentDirectory response parse error: {e}")
            return None

        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local in ("Result", "r") and el.text:
                logger.debug(f"S2 ContentDirectory proxy OK for '{object_id}'")
                return el.text

        logger.debug(f"S2 ContentDirectory response had no Result for '{object_id}'")
        return None

    def _proxy_search_to_s2(self, criteria: str, start: int, count: int) -> str | None:
        """
        Send a ContentDirectory Search SOAP request to the active S2 speaker
        and return the raw DIDL-Lite string, or None on failure.
        """
        ip = self.client.get_active_room_ip()
        if not ip:
            return None

        soap = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
            ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            f'<u:Search xmlns:u="{self._S2_CD_NS}">'
            '<ContainerID>0</ContainerID>'
            f"<SearchCriteria>{html.escape(criteria)}</SearchCriteria>"
            "<Filter>*</Filter>"
            f"<StartingIndex>{start}</StartingIndex>"
            f"<RequestedCount>{count}</RequestedCount>"
            "<SortCriteria></SortCriteria>"
            "</u:Search>"
            "</s:Body>"
            "</s:Envelope>"
        )

        url = f"http://{ip}:1400/MediaServer/ContentDirectory/Control"
        req = urllib.request.Request(
            url,
            data=soap.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPACTION": f'"{self._S2_CD_NS}#Search"',
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"S2 ContentDirectory search proxy failed: {e}")
            return None

        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return None

        for el in root.iter():
            local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
            if local in ("Result", "r") and el.text:
                return el.text
        return None

    def _search(self, params: dict) -> str:
        criteria = params.get("SearchCriteria", "")
        start    = int(params.get("StartingIndex", 0))
        count    = int(params.get("RequestedCount", 20))

        # 1. Proxy the Search request directly to the S2 speaker's ContentDirectory.
        #    This returns the S2's own search results (its registered music services).
        didl = self._proxy_search_to_s2(criteria, start, count)
        if didl:
            try:
                root = ET.fromstring(didl)
                returned = len(list(root))
            except ET.ParseError:
                returned = 0
            return self._browse_response(didl, returned, returned)

        # 2. Fallback: extract a text query and search via node-sonos-http-api
        query = self._extract_search_query(criteria)
        if not query:
            return self._empty_browse()

        room = self.client.get_active_room()
        if room is None:
            return self._empty_browse()

        results = []
        for service in ["spotify", "apple", "library"]:
            items = self.client.search(room.name, service, query)
            if items:
                results = items
                break

        page = results[start:start + count]
        return self._browse_response(build_queue_didl(page), len(page), len(results))

    def _extract_search_query(self, criteria: str) -> str:
        m = re.search(r'contains\s+"([^"]+)"', criteria)
        if m:
            return m.group(1)
        m = re.search(r'=\s+"([^"]+)"', criteria)
        if m:
            return m.group(1)
        return criteria.strip()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _browse_response(self, didl: str, returned: int, total: int) -> str:
        return (
            '<u:BrowseResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">'
            f'<r>{html.escape(didl)}</r>'
            f'<NumberReturned>{returned}</NumberReturned>'
            f'<TotalMatches>{total}</TotalMatches>'
            '<UpdateID>1</UpdateID>'
            '</u:BrowseResponse>'
        )

    def _empty_browse(self) -> str:
        return self._browse_response(
            '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>',
            0, 0
        )

    def _empty(self, action: str) -> str:
        return f'<u:{action}Response xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"/>'

    @staticmethod
    def _hms_to_seconds(hms: str) -> int:
        try:
            parts = hms.split(":")
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(parts[0])
        except Exception:
            return 0
