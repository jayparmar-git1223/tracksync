"""
osc_integration.py — OSC Integration Module

Sends and receives session data over OSC (Open Sound Control).

OSC is a widely supported protocol in professional audio that allows
real-time communication between consoles, DAWs, and control surfaces.

This module enables:
  1. SENDING   — Push session channel names/routing to a DiGiCo/Yamaha/etc
                 console over OSC for live show handoff
  2. RECEIVING — Receive channel name updates from a running console
                 and sync them back into the Universal Session JSON
  3. QUERYING  — Ask a console for its current channel list over OSC
                 (where the console supports OSC querying)

Supported OSC targets:
  - Reaper (localhost:8080 by default — REAPER OSC control)
  - DiGiCo SD Range (OSC extensions via third-party middleware)
  - Yamaha CL/QL (via Yamaha OSC companion or ProVisionaire)
  - QLab (localhost:53000)
  - Custom OSC targets (user-configurable IP:port)

This module uses the built-in Python socket library only.
An optional dependency on python-osc provides richer functionality.

Usage:
    from osc_integration import OSCClient, OSCSender

    # Send channel names to REAPER
    client = OSCClient("127.0.0.1", 8080)
    sender = OSCSender(client)
    sender.send_session(session)

    # Send to QLab
    qlab = OSCClient("192.168.1.50", 53000)
    sender = OSCSender(qlab)
    sender.announce_show(session.session_name)
"""

import socket
import struct
import logging
import time
from typing import Optional
from dataclasses import dataclass, field
from models.session import Session
from models.track import Track

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# OSC Packet Builder (minimal, no external dependency)
# ─────────────────────────────────────────────────────────────────────

def _pad_string(s: str) -> bytes:
    """Encode an OSC string — null-terminated, padded to 4-byte boundary."""
    encoded = (s + "\x00").encode("utf-8")
    # Pad to next 4-byte boundary
    padded_len = (len(encoded) + 3) & ~3
    return encoded.ljust(padded_len, b"\x00")


def _pad_blob(data: bytes) -> bytes:
    """Encode an OSC blob — 4-byte length prefix + data padded to 4-byte boundary."""
    size = struct.pack(">I", len(data))
    padded_len = (len(data) + 3) & ~3
    return size + data.ljust(padded_len, b"\x00")


def build_osc_message(address: str, *args) -> bytes:
    """
    Build a raw OSC message packet.

    Supports argument types:
      int, float, str, bytes (blob)

    Parameters
    ----------
    address : str
        The OSC address pattern. e.g. "/track/1/name"
    *args
        The message arguments.

    Returns
    -------
    bytes
        The raw OSC packet ready to send over UDP.
    """
    # Address
    packet = _pad_string(address)

    # Type tag string
    type_tags = ","
    for arg in args:
        if isinstance(arg, bool):
            type_tags += "T" if arg else "F"
        elif isinstance(arg, int):
            type_tags += "i"
        elif isinstance(arg, float):
            type_tags += "f"
        elif isinstance(arg, str):
            type_tags += "s"
        elif isinstance(arg, bytes):
            type_tags += "b"
        else:
            type_tags += "s"
            args = list(args)

    packet += _pad_string(type_tags)

    # Argument values
    for arg in args:
        if isinstance(arg, bool):
            pass  # T/F have no data
        elif isinstance(arg, int):
            packet += struct.pack(">i", arg)
        elif isinstance(arg, float):
            packet += struct.pack(">f", arg)
        elif isinstance(arg, str):
            packet += _pad_string(arg)
        elif isinstance(arg, bytes):
            packet += _pad_blob(arg)
        else:
            packet += _pad_string(str(arg))

    return packet


