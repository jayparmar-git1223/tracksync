"""
yamaha_parser.py — Yamaha CL/QL Series Console Parser

Handles session data exported from Yamaha CL and QL series consoles.

Yamaha CL/QL consoles can export session data in several formats:
  - .cel  (Console Extension Language — XML-based)
  - .csv  (channel name/patch export from various menus)
  - .txt  (plain text channel lists from CL/QL editors)

This parser supports all three formats, auto-detecting the type
from file content.

Supported consoles:
    CL1, CL3, CL5
    QL1, QL5

Architecture:
    YamahaParser (BaseParser)
        └── _parse_cel()   → XML format
        └── _parse_csv()   → CSV channel list
        └── _parse_txt()   → Plain text channel list

Usage:
    from parser.yamaha_parser import YamahaParser
    parser = YamahaParser()
    session = parser.parse("show.cel")
"""

import re
import csv
import logging
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from typing import Optional

from parser.base_parser import BaseParser, ParserError
from models.session import Session
from models.track import (
    Track, TRACK_TYPE_MONO, TRACK_TYPE_STEREO,
    GROUP_MISC, GROUP_COLORS,
)
from models.bus import Bus
from parser.digico_parser import classify_track, detect_stereo_pairs

logger = logging.getLogger(__name__)


class YamahaParser(BaseParser):
    """
    Parser for Yamaha CL/QL console session exports.

    Yamaha consoles export in multiple formats. This parser
    auto-detects the format and routes to the correct sub-parser.

    Supported file types:
        .cel  — Console Extension Language (XML)
        .csv  — Channel name/patch CSV export
        .txt  — Plain text channel list
        .xml  — Generic XML export

    Example usage:
        parser = YamahaParser()
        session = parser.parse("CL5_show.cel")
    """

    # Yamaha console model identifiers found in session files
    YAMAHA_MODELS = [
        "CL1", "CL3", "CL5",
        "QL1", "QL5",
        "PM5D", "PM7D",
        "M7CL", "LS9",
    ]

    def __init__(self):
        super().__init__(console_name="Yamaha CL/QL")

    def parse(self, file_path: str) -> Session:
        """
        Parse a Yamaha console session export file.

        Auto-detects the format from the file extension and content.

        Parameters
        ----------
        file_path : str
            Path to the Yamaha session file.

        Returns
        -------
        Session
            Fully-populated Universal Session object.
        """
        logger.info(f"[INFO] YamahaParser: Starting parse of '{file_path}'")
        path = self._validate_file(file_path)

        # Read raw file content
        content = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix.lower()

        # Auto-detect format
        if suffix in (".cel", ".xml") or content.strip().startswith("<"):
            logger.info("[INFO] YamahaParser: Detected XML/CEL format")
            tracks, session_name, sample_rate, console_model = self._parse_xml(content, path)
        elif suffix == ".csv" or "," in content[:200]:
            logger.info("[INFO] YamahaParser: Detected CSV format")
            tracks, session_name, sample_rate, console_model = self._parse_csv(content, path)
        else:
            logger.info("[INFO] YamahaParser: Detected plain text format")
            tracks, session_name, sample_rate, console_model = self._parse_txt(content, path)

        if not tracks:
            raise ParserError(
                f"YamahaParser: No tracks could be extracted from '{file_path}'. "
                f"Please check that this is a valid Yamaha session export."
            )

        logger.info(f"[INFO] YamahaParser: Found {len(tracks)} tracks")

        # Auto-classify and detect stereo pairs
        for track in tracks:
            if track.group == GROUP_MISC:
                track.group = classify_track(track.name)
                track.color = GROUP_COLORS.get(track.group, "#95A5A6")

        tracks = detect_stereo_pairs(tracks)

        # Auto-create buses from groups
        buses = self._build_buses(tracks)

        session = Session(
            console=      f"Yamaha {console_model}",
            session_name= session_name,
            sample_rate=  sample_rate,
            bit_depth=    24,
            source_file=  str(path),
            tracks=       tracks,
            buses=        buses,
        )

        logger.info(
            f"[SUCCESS] YamahaParser: Session '{session_name}' loaded — "
            f"{len(tracks)} tracks"
        )
        return session

    # ──────────────────────────────────────────────────────────────────
    # Format sub-parsers
    # ──────────────────────────────────────────────────────────────────

    def _parse_xml(
        self, content: str, path: Path
    ) -> tuple[list[Track], str, int, str]:
        """
        Parse Yamaha CEL/XML format.

        Yamaha CEL files are XML documents with a structure like:
            <YamahaProAudioData>
              <FileInfo>
                <ShowName>My Show</ShowName>
                <SamplingRate>48000</SamplingRate>
              </FileInfo>
              <InputChannel CH="1">
                <Name>Kick In</Name>
              </InputChannel>
            </YamahaProAudioData>
        """
        tracks = []
        session_name = path.stem
        sample_rate = 48000
        console_model = "CL/QL"

        try:
            root = ET.fromstring(content)
        except ET.ParseError as e:
            logger.warning(f"[WARNING] YamahaParser: XML parse error: {e}. Trying text fallback.")
            return self._parse_txt(content, path)

        # Extract metadata
        for elem in root.iter():
            tag = elem.tag.lower()
            if "showname" in tag or "sessionname" in tag:
                if elem.text:
                    session_name = elem.text.strip()
            elif "samplingrate" in tag or "samplerate" in tag:
                if elem.text:
                    try:
                        sample_rate = int(elem.text.strip())
                    except ValueError:
                        pass
            elif "model" in tag or "console" in tag:
                if elem.text:
                    console_model = elem.text.strip()

        # Extract channels — Yamaha XML uses CH attribute or sequential elements
        ch_elements = (
            list(root.iter("InputChannel")) or
            list(root.iter("Channel")) or
            list(root.iter("INPUT"))
        )

        for elem in ch_elements:
            ch_num = None

            # Try CH attribute first
            for attr in ["CH", "ch", "Number", "number", "ID", "id"]:
                if attr in elem.attrib:
                    try:
                        ch_num = int(elem.attrib[attr])
                        break
                    except ValueError:
                        pass

            # Fall back to auto-numbering
            if ch_num is None:
                ch_num = len(tracks) + 1

            # Get channel name
            name = ""
            for name_tag in ["Name", "name", "ChannelName", "Label", "label"]:
                name_elem = elem.find(name_tag)
                if name_elem is not None and name_elem.text:
                    name = name_elem.text.strip()
                    break

            if not name or name in ("", "CH " + str(ch_num), f"Input {ch_num}"):
                name = f"Input {ch_num}"

            tracks.append(Track(
                channel=    ch_num,
                name=       name,
                track_type= TRACK_TYPE_MONO,
                group=      GROUP_MISC,
            ))

        tracks.sort(key=lambda t: t.channel)
        return tracks, session_name, sample_rate, console_model

    def _parse_csv(
        self, content: str, path: Path
    ) -> tuple[list[Track], str, int, str]:
        """
        Parse Yamaha CSV channel name export.

        Common Yamaha CSV formats:
            CH,Name,Patch
            1,Kick In,1
            2,Snare Top,2

        Or without header:
            1,Kick In
            2,Snare Top
        """
        tracks = []
        session_name = path.stem.replace("_", " ").title()
        sample_rate = 48000
        console_model = "CL/QL"

        try:
            reader = csv.reader(StringIO(content))
            rows = list(reader)
        except Exception as e:
            logger.warning(f"[WARNING] YamahaParser: CSV parse error: {e}")
            return [], session_name, sample_rate, console_model

        for row in rows:
            if not row or len(row) < 2:
                continue

            # Skip header rows
            first = row[0].strip().lower()
            if first in ("ch", "channel", "#", "num", "number"):
                continue

            try:
                ch_num = int(row[0].strip())
                name = row[1].strip()

                if not name or ch_num < 1 or ch_num > 512:
                    continue

                # Detect console model hints in CSV metadata
                if "cl5" in name.lower() or "cl3" in name.lower():
                    console_model = name.upper()
                    continue

                tracks.append(Track(
                    channel=    ch_num,
                    name=       name,
                    track_type= TRACK_TYPE_MONO,
                    group=      GROUP_MISC,
                ))

            except (ValueError, IndexError):
                continue

        tracks.sort(key=lambda t: t.channel)
        return tracks, session_name, sample_rate, console_model

    def _parse_txt(
        self, content: str, path: Path
    ) -> tuple[list[Track], str, int, str]:
        """
        Parse plain text channel list.

        Handles formats like:
            Channel List - CL5
            1: Kick In
            2: Snare Top

        Or:
            1  Kick In
            2  Snare Top
        """
        tracks = []
        session_name = path.stem.replace("_", " ").title()
        sample_rate = 48000
        console_model = "CL/QL"

        # Detect console model from header
        for model in self.YAMAHA_MODELS:
            if model.lower() in content.lower()[:200]:
                console_model = model
                break

        # Extract session name from header
        name_match = re.search(r'(?:show|session|scene)\s*(?:name)?\s*[:\-]\s*(.+)', content, re.IGNORECASE)
        if name_match:
            session_name = name_match.group(1).strip()[:80]

        # Extract sample rate
        sr_match = re.search(r'(\d+)\s*khz', content, re.IGNORECASE)
        if sr_match:
            try:
                sample_rate = int(sr_match.group(1)) * 1000
            except ValueError:
                pass

        # Multiple channel list patterns
        patterns = [
            re.compile(r'^(\d{1,3})[:\.\s]\s*([A-Za-z][^\n\r]{1,40}?)\s*$', re.MULTILINE),
            re.compile(r'^(\d{1,3})\s{2,}([A-Za-z][^\n\r]{1,40}?)\s*$', re.MULTILINE),
        ]

        seen = set()
        candidates = []
        for pattern in patterns:
            matches = list(pattern.finditer(content))
            if len(matches) > len(candidates):
                candidates = matches

        garbage = {"channel", "input", "output", "name", "patch", "scene", "show",
                   "yamaha", "cl1", "cl3", "cl5", "ql1", "ql5", "date", "time"}

        for m in candidates:
            try:
                ch_num = int(m.group(1))
                name = m.group(2).strip()

                if ch_num < 1 or ch_num > 512 or ch_num in seen:
                    continue
                if not name or name.lower() in garbage:
                    continue

                seen.add(ch_num)
                tracks.append(Track(
                    channel=    ch_num,
                    name=       name,
                    track_type= TRACK_TYPE_MONO,
                    group=      GROUP_MISC,
                ))
            except (ValueError, IndexError):
                continue

        tracks.sort(key=lambda t: t.channel)
        return tracks, session_name, sample_rate, console_model

    def _build_buses(self, tracks: list[Track]) -> list[Bus]:
        """Auto-create buses from detected instrument groups."""
        groups_found = set(t.group for t in tracks)
        buses = []
        for group in groups_found:
            if group != GROUP_MISC:
                buses.append(Bus(
                    name=     f"{group.title()} Bus",
                    bus_type= "subgroup",
                    channels= [t.channel for t in tracks if t.group == group],
                    color=    GROUP_COLORS.get(group, "#2C3E50"),
                ))
        return buses
