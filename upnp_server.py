"""
UPnP HTTP Server
Serves two things:
  1. Device description XML  — tells the CR200 what "device" it's talking to
  2. SOAP action endpoints   — receives play/pause/volume/etc commands
     and forwards them to real S2 speakers via SoCo
"""

import threading
import logging
import xml.etree.ElementTree as ET
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from config import BRIDGE_CONFIG
from soap_handler import SOAPHandler

logger = logging.getLogger(__name__)

# Minimal device description that looks like a Sonos ZonePlayer (S1 era)
DEVICE_DESCRIPTION_XML = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion><major>1</major><minor>0</minor></specVersion>
  <device>
    <deviceType>urn:schemas-upnp-org:device:ZonePlayer:1</deviceType>
    <friendlyName>{friendly_name}</friendlyName>
    <manufacturer>Sonos, Inc.</manufacturer>
    <manufacturerURL>http://www.sonos.com</manufacturerURL>
    <modelNumber>S3</modelNumber>
    <modelDescription>Sonos Zone Player</modelDescription>
    <modelName>Sonos Play:3</modelName>
    <UDN>uuid:{uuid}</UDN>
    <serviceList>
      <service>
        <serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:AVTransport</serviceId>
        <SCPDURL>/xml/AVTransport1.xml</SCPDURL>
        <controlURL>/MediaRenderer/AVTransport/Control</controlURL>
        <eventSubURL>/MediaRenderer/AVTransport/Event</eventSubURL>
      </service>
      <service>
        <serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:RenderingControl</serviceId>
        <SCPDURL>/xml/RenderingControl1.xml</SCPDURL>
        <controlURL>/MediaRenderer/RenderingControl/Control</controlURL>
        <eventSubURL>/MediaRenderer/RenderingControl/Event</eventSubURL>
      </service>
      <service>
        <serviceType>urn:schemas-upnp-org:service:ContentDirectory:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:ContentDirectory</serviceId>
        <SCPDURL>/xml/ContentDirectory1.xml</SCPDURL>
        <controlURL>/MediaServer/ContentDirectory/Control</controlURL>
        <eventSubURL>/MediaServer/ContentDirectory/Event</eventSubURL>
      </service>
      <service>
        <serviceType>urn:schemas-upnp-org:service:ZoneGroupTopology:1</serviceType>
        <serviceId>urn:upnp-org:serviceId:ZoneGroupTopology</serviceId>
        <SCPDURL>/xml/ZoneGroupTopology1.xml</SCPDURL>
        <controlURL>/ZoneGroupTopology/Control</controlURL>
        <eventSubURL>/ZoneGroupTopology/Event</eventSubURL>
      </service>
    </serviceList>
  </device>
</root>"""

# SOAP response envelope template
SOAP_RESPONSE_TEMPLATE = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"
            s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    {body}
  </s:Body>
</s:Envelope>"""

SOAP_ERROR_TEMPLATE = """<s:Fault>
  <faultcode>s:Client</faultcode>
  <faultstring>UPnPError</faultstring>
  <detail>
    <UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
      <errorCode>{code}</errorCode>
      <errorDescription>{description}</errorDescription>
    </UPnPError>
  </detail>
</s:Fault>"""


class UPnPRequestHandler(BaseHTTPRequestHandler):
    soap_handler: SOAPHandler = None  # Injected at server start

    def log_message(self, format, *args):
        logger.debug(f"HTTP {self.address_string()} - {format % args}")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/xml/device_description.xml":
            self._serve_device_description()
        elif path.startswith("/xml/"):
            # Serve stub service XML files — CR200 fetches these but we
            # only need them to not 404; actual control is via SOAP POST
            self._serve_stub_xml(path)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle incoming SOAP control actions from the CR200."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8", errors="ignore")

        soap_action = self.headers.get("SOAPACTION", "").strip('"')
        path = urlparse(self.path).path

        logger.info(f"SOAP POST to {path} action={soap_action}")
        logger.debug(f"SOAP body: {body}")

        try:
            response_body = self.soap_handler.handle(path, soap_action, body)
            response_xml = SOAP_RESPONSE_TEMPLATE.format(body=response_body)
            self.send_response(200)
            self.send_header("Content-Type", "text/xml; charset=utf-8")
            self.send_header("Content-Length", str(len(response_xml.encode())))
            self.end_headers()
            self.wfile.write(response_xml.encode())
        except NotImplementedError as e:
            logger.warning(f"Unhandled SOAP action: {soap_action} - {e}")
            self._send_soap_error(501, str(e))
        except Exception as e:
            logger.error(f"SOAP handler error: {e}", exc_info=True)
            self._send_soap_error(500, "Internal error")

    def do_SUBSCRIBE(self):
        """CR200 subscribes for UPnP events. Acknowledge but we won't push events (yet)."""
        self.send_response(200)
        self.send_header("SID", f"uuid:{BRIDGE_CONFIG['uuid']}-event")
        self.send_header("TIMEOUT", "Second-1800")
        self.end_headers()

    def do_UNSUBSCRIBE(self):
        self.send_response(200)
        self.end_headers()

    def _serve_device_description(self):
        xml = DEVICE_DESCRIPTION_XML.format(
            friendly_name=BRIDGE_CONFIG["friendly_name"],
            uuid=BRIDGE_CONFIG["uuid"],
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(xml.encode())))
        self.end_headers()
        self.wfile.write(xml.encode())

    def _serve_stub_xml(self, path: str):
        # Minimal valid SCPD XML — just enough to not break the CR200
        stub = """<?xml version="1.0"?><scpd xmlns="urn:schemas-upnp-org:service-1-0">
        <specVersion><major>1</major><minor>0</minor></specVersion>
        <actionList/><serviceStateTable/></scpd>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/xml")
        self.end_headers()
        self.wfile.write(stub.encode())

    def _send_soap_error(self, code: int, description: str):
        body = SOAP_ERROR_TEMPLATE.format(code=code, description=description)
        response_xml = SOAP_RESPONSE_TEMPLATE.format(body=body)
        self.send_response(500)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.end_headers()
        self.wfile.write(response_xml.encode())


class UPnPServer:
    def __init__(self, local_ip: str, soap_handler: SOAPHandler):
        self.local_ip = local_ip
        self.soap_handler = soap_handler
        self._server = None
        self._thread = None

    def start(self):
        # Inject soap_handler into the request handler class
        UPnPRequestHandler.soap_handler = self.soap_handler

        self._server = HTTPServer(
            (self.local_ip, BRIDGE_CONFIG["http_port"]),
            UPnPRequestHandler
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True
        )
        self._thread.start()
        logger.info(
            f"UPnP HTTP server listening on "
            f"{self.local_ip}:{BRIDGE_CONFIG['http_port']}"
        )

    def stop(self):
        if self._server:
            self._server.shutdown()
        logger.info("UPnP HTTP server stopped")