def build_osc_bundle(messages: list[tuple], timetag: float = 0.0) -> bytes:
    """
    Build an OSC bundle containing multiple messages.

    Parameters
    ----------
    messages : list of (address, *args) tuples
    timetag : float
        OSC timetag. 0 = immediate.

    Returns
    -------
    bytes
        The raw OSC bundle packet.
    """
    # Bundle header
    bundle = _pad_string("#bundle")

    # Timetag (64-bit NTP timestamp — 0 = immediate)
    if timetag == 0:
        bundle += struct.pack(">II", 0, 1)  # Immediate
    else:
        seconds     = int(timetag)
        fractions   = int((timetag - seconds) * 2**32)
        bundle += struct.pack(">II", seconds + 2208988800, fractions)

    for address, *args in messages:
        msg = build_osc_message(address, *args)
        bundle += struct.pack(">I", len(msg))
        bundle += msg

    return bundle


# ─────────────────────────────────────────────────────────────────────
# OSC Client
# ─────────────────────────────────────────────────────────────────────

@dataclass
class OSCTarget:
    """Represents a remote OSC endpoint."""
    name:        str
    ip:          str
    port:        int
    description: str = ""

    def __str__(self) -> str:
        return f"{self.name} ({self.ip}:{self.port})"


# Built-in known OSC targets
KNOWN_TARGETS = {
    "reaper":  OSCTarget("REAPER",  "127.0.0.1", 8080,  "REAPER DAW OSC control"),
    "qlab":    OSCTarget("QLab",    "127.0.0.1", 53000, "QLab show control"),
    "digico":  OSCTarget("DiGiCo",  "192.168.1.200", 9000, "DiGiCo SD Range OSC"),
    "yamaha":  OSCTarget("Yamaha",  "192.168.1.100", 9001, "Yamaha CL/QL OSC"),
    "x32":     OSCTarget("X32",     "192.168.1.50",  10023,"Behringer X32 OSC"),
    "m32":     OSCTarget("M32",     "192.168.1.50",  10023,"Midas M32 OSC"),
}


class OSCClient:
    """
    UDP-based OSC client for sending OSC messages and bundles.

    Uses Python's built-in socket module — no external dependencies.

    Example usage:
        client = OSCClient("127.0.0.1", 8080)
        client.send("/track/1/name", "Kick In")
        client.send("/track/1/volume", 0.8)
        client.close()
    """

    def __init__(self, ip: str, port: int, timeout: float = 2.0):
        """
        Parameters
        ----------
        ip : str
            Target IP address.
        port : int
            Target UDP port.
        timeout : float
            Socket timeout in seconds.
        """
        self.ip      = ip
        self.port    = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._connected = False

    def connect(self) -> bool:
        """
        Open the UDP socket.

        Returns
        -------
        bool
            True if the socket was opened successfully.
        """
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.settimeout(self.timeout)
            self._connected = True
            logger.info(f"[INFO] OSCClient: Socket opened → {self.ip}:{self.port}")
            return True
        except OSError as e:
            logger.error(f"[ERROR] OSCClient: Failed to open socket: {e}")
            return False

    def send(self, address: str, *args) -> bool:
        """
        Send a single OSC message.

        Parameters
        ----------
        address : str
            OSC address pattern. e.g. "/track/1/name"
        *args
            Message arguments.

        Returns
        -------
        bool
            True if sent successfully.
        """
        if not self._connected:
            self.connect()

        try:
            packet = build_osc_message(address, *args)
            self._sock.sendto(packet, (self.ip, self.port))
            logger.debug(f"[DEBUG] OSC → {address} {args}")
            return True
        except OSError as e:
            logger.error(f"[ERROR] OSCClient: Send failed: {e}")
            return False

    def send_bundle(self, messages: list[tuple]) -> bool:
        """
        Send a bundle of OSC messages atomically.

        Parameters
        ----------
        messages : list of (address, *args) tuples
        """
        if not self._connected:
            self.connect()
        try:
            packet = build_osc_bundle(messages)
            self._sock.sendto(packet, (self.ip, self.port))
            logger.debug(f"[DEBUG] OSC bundle → {len(messages)} messages")
            return True
        except OSError as e:
            logger.error(f"[ERROR] OSCClient: Bundle send failed: {e}")
            return False

    def ping(self) -> bool:
        """
        Test connectivity by sending a harmless OSC message.

        Returns True if the socket can send without error.
        (Note: UDP is fire-and-forget — true ACK requires a listener.)
        """
        return self.send("/liveconsole/ping", "ping")

    def close(self):
        """Close the UDP socket."""
        if self._sock:
            self._sock.close()
            self._sock       = None
            self._connected  = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self) -> str:
        return f"<OSCClient {self.ip}:{self.port} connected={self._connected}>"


