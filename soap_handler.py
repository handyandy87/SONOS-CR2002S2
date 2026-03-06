"""
SOAP Handler
Parses incoming UPnP SOAP actions from the CR200 and maps them
to the appropriate SoCo (S2) API calls.

CR200 sends actions like:
  - AVTransport::Play
  - AVTransport::Pause
  - AVTransport::Next / Previous
  - AVTransport::SetAVTransportURI  (change track/queue)
  - RenderingControl::SetVolume
  - RenderingControl::GetVolume
  - ZoneGroupTopology::GetZoneGroupState
  - ContentDirectory::Browse
"""

import logging
import xml.etree.ElementTree as ET
from typing import Optional
import soco
from soco import SoCo
from zone_manager import ZoneManager

logger = logging.getLogger(__name__)

# XML namespaces used in SOAP bodies
NS = {
    "s": "http://schemas.xmlsoap.org/soap/envelope/",
    "u": "",  # action namespace, varies per service
}


def parse_soap_action(body: str) -> tuple[str, dict]:
    """Extract action name and parameters from a SOAP body."""
    root = ET.fromstring(body)
    soap_body = root.find("{http://schemas.xmlsoap.org/soap/envelope/}Body")
    if soap_body is None:
        raise ValueError("No SOAP Body found")

    # First child of Body is the action element
    action_el = list(soap_body)[0]
    action_name = action_el.tag.split("}")[-1] if "}" in action_el.tag else action_el.tag

    params = {}
    for child in action_el:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        params[tag] = child.text or ""

    return action_name, params


