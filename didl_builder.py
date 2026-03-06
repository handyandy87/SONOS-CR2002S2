"""
DIDL-Lite Metadata Builder

The CR200 screen shows Now Playing info (title, artist, album, artwork)
by parsing DIDL-Lite XML embedded in SOAP responses.

This module builds correct DIDL-Lite from node-sonos-http-api state data,
including artwork URLs that the CR200 can fetch directly.

DIDL-Lite spec: http://www.upnp.org/specs/av/UPnP-av-ContentDirectory-v1-Service.pdf
Sonos extensions: x-rincon-*, upnp:class values, res protocol info
"""

import html
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Sonos/UPnP namespaces used in DIDL-Lite
DIDL_NS = 'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"'
DC_NS   = 'xmlns:dc="http://purl.org/dc/elements/1.1/"'
UPNP_NS = 'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
R_NS    = 'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"'

ALL_NS  = f'{DIDL_NS} {DC_NS} {UPNP_NS} {R_NS}'


def _esc(s: str) -> str:
    """XML-escape a string for embedding in attributes/text."""
    return html.escape(str(s), quote=True)


def seconds_to_hms(seconds: int) -> str:
    """Convert seconds to HH:MM:SS for UPnP duration fields."""
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{'0' if m < 10 else ''}{m}:{'0' if s < 10 else ''}{s}"


def build_track_didl(
    title: str,
    artist: str,
    album: str,
    artwork_url: str,
    uri: str,
    duration_secs: int = 0,
    track_num: int = 1,
    upnp_class: str = "object.item.audioItem.musicTrack",
    item_id: str = "Q:0/1",
    parent_id: str = "Q:0",
) -> str:
    """
    Build a DIDL-Lite XML string for a single track.
    This is what gets embedded (XML-escaped) in GetPositionInfo
    and GetMediaInfo SOAP responses so the CR200 shows Now Playing.
    """
    duration = seconds_to_hms(duration_secs)
    art_element = (
        f'<upnp:albumArtURI>{_esc(artwork_url)}</upnp:albumArtURI>'
        if artwork_url else ""
    )

    # res element carries the stream URI + protocol info
    protocol_info = _guess_protocol_info(uri)
    res_element = (
        f'<res protocolInfo="{_esc(protocol_info)}" duration="{duration}">'
        f'{_esc(uri)}</res>'
        if uri else ""
    )

    didl = (
        f'<DIDL-Lite {ALL_NS}>'
        f'<item id="{_esc(item_id)}" parentID="{_esc(parent_id)}" restricted="true">'
        f'<dc:title>{_esc(title)}</dc:title>'
        f'<dc:creator>{_esc(artist)}</dc:creator>'
        f'<upnp:artist>{_esc(artist)}</upnp:artist>'
        f'<upnp:album>{_esc(album)}</upnp:album>'
        f'<upnp:class>{upnp_class}</upnp:class>'
        f'<upnp:albumArtist>{_esc(artist)}</upnp:albumArtist>'
        f'{art_element}'
        f'{res_element}'
        f'</item>'
        f'</DIDL-Lite>'
    )
    return didl


def build_radio_didl(
    station_name: str,
    stream_uri: str,
    artwork_url: str = "",
    current_title: str = "",  # "Artist - Song" string often in radio metadata
) -> str:
    """DIDL-Lite for radio/streaming stations (no album/track structure)."""
    art_element = (
        f'<upnp:albumArtURI>{_esc(artwork_url)}</upnp:albumArtURI>'
        if artwork_url else ""
    )
    display_title = current_title or station_name

    didl = (
        f'<DIDL-Lite {ALL_NS}>'
        f'<item id="R:0/0" parentID="R:0" restricted="true">'
        f'<dc:title>{_esc(display_title)}</dc:title>'
        f'<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>'
        f'<r:streamContent>{_esc(current_title)}</r:streamContent>'
        f'<r:radioShowMd></r:radioShowMd>'
        f'{art_element}'
        f'<res protocolInfo="x-rincon-mp3radio:*:audio/mpeg:*">'
        f'{_esc(stream_uri)}</res>'
        f'</item>'
        f'</DIDL-Lite>'
    )
    return didl


def build_queue_didl(items: list[dict]) -> str:
    """
    Build a DIDL-Lite container with multiple queue items.
    Used for ContentDirectory Browse responses.
    """
    item_xmls = []
    for i, item in enumerate(items):
        title    = item.get("title", "Unknown")
        artist   = item.get("artist", "")
        album    = item.get("album", "")
        uri      = item.get("uri", "")
        art      = item.get("albumArtUri", "")
        duration = item.get("duration", 0)

        art_el = f'<upnp:albumArtURI>{_esc(art)}</upnp:albumArtURI>' if art else ""
        proto  = _guess_protocol_info(uri)
        dur_s  = seconds_to_hms(duration)

        item_xmls.append(
            f'<item id="Q:0/{i+1}" parentID="Q:0" restricted="true">'
            f'<dc:title>{_esc(title)}</dc:title>'
            f'<dc:creator>{_esc(artist)}</dc:creator>'
            f'<upnp:artist>{_esc(artist)}</upnp:artist>'
            f'<upnp:album>{_esc(album)}</upnp:album>'
            f'<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
            f'{art_el}'
            f'<res protocolInfo="{_esc(proto)}" duration="{dur_s}">{_esc(uri)}</res>'
            f'</item>'
        )

    return f'<DIDL-Lite {ALL_NS}>{"".join(item_xmls)}</DIDL-Lite>'