# ─────────────────────────────────────────────────────────────────────
# OSC Session Sender — sends session data to a target
# ─────────────────────────────────────────────────────────────────────

class OSCSender:
    """
    Sends Universal Session data over OSC to a remote target.

    Supports multiple target protocols:
      - REAPER OSC control (channel names, volumes, colors)
      - Generic OSC (any target that accepts channel name messages)
      - QLab (cue list population)

    Example usage:
        client = OSCClient("127.0.0.1", 8080)
        sender = OSCSender(client, protocol="reaper")
        sender.send_session(session)
    """

    PROTOCOLS = ["reaper", "generic", "qlab", "x32"]

    def __init__(self, client: OSCClient, protocol: str = "generic",
                 delay_ms: int = 10):
        """
        Parameters
        ----------
        client : OSCClient
            The connected OSC client to send through.
        protocol : str
            OSC address schema to use. One of: reaper, generic, qlab, x32
        delay_ms : int
            Milliseconds to wait between messages (rate limiting).
            Some consoles drop messages if sent too fast.
        """
        self.client   = client
        self.protocol = protocol.lower()
        self.delay    = delay_ms / 1000.0

    def send_session(self, session: Session, tracks_only: bool = False) -> int:
        """
        Send all session track names and metadata over OSC.

        Parameters
        ----------
        session : Session
            The session to send.
        tracks_only : bool
            If True, send only track names (skip metadata).

        Returns
        -------
        int
            Number of messages sent successfully.
        """
        logger.info(
            f"[INFO] OSCSender: Sending '{session.session_name}' "
            f"({len(session.tracks)} tracks) via {self.protocol.upper()} OSC"
        )

        sent = 0

        if not tracks_only:
            sent += self._send_metadata(session)

        for track in session.tracks:
            ok = self._send_track(track)
            if ok:
                sent += 1
            if self.delay > 0:
                time.sleep(self.delay)

        logger.info(f"[SUCCESS] OSCSender: Sent {sent} OSC messages")
        return sent

    def send_track_name(self, channel: int, name: str) -> bool:
        """Send a single channel name update."""
        if self.protocol == "reaper":
            return self.client.send(f"/track/{channel}/name", name)
        elif self.protocol == "x32":
            ch_str = f"{channel:02d}"
            return self.client.send(f"/ch/{ch_str}/config/name", name)
        elif self.protocol == "qlab":
            return self.client.send(f"/cue/{channel}/name", name)
        else:
            return self.client.send(f"/channel/{channel}/name", name)

    def announce_show(self, show_name: str) -> bool:
        """Broadcast the show name to the target."""
        logger.info(f"[INFO] OSCSender: Announcing show '{show_name}'")
        return self.client.send("/liveconsole/show", show_name)

    def _send_metadata(self, session: Session) -> int:
        """Send session-level metadata messages."""
        sent = 0
        msgs = [
            ("/liveconsole/session_name", session.session_name),
            ("/liveconsole/console",      session.console),
            ("/liveconsole/track_count",  session.get_track_count()),
            ("/liveconsole/sample_rate",  session.sample_rate),
        ]
        for address, value in msgs:
            if self.client.send(address, value):
                sent += 1
            time.sleep(self.delay)
        return sent

    def _send_track(self, track: Track) -> bool:
        """Send a single track's data."""
        ch = track.channel
        ok = True

        if self.protocol == "reaper":
            ok &= self.client.send(f"/track/{ch}/name", track.name)
            # REAPER color: send group color index
            ok &= self.client.send(f"/track/{ch}/mute", int(track.mute))

        elif self.protocol == "x32":
            ch_str = f"{ch:02d}"
            ok &= self.client.send(f"/ch/{ch_str}/config/name", track.name)
            ok &= self.client.send(f"/ch/{ch_str}/mix/on", 1)

        elif self.protocol == "qlab":
            ok &= self.client.send(f"/cue/{ch}/name", track.name)
            ok &= self.client.send(f"/cue/{ch}/number", str(ch))

        else:
            # Generic: just send channel name
            ok &= self.client.send(f"/channel/{ch}/name", track.name)
            ok &= self.client.send(f"/channel/{ch}/group", track.group)

        return ok


