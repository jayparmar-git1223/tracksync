"""
allen_heath_parser.py — Allen & Heath Console Parser

Handles session data from Allen & Heath dLive, SQ, and Avantis series consoles.

Allen & Heath consoles export session data as:
  - .scene  (dLive XML scene files)
  - .csv    (channel name exports from Allen & Heath Editor software)
  - .txt    (plain channel lists)

Supported consoles:
    dLive S Class, C Class, CDM (MixRack)
    SQ-5, SQ-6, SQ-7
    Avantis
    Qu-16, Qu-24, Qu-32, Qu-Pac, Qu-SB

Usage:
    from parser.allen_heath_parser import AllenHeathParser
    parser = AllenHeathParser()
    session = parser.parse("show.scene")
"""

import re
import csv
import logging
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path

from parser.base_parser import BaseParser, ParserError
from models.session import Session
from models.track import (
    Track, TRACK_TYPE_MONO, TRACK_TYPE_STEREO,
    GROUP_MISC, GROUP_COLORS,
)
from models.bus import Bus
from parser.digico_parser import classify_track, detect_stereo_pairs

logger = logging.getLogger(__name__)


class AllenHeathParser(BaseParser):
    """
    Parser for Allen & Heath dLive/SQ/Avantis/Qu console exports.

    Auto-detects the export format from file extension and content,
    then routes to the appropriate sub-parser.

    Example usage:
        parser = AllenHeathParser()
        session = parser.parse("dLive_show.scene")
    """

    AH_MODELS = [
        "dLive", "dlive",
        "SQ-5", "SQ-6", "SQ-7", "SQ5", "SQ6", "SQ7",
        "Avantis", "avantis",
        "Qu-16", "Qu-24", "Qu-32", "Qu-Pac", "Qu-SB",
        "GLD-80", "GLD-112",
    ]

    def __init__(self):
        super().__init__(console_name="Allen & Heath")

    def parse(self, file_path: str) -> Session:
        """
        Parse an Allen & Heath console session export file.

        Parameters
        ----------
        file_path : str
            Path to the console export file.

        Returns
        -------
        Session
            Universal Session object.
        """
        logger.info(f"[INFO] AllenHeathParser: Starting parse of '{file_path}'")
        path = self._validate_file(file_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix.lower()

        if suffix in (".scene", ".xml") or content.strip().startswith("<"):
            logger.info("[INFO] AllenHeathParser: Detected XML/Scene format")
            tracks, name, rate, model = self._parse_xml(content, path)
        elif suffix == ".csv" or ("," in content[:100] and "\n" in content[:100]):
            logger.info("[INFO] AllenHeathParser: Detected CSV format")
            tracks, name, rate, model = self._parse_csv(content, path)
        else:
            logger.info("[INFO] AllenHeathParser: Detected text format")
            tracks, name, rate, model = self._parse_txt(content, path)

        if not tracks:
            raise ParserError(
                f"AllenHeathParser: No tracks found in '{file_path}'. "
                f"Please verify this is a valid Allen & Heath session export."
            )

        for t in tracks:
            if t.group == GROUP_MISC:
                t.group = classify_track(t.name)
                t.color = GROUP_COLORS.get(t.group, "#95A5A6")

        tracks = detect_stereo_pairs(tracks)
        buses = self._auto_buses(tracks)

        session = Session(
            console=      f"Allen & Heath {model}",
            session_name= name,
            sample_rate=  rate,
            bit_depth=    24,
            source_file=  str(path),
            tracks=       tracks,
            buses=        buses,
        )

        logger.info(f"[SUCCESS] AllenHeathParser: '{name}' — {len(tracks)} tracks")
        return session

    def _parse_xml(self, content: str, path: Path):
        """Parse dLive .scene XML format."""
        tracks = []
        session_name = path.stem.replace("_", " ").title()
        sample_rate = 48000
        model = "dLive"

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.warning(f"[WARNING] AllenHeathParser: XML error: {e}. Falling back to text.")
            return self._parse_txt(content, path)

        # Find metadata
        for elem in root.iter():
            tag = elem.tag.lower()
            if "name" in tag and elem.text and len(elem.text.strip()) > 2:
                if "show" in tag or "scene" in tag or "session" in tag:
                    session_name = elem.text.strip()[:80]
            if "samplerate" in tag or "rate" in tag:
                try:
                    rate_val = int(elem.text.strip())
                    if rate_val in (44100, 48000, 88200, 96000):
                        sample_rate = rate_val
                except (ValueError, TypeError, AttributeError):
                    pass

        # dLive uses <Input> or <Channel> elements
        for ch_tag in ["Input", "Channel", "InputChannel", "Strip"]:
            elements = list(root.iter(ch_tag))
            if elements:
                for i, elem in enumerate(elements):
                    ch_num = None
                    for attr in ["Number", "number", "CH", "ch", "Index", "id"]:
                        if attr in elem.attrib:
                            try:
                                ch_num = int(elem.attrib[attr])
                                break
                            except ValueError:
                                pass
                    if ch_num is None:
                        ch_num = i + 1

                    # dLive stores name in <Name> or <UserLabel>
                    name = ""
                    for n_tag in ["Name", "UserLabel", "Label", "name"]:
                        n = elem.find(n_tag)
                        if n is not None and n.text:
                            name = n.text.strip()
                            break

                    if not name:
                        name = f"Input {ch_num}"

                    tracks.append(Track(channel=ch_num, name=name))
                break

        tracks.sort(key=lambda t: t.channel)
        return tracks, session_name, sample_rate, model

    def _parse_csv(self, content: str, path: Path):
        """Parse Allen & Heath CSV channel export."""
        tracks = []
        session_name = path.stem.replace("_", " ").title()
        sample_rate = 48000
        model = "SQ/dLive"

        # Detect model from content header
        for m in self.AH_MODELS:
            if m.lower() in content.lower()[:300]:
                model = m
                break

        try:
            reader = csv.reader(StringIO(content))
            for row in reader:
                if not row or len(row) < 2:
                    continue
                first = row[0].strip()
                if not first or first.lower() in ("ch", "channel", "#", "input", "strip"):
                    continue
                try:
                    ch_num = int(first)
                    name = row[1].strip()
                    if name and 1 <= ch_num <= 512:
                        tracks.append(Track(channel=ch_num, name=name))
                except (ValueError, IndexError):
                    continue
        except Exception as e:
            logger.warning(f"[WARNING] AllenHeathParser: CSV error: {e}")

        tracks.sort(key=lambda t: t.channel)
        return tracks, session_name, sample_rate, model

    def _parse_txt(self, content: str, path: Path):
        """Parse plain text channel list."""
        tracks = []
        session_name = path.stem.replace("_", " ").title()
        sample_rate = 48000
        model = "dLive/SQ"

        for m in self.AH_MODELS:
            if m.lower() in content[:200].lower():
                model = m
                break

        name_match = re.search(r'(?:show|scene|session)\s*[:\-]\s*(.+)', content, re.IGNORECASE)
        if name_match:
            session_name = name_match.group(1).strip()[:80]

        pattern = re.compile(
            r'^(\d{1,3})[:\.\s]+([A-Za-z][^\n\r]{1,40}?)\s*$', re.MULTILINE
        )
        seen = set()
        garbage = {"channel", "input", "strip", "name", "allen", "heath", "dlive", "avantis"}

        for m in pattern.finditer(content):
            try:
                ch_num = int(m.group(1))
                name = m.group(2).strip()
                if ch_num < 1 or ch_num > 512 or ch_num in seen:
                    continue
                if not name or name.lower() in garbage:
                    continue
                seen.add(ch_num)
                tracks.append(Track(channel=ch_num, name=name))
            except (ValueError, IndexError):
                continue

        tracks.sort(key=lambda t: t.channel)
        return tracks, session_name, sample_rate, model

    def _auto_buses(self, tracks: list[Track]) -> list[Bus]:
        groups = set(t.group for t in tracks)
        return [
            Bus(
                name=     f"{g.title()} Bus",
                bus_type= "subgroup",
                channels= [t.channel for t in tracks if t.group == g],
                color=    GROUP_COLORS.get(g, "#2C3E50"),
            )
            for g in groups if g != GROUP_MISC
        ]
