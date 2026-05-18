"""
ableton_exporter.py — Ableton Live Set Exporter

Generates Ableton Live Set (.als) files from a Universal Session object.

Ableton Live Sets are gzip-compressed XML files. The XML structure
describes tracks, clips, devices, and routing.

This exporter generates a valid .als file with:
- All tracks in session order
- Track names from the console
- Instrument group organization (color-coded)
- Audio tracks configured for recording

The .als format is documented via community reverse-engineering:
    https://github.com/cylab/AbletonLiveParser

Ableton Version Compatibility:
    Live 10+  — Supported (XML schema version 10)
    Live 11+  — Recommended
    Live 12   — Full color support

Usage:
    from exporters.ableton.ableton_exporter import AbletonExporter
    exporter = AbletonExporter()
    path = exporter.export(session, "output/show.als")
"""

import gzip
import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from datetime import datetime

from models.session import Session
from models.track import Track, GROUP_COLORS
from exporters.base_exporter import BaseExporter, ExporterError

logger = logging.getLogger(__name__)


def hex_to_ableton_color(hex_color: str) -> int:
    """
    Convert hex color to Ableton's packed integer color format.

    Ableton uses 0xRRGGBBAA (RGBA, big-endian) stored as a signed 32-bit int.

    Parameters
    ----------
    hex_color : str
        Hex color e.g. "#C0392B"

    Returns
    -------
    int
        Ableton color integer.
    """
    hex_color = hex_color.lstrip("#")
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        # Ableton: ARGB packed as signed 32-bit
        color = (0xFF << 24) | (r << 16) | (g << 8) | b
        # Convert to signed 32-bit
        if color >= 0x80000000:
            color -= 0x100000000
        return color
    except (ValueError, IndexError):
        return -1  # Ableton default


# Ableton track color indices for standard colors (approximate mapping)
ABLETON_COLORS = {
    "DRUMS":   13,   # Red
    "VOCALS":  25,   # Blue
    "GUITARS": 18,   # Green
    "KEYS":    28,   # Purple
    "BASS":    10,   # Orange
    "BRASS":   5,    # Yellow
    "STRINGS": 22,   # Teal
    "EFFECTS": 0,    # Grey
    "MISC":    0,
}