class SOAPHandler:
    def __init__(self, zone_manager: ZoneManager):
        self.zone_manager = zone_manager

    def handle(self, path: str, soap_action: str, body: str) -> str:
        """Route SOAP action to the correct handler. Returns response XML body string."""
        action_name, params = parse_soap_action(body)
        logger.info(f"Action: {action_name} | Params: {params}")

        # Route by path/service
        if "/AVTransport" in path:
            return self._handle_av_transport(action_name, params)
        elif "/RenderingControl" in path:
            return self._handle_rendering_control(action_name, params)
        elif "/ZoneGroupTopology" in path:
            return self._handle_zone_topology(action_name, params)
        elif "/ContentDirectory" in path:
            return self._handle_content_directory(action_name, params)
        else:
            raise NotImplementedError(f"Unknown service path: {path}")

    # -------------------------------------------------------------------------
    # AVTransport — playback control
    # -------------------------------------------------------------------------

    def _handle_av_transport(self, action: str, params: dict) -> str:
        speaker = self.zone_manager.get_active_speaker()
        if speaker is None:
            logger.warning("No active speaker — cannot handle AVTransport action")
            return self._empty_response(action)

        if action == "Play":
            speaker.play()
            logger.info(f"► Play on {speaker.player_name}")

        elif action == "Pause":
            speaker.pause()
            logger.info(f"⏸ Pause on {speaker.player_name}")

        elif action == "Stop":
            speaker.stop()
            logger.info(f"⏹ Stop on {speaker.player_name}")

        elif action == "Next":
            speaker.next()
            logger.info(f"⏭ Next on {speaker.player_name}")

        elif action == "Previous":
            speaker.previous()
            logger.info(f"⏮ Previous on {speaker.player_name}")

        elif action == "Seek":
            unit = params.get("Unit", "REL_TIME")
            target = params.get("Target", "0:00:00")
            if unit == "TRACK_NR":
                speaker.play_from_queue(int(target) - 1)
            else:
                speaker.seek(target)
            logger.info(f"⏩ Seek {unit}={target} on {speaker.player_name}")

        elif action == "SetPlayMode":
            mode = params.get("NewPlayMode", "NORMAL")
            self._apply_play_mode(speaker, mode)

        elif action == "SetAVTransportURI":
            uri = params.get("CurrentURI", "")
            metadata = params.get("CurrentURIMetaData", "")
            if uri:
                speaker.play_uri(uri, meta=metadata)
                logger.info(f"▶ Play URI: {uri}")

        elif action == "GetTransportInfo":
            return self._get_transport_info(speaker)

        elif action == "GetPositionInfo":
            return self._get_position_info(speaker)

        elif action == "GetMediaInfo":
            return self._get_media_info(speaker)

        return self._empty_response(action)

    def _apply_play_mode(self, speaker: SoCo, mode: str):
        """Map UPnP play modes to SoCo shuffle/repeat settings."""
        mode_map = {
            "NORMAL":         (False, False, False),
            "REPEAT_ALL":     (True,  False, False),
            "REPEAT_ONE":     (False, False, True),
            "SHUFFLE":        (True,  True,  False),
            "SHUFFLE_NOREPEAT": (False, True, False),
        }
        repeat, shuffle, repeat_one = mode_map.get(mode, (False, False, False))
        speaker.repeat = "ONE" if repeat_one else repeat
        speaker.shuffle = shuffle

    def _get_transport_info(self, speaker: SoCo) -> str:
        try:
            info = speaker.get_current_transport_info()
            state = info.get("current_transport_state", "STOPPED")
        except Exception:
            state = "STOPPED"
        return f"""<u:GetTransportInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
            <CurrentTransportState>{state}</CurrentTransportState>
            <CurrentTransportStatus>OK</CurrentTransportStatus>
            <CurrentSpeed>1</CurrentSpeed>
        </u:GetTransportInfoResponse>"""

    def _get_position_info(self, speaker: SoCo) -> str:
        try:
            info = speaker.get_current_track_info()
            track = info.get("playlist_position", 1)
            duration = info.get("duration", "0:00:00")
            position = info.get("position", "0:00:00")
            uri = info.get("uri", "")
            title = info.get("title", "")
        except Exception:
            track, duration, position, uri, title = 1, "0:00:00", "0:00:00", "", ""
        return f"""<u:GetPositionInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
            <Track>{track}</Track>
            <TrackDuration>{duration}</TrackDuration>
            <TrackMetaData></TrackMetaData>
            <TrackURI>{uri}</TrackURI>
            <RelTime>{position}</RelTime>
            <AbsTime>{position}</AbsTime>
            <RelCount>0</RelCount>
            <AbsCount>0</AbsCount>
        </u:GetPositionInfoResponse>"""

    def _get_media_info(self, speaker: SoCo) -> str:
        try:
            info = speaker.get_current_track_info()
            uri = info.get("uri", "")
        except Exception:
            uri = ""
        return f"""<u:GetMediaInfoResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
            <NrTracks>0</NrTracks>
            <MediaDuration>0:00:00</MediaDuration>
            <CurrentURI>{uri}</CurrentURI>
            <CurrentURIMetaData></CurrentURIMetaData>
            <NextURI></NextURI>
            <NextURIMetaData></NextURIMetaData>
            <PlayMedium>NONE</PlayMedium>
            <RecordMedium>NOT_IMPLEMENTED</RecordMedium>
            <WriteStatus>NOT_IMPLEMENTED</WriteStatus>
        </u:GetMediaInfoResponse>"""

    # -------------------------------------------------------------------------
    # RenderingControl — volume
    # -------------------------------------------------------------------------

    def _handle_rendering_control(self, action: str, params: dict) -> str:
        speaker = self.zone_manager.get_active_speaker()
        if speaker is None:
            return self._empty_response(action)

        if action == "SetVolume":
            vol = int(params.get("DesiredVolume", 10))
            speaker.volume = vol
            logger.info(f"🔊 Volume → {vol} on {speaker.player_name}")

        elif action == "GetVolume":
            vol = speaker.volume
            return f"""<u:GetVolumeResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
                <CurrentVolume>{vol}</CurrentVolume>
            </u:GetVolumeResponse>"""

        elif action == "SetMute":
            muted = params.get("DesiredMute", "0") == "1"
            speaker.mute = muted
            logger.info(f"🔇 Mute → {muted} on {speaker.player_name}")

        elif action == "GetMute":
            muted = 1 if speaker.mute else 0
            return f"""<u:GetMuteResponse xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
                <CurrentMute>{muted}</CurrentMute>
            </u:GetMuteResponse>"""

        return self._empty_response(action)

    # -------------------------------------------------------------------------
    # ZoneGroupTopology — zone/group discovery
    # -------------------------------------------------------------------------

    def _handle_zone_topology(self, action: str, params: dict) -> str:
        if action == "GetZoneGroupState":
            return self._get_zone_group_state()
        elif action == "GetZoneGroupAttributes":
            return self._get_zone_group_attributes()
        return self._empty_response(action)

    def _get_zone_group_state(self) -> str:
        """Build a ZoneGroupState XML from discovered S2 speakers."""
        zones = self.zone_manager.get_all_zones()
        zone_xml_parts = []

        for zone in zones:
            members_xml = ""
            for member in zone["members"]:
                members_xml += f"""<ZoneGroupMember
                    UUID="{member['uuid']}"
                    Location="http://{member['ip']}:1400/xml/device_description.xml"
                    ZoneName="{member['name']}"
                    Icon="x-rincon-roomicon:living"
                    Configuration="1"
                    SoftwareVersion="29.3-87071"
                    MinCompatibleVersion="22.0-00000"
                    LegacyCompatibleVersion="7.1-1r"
                    BootSeq="1"
                />"""
            zone_xml_parts.append(
                f'<ZoneGroup Coordinator="{zone["coordinator_uuid"]}" '
                f'ID="{zone["coordinator_uuid"]}:0">'
                f'{members_xml}</ZoneGroup>'
            )

        zone_groups_xml = "".join(zone_xml_parts)
        # The full state is DIDL-style, wrapped and XML-escaped for SOAP
        state_xml = f"<ZoneGroups>{zone_groups_xml}</ZoneGroups>"
        import html
        escaped = html.escape(state_xml)

        return f"""<u:GetZoneGroupStateResponse xmlns:u="urn:schemas-upnp-org:service:ZoneGroupTopology:1">
            <ZoneGroupState>{escaped}</ZoneGroupState>
        </u:GetZoneGroupStateResponse>"""

    def _get_zone_group_attributes(self) -> str:
        speaker = self.zone_manager.get_active_speaker()
        name = speaker.player_name if speaker else "Bridge"
        return f"""<u:GetZoneGroupAttributesResponse xmlns:u="urn:schemas-upnp-org:service:ZoneGroupTopology:1">
            <CurrentZoneGroupName>{name}</CurrentZoneGroupName>
            <CurrentZoneGroupID>RINCON_000000000000:0</CurrentZoneGroupID>
            <CurrentZonePlayerUDDISet></CurrentZonePlayerUDDISet>
        </u:GetZoneGroupAttributesResponse>"""

    # -------------------------------------------------------------------------
    # ContentDirectory — browse music library / queue
    # -------------------------------------------------------------------------

    def _handle_content_directory(self, action: str, params: dict) -> str:
        speaker = self.zone_manager.get_active_speaker()

        if action == "Browse":
            object_id = params.get("ObjectID", "Q:0")
            # Q:0 is the play queue
            if object_id.startswith("Q:"):
                return self._browse_queue(speaker)
            else:
                # Return empty container for other browse requests
                return self._empty_browse_response()

        return self._empty_response(action)

    def _browse_queue(self, speaker: Optional[SoCo]) -> str:
        if speaker is None:
            return self._empty_browse_response()
        try:
            queue = speaker.get_queue()
            items_xml = ""
            for i, item in enumerate(queue):
                items_xml += f"""<item id="Q:0/{i+1}" parentID="Q:0" restricted="true">
                    <dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">{item.title}</dc:title>
                    <res>{item.resources[0].uri if item.resources else ""}</res>
                </item>"""
            count = len(queue)
            import html
            didl = f'<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">{items_xml}</DIDL-Lite>'
            return f"""<u:BrowseResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
                <Result>{html.escape(didl)}</Result>
                <NumberReturned>{count}</NumberReturned>
                <TotalMatches>{count}</TotalMatches>
                <UpdateID>1</UpdateID>
            </u:BrowseResponse>"""
        except Exception as e:
            logger.error(f"Browse queue error: {e}")
            return self._empty_browse_response()

    def _empty_browse_response(self) -> str:
        import html
        didl = '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>'
        return f"""<u:BrowseResponse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
            <Result>{html.escape(didl)}</Result>
            <NumberReturned>0</NumberReturned>
            <TotalMatches>0</TotalMatches>
            <UpdateID>1</UpdateID>
        </u:BrowseResponse>"""

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _empty_response(self, action: str) -> str:
        return f'<u:{action}Response xmlns:u="urn:schemas-upnp-org:service:AVTransport:1"/>'