# ─────────────────────────────────────────────────────────────────────
# OSC Listener — receive channel updates from a running console
# ─────────────────────────────────────────────────────────────────────

class OSCListener:
    """
    Listens for incoming OSC messages on a UDP port.

    Use this to receive channel name updates from a console
    and sync them back into a Session object.

    Note: This is a blocking listener. Run in a separate thread
    when using with a GUI application.

    Example usage (in a thread):
        listener = OSCListener(port=9000)
        listener.on_channel_name = lambda ch, name: print(f"CH {ch}: {name}")
        listener.start()  # blocks until listener.stop() called
    """

    def __init__(self, port: int = 9000, bind_ip: str = "0.0.0.0"):
        self.port      = port
        self.bind_ip   = bind_ip
        self._running  = False
        self._sock: Optional[socket.socket] = None

        # Callbacks — override these to handle incoming data
        self.on_channel_name  = None   # (channel: int, name: str) → None
        self.on_message       = None   # (address: str, args: list) → None

    def start(self):
        """Start listening for OSC messages. Blocks until stop() is called."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(1.0)

        try:
            self._sock.bind((self.bind_ip, self.port))
            self._running = True
            logger.info(f"[INFO] OSCListener: Listening on {self.bind_ip}:{self.port}")

            while self._running:
                try:
                    data, addr = self._sock.recvfrom(4096)
                    self._handle_packet(data, addr)
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.warning(f"[WARNING] OSCListener: Receive error: {e}")

        finally:
            self._sock.close()
            logger.info("[INFO] OSCListener: Stopped")

    def stop(self):
        """Signal the listener to stop."""
        self._running = False

    def _handle_packet(self, data: bytes, addr: tuple):
        """Parse an incoming OSC packet and fire callbacks."""
        try:
            # Decode the address string
            addr_end = data.index(b"\x00")
            address  = data[:addr_end].decode("utf-8")

            # Fire generic callback
            if self.on_message:
                self.on_message(address, [])

            # Parse channel name pattern: /channel/N/name or /ch/NN/config/name
            import re
            ch_match = re.search(r'/(?:channel|ch|track)/(\d+)(?:/config)?/name', address)
            if ch_match:
                ch_num = int(ch_match.group(1))
                # Extract string argument (after type tag ",s")
                name = self._extract_string_arg(data)
                if name and self.on_channel_name:
                    self.on_channel_name(ch_num, name)

        except Exception as e:
            logger.debug(f"[DEBUG] OSCListener: Could not parse packet: {e}")

    def _extract_string_arg(self, data: bytes) -> Optional[str]:
        """Extract the first string argument from an OSC message."""
        try:
            # Find type tag string (starts with ",")
            tag_start = data.index(b",")
            tag_end   = data.index(b"\x00", tag_start)
            type_tags = data[tag_start+1:tag_end].decode("ascii")

            # Find start of argument data (after type tag, padded to 4-byte)
            arg_start = (tag_end + 4) & ~3

            if "s" in type_tags:
                s_end  = data.index(b"\x00", arg_start)
                return data[arg_start:s_end].decode("utf-8")
        except Exception:
            pass
        return None