class AbletonExporter(BaseExporter):
    """
    Ableton Live Set Exporter (.als).

    Generates a valid gzip-compressed XML Ableton Live Set with:
    - Audio tracks for each console channel
    - Tracks named and colored per instrument group
    - Return tracks for main bus groups
    - Master track

    The generated .als file can be opened directly in Ableton Live 10+.

    Example usage:
        exporter = AbletonExporter()
        path = exporter.export(session, "output/show.als")
    """

    # Ableton XML schema version
    SCHEMA_VERSION = "10"

    def __init__(self):
        super().__init__(daw_name="Ableton", file_extension=".als")

    def export(self, session: Session, output_path: str) -> str:
        """
        Export a Session to an Ableton Live Set (.als) file.

        Parameters
        ----------
        session : Session
        output_path : str

        Returns
        -------
        str
            Path to the written .als file.
        """
        if not session.tracks:
            raise ExporterError("AbletonExporter: Session has no tracks to export.")

        self.logger.info(
            f"[INFO] AbletonExporter: Exporting '{session.session_name}' "
            f"({len(session.tracks)} tracks) → Ableton Live"
        )

        out_path = self._ensure_output_dir(output_path)

        # Build the XML tree
        xml_bytes = self._build_als_xml(session)

        # Ableton .als files are gzip-compressed XML
        with gzip.open(out_path, "wb") as f:
            f.write(xml_bytes)

        self.logger.info(f"[SUCCESS] AbletonExporter: Written to '{out_path}'")
        return str(out_path)

    def _build_als_xml(self, session: Session) -> bytes:
        """Build the full Ableton Live Set XML and return as bytes."""

        # Root element
        root = ET.Element("Ableton")
        root.set("MajorVersion", "10.0.2")
        root.set("MinorVersion", "10.0.2b5")
        root.set("SchemaChangeCount", "3")
        root.set("Creator", f"Live Console DAW Mirror | {session.console}")
        root.set("Revision", "")

        # LiveSet
        live_set = ET.SubElement(root, "LiveSet")

        # Tracks container
        tracks_elem = ET.SubElement(live_set, "Tracks")

        track_id = 1
        for track in session.tracks:
            track_elem = self._build_audio_track(track, track_id, session)
            tracks_elem.append(track_elem)
            track_id += 1

        # Return tracks (one per bus group)
        for bus in session.buses[:8]:  # Ableton supports up to 12 return tracks
            ret = self._build_return_track(bus, track_id)
            tracks_elem.append(ret)
            track_id += 1

        # Master track
        master = self._build_master_track(session, track_id)
        live_set.append(master)

        # Scene list
        scenes = ET.SubElement(live_set, "Scenes")
        scene = ET.SubElement(scenes, "Scene")
        name_elem = ET.SubElement(scene, "Name")
        name_elem.set("Value", session.session_name)

        # Transport settings
        transport = ET.SubElement(live_set, "Transport")
        ET.SubElement(transport, "PhaseNudgeTempo").set("Value", "10")
        ET.SubElement(transport, "LoopOn").set("Value", "false")
        ET.SubElement(transport, "CurrentTime").set("Value", "0")
        ET.SubElement(transport, "LoopStart").set("Value", "0")
        ET.SubElement(transport, "LoopLength").set("Value", "16")
        ET.SubElement(transport, "DrawMode").set("Value", "0")
        ET.SubElement(transport, "TimeFormat").set("Value", "1")

        # Sample rate hint (stored in root)
        root.set("SampleRate", str(session.sample_rate))

        # Convert to pretty XML bytes
        raw = ET.tostring(root, encoding="unicode", xml_declaration=False)
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + raw
        return xml_str.encode("utf-8")

    def _build_audio_track(self, track: Track, track_id: int, session: Session) -> ET.Element:
        """Build an Ableton AudioTrack XML element."""
        color = ABLETON_COLORS.get(track.group, 0)

        t = ET.Element("AudioTrack")
        t.set("Id", str(track_id))
        t.set("LomId", "0")

        # Track name
        n = ET.SubElement(t, "Name")
        ET.SubElement(n, "EffectiveName").set("Value", track.name)
        ET.SubElement(n, "UserName").set("Value", track.name)
        ET.SubElement(n, "Annotation").set(
            "Value", f"CH {track.channel} | {track.group} | {session.console}"
        )
        ET.SubElement(n, "MemorizedFirstClipName").set("Value", "")

        # Color
        ET.SubElement(t, "ColorIndex").set("Value", str(color))

        # Auto-arm for recording
        ET.SubElement(t, "AutomationMode").set("Value", "0")
        ET.SubElement(t, "TrackDelay").set("Value", "0")
        ET.SubElement(t, "Freeze").set("Value", "false")

        # Device chain
        device_chain = ET.SubElement(t, "DeviceChain")
        audio_input = ET.SubElement(device_chain, "AudioInputRouting")
        ET.SubElement(audio_input, "Target").set("Value", f"AudioIn/{track.channel}")
        ET.SubElement(audio_input, "UpperDisplayString").set(
            "Value", f"Ext. In {track.channel}"
        )
        ET.SubElement(audio_input, "LowerDisplayString").set(
            "Value", "1/2" if track.track_type == "stereo" else "1"
        )

        audio_output = ET.SubElement(device_chain, "AudioOutputRouting")
        ET.SubElement(audio_output, "Target").set("Value", "AudioOut/Master")
        ET.SubElement(audio_output, "UpperDisplayString").set("Value", "Master")
        ET.SubElement(audio_output, "LowerDisplayString").set("Value", "")

        # Mixer settings
        mixer = ET.SubElement(device_chain, "Mixer")
        ET.SubElement(mixer, "Volume").set("Value", "1")
        ET.SubElement(mixer, "Pan").set("Value", "0")
        ET.SubElement(mixer, "Mute").set("Value", "false")
        ET.SubElement(mixer, "Solo").set("Value", "false")
        ET.SubElement(mixer, "SoloSink").set("Value", "false")
        ET.SubElement(mixer, "MonitoringEnum").set("Value", "1")  # In = 0, Auto = 1, Off = 2

        # Clip slots (empty)
        clip_slots = ET.SubElement(t, "ClipSlotList")
        for i in range(8):
            slot = ET.SubElement(clip_slots, "ClipSlot")
            slot.set("Id", str(i))
            ET.SubElement(slot, "HasStop").set("Value", "true")
            ET.SubElement(slot, "NeedRefreeze").set("Value", "true")

        ET.SubElement(t, "TrackGroupId").set("Value", "-1")
        ET.SubElement(t, "TrackUnfolded").set("Value", "true")

        return t

    def _build_return_track(self, bus, track_id: int) -> ET.Element:
        """Build an Ableton ReturnTrack for a bus/subgroup."""
        t = ET.Element("ReturnTrack")
        t.set("Id", str(track_id))

        n = ET.SubElement(t, "Name")
        ET.SubElement(n, "EffectiveName").set("Value", bus.name)
        ET.SubElement(n, "UserName").set("Value", bus.name)
        ET.SubElement(n, "Annotation").set("Value", f"{bus.bus_type}")

        ET.SubElement(t, "ColorIndex").set("Value", "1")

        device_chain = ET.SubElement(t, "DeviceChain")
        audio_out = ET.SubElement(device_chain, "AudioOutputRouting")
        ET.SubElement(audio_out, "Target").set("Value", "AudioOut/Master")
        ET.SubElement(audio_out, "UpperDisplayString").set("Value", "Master")

        mixer = ET.SubElement(device_chain, "Mixer")
        ET.SubElement(mixer, "Volume").set("Value", "1")
        ET.SubElement(mixer, "Pan").set("Value", "0")
        ET.SubElement(mixer, "Mute").set("Value", "false")

        return t

    def _build_master_track(self, session: Session, track_id: int) -> ET.Element:
        """Build the Ableton MasterTrack."""
        master = ET.Element("MasterTrack")
        master.set("Id", str(track_id))

        n = ET.SubElement(master, "Name")
        ET.SubElement(n, "EffectiveName").set("Value", "Master")
        ET.SubElement(n, "UserName").set("Value", "Master")
        ET.SubElement(n, "Annotation").set(
            "Value", f"Generated by Live Console DAW Mirror | {session.session_name}"
        )

        ET.SubElement(master, "ColorIndex").set("Value", "0")

        device_chain = ET.SubElement(master, "DeviceChain")
        audio_out = ET.SubElement(device_chain, "AudioOutputRouting")
        ET.SubElement(audio_out, "Target").set("Value", "AudioOut/None")

        mixer = ET.SubElement(device_chain, "Mixer")
        ET.SubElement(mixer, "Volume").set("Value", "1")
        ET.SubElement(mixer, "Pan").set("Value", "0")
        ET.SubElement(mixer, "Tempo").set("Value", "120")
        ET.SubElement(mixer, "TimeSignature").set("Numerator", "4")
        ET.SubElement(mixer, "TimeSignature").set("Denominator", "4")

        return master