def build_container_didl(containers: list[dict]) -> str:
    """
    Build DIDL-Lite with container items (playlists, albums, service roots).
    """
    item_xmls = []
    for i, c in enumerate(containers):
        cid   = c.get("id", f"C:{i}")
        title = c.get("title", c.get("name", "Untitled"))
        art   = c.get("albumArtUri", "")
        upnp_class = c.get("upnpClass", "object.container.playlistContainer")
        art_el = f'<upnp:albumArtURI>{_esc(art)}</upnp:albumArtURI>' if art else ""

        item_xmls.append(
            f'<container id="{_esc(cid)}" parentID="A:PLAYLISTS" restricted="true" '
            f'searchable="false" childCount="0">'
            f'<dc:title>{_esc(title)}</dc:title>'
            f'<upnp:class>{upnp_class}</upnp:class>'
            f'{art_el}'
            f'</container>'
        )

    return f'<DIDL-Lite {ALL_NS}>{"".join(item_xmls)}</DIDL-Lite>'


def build_favorites_didl(favorites: list[dict]) -> str:
    """Build DIDL-Lite for Sonos Favorites list."""
    item_xmls = []
    for i, fav in enumerate(favorites):
        title = fav.get("title", fav.get("name", "Favorite"))
        uri   = fav.get("uri", "")
        art   = fav.get("albumArtUri", fav.get("art", ""))
        meta  = fav.get("metadata", "")
        art_el = f'<upnp:albumArtURI>{_esc(art)}</upnp:albumArtURI>' if art else ""
        proto  = _guess_protocol_info(uri)

        item_xmls.append(
            f'<item id="FV:2/{i+1}" parentID="FV:2" restricted="true">'
            f'<dc:title>{_esc(title)}</dc:title>'
            f'<upnp:class>object.itemobject.item.sonos-favorite</upnp:class>'
            f'{art_el}'
            f'<res protocolInfo="{_esc(proto)}">{_esc(uri)}</res>'
            f'<r:type>instantPlay</r:type>'
            f'</item>'
        )

    return f'<DIDL-Lite {ALL_NS}>{"".join(item_xmls)}</DIDL-Lite>'


def didl_from_room_state(room) -> tuple[str, str]:
    """
    Given a SonosRoom, return (track_didl, next_didl) DIDL-Lite strings.
    Handles both normal tracks and radio/stream sources.
    """
    uri = room.track_uri
    is_radio = (
        uri.startswith("x-sonosapi-stream:")
        or uri.startswith("x-rincon-mp3radio:")
        or uri.startswith("aac:")
        or "radiotime" in uri
    )

    if is_radio:
        track_didl = build_radio_didl(
            station_name=room.track_title or "Radio",
            stream_uri=uri,
            artwork_url=room.artwork_url,
            current_title=f"{room.track_artist} - {room.track_title}" if room.track_artist else room.track_title,
        )
    else:
        track_didl = build_track_didl(
            title=room.track_title,
            artist=room.track_artist,
            album=room.track_album,
            artwork_url=room.artwork_url,
            uri=uri,
            duration_secs=room.track_duration,
            track_num=room.queue_position,
        )

    # Next track (if available)
    next_t = room.next_track
    if next_t and next_t.get("title"):
        next_didl = build_track_didl(
            title=next_t.get("title", ""),
            artist=next_t.get("artist", ""),
            album=next_t.get("album", ""),
            artwork_url=next_t.get("absoluteAlbumArtUri", ""),
            uri=next_t.get("uri", ""),
            item_id="Q:0/2",
        )
    else:
        next_didl = ""

    return track_didl, next_didl


def _guess_protocol_info(uri: str) -> str:
    """
    Guess the UPnP protocolInfo string from a URI.
    The CR200 uses this to understand what kind of stream it is.
    """
    if not uri:
        return "http-get:*:audio/mpeg:*"
    u = uri.lower()
    if "spotify" in u or u.startswith("x-sonos-spotify"):
        return "x-sonos-spotify:*:audio/x-spotify:*"
    if u.startswith("x-sonosapi-stream"):
        return "x-sonosapi-stream:*:*:*"
    if u.startswith("x-rincon-mp3radio"):
        return "x-rincon-mp3radio:*:audio/mpeg:*"
    if u.startswith("x-rincon-queue"):
        return "x-rincon-queue:*:*:*"
    if u.endswith(".flac"):
        return "http-get:*:audio/flac:*"
    if u.endswith(".mp4") or u.endswith(".m4a") or u.endswith(".aac"):
        return "http-get:*:audio/mp4:*"
    if u.endswith(".ogg"):
        return "http-get:*:audio/ogg:*"
    return "http-get:*:audio/mpeg:*"
