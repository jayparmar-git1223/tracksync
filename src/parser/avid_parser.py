"""
avid_parser.py — Avid S6L / VENUE Console Parser

Handles session data exported from Avid S6L and VENUE series consoles.

Avid S6L uses VENUE software which can export:
  - Channel name lists as .csv from the Input patchbay
  - Session reports as formatted .txt files
  - System configuration as .xml (VENUE System Config)

Supported consoles:
    S6L-24D, S6L-32D, S6L-48D
    S3L-X (with VENUE software)
    Pro Series (legacy VENUE)

Usage:
    from parser.avid_parser import AvidS6LParser
    parser = AvidS6LParser()
    session = parser.parse("venue_show.csv")
"""

import re
import csv
import logging
from io import StringIO
from pathlib import Path

from parser.base_parser import BaseParser, ParserError
from models.session import Session
from models.track import Track, TRACK_TYPE_MONO, GROUP_MISC, GROUP_COLORS
from models.bus import Bus
from parser.digico_parser import classify_track, detect_stereo_pairs

logger = logging.getLogger(__name__)


class AvidS6LParser(BaseParser):
    """
    Parser for Avid S6L / VENUE console session exports.

    Handles:
    - CSV channel name exports from VENUE Input patchbay
    - Plain text channel lists from VENUE session reports
    - VENUE XML system config files

    Example usage:
        parser = AvidS6LParser()
        session = parser.parse("venue_show.csv")
    """

    AVID_MODELS = [
        "S6L-24D", "S6L-32D", "S6L-48D",
        "S6L", "S3L", "S3L-X",
        "VENUE", "Pro Series", "D-Show",
    ]

    def __init__(self):
        super().__init__(console_name="Avid S6L/VENUE")

    def parse(self, file_path: str) -> Session:
        """
        Parse an Avid S6L / VENUE session export.

        Parameters
        ----------
        file_path : str
            Path to the session export file.

        Returns
        -------
        Session
            Universal Session object.
        """
        logger.info(f"[INFO] AvidS6LParser: Starting parse of '{file_path}'")
        path = self._validate_file(file_path)
        content = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix.lower()

        # Route to appropriate sub-parser
        if suffix == ".xml" or content.strip().startswith("<"):
            tracks, name, rate, model = self._parse_xml(content, path)
        elif suffix == ".csv" or self._looks_like_csv(content):
            tracks, name, rate, model = self._parse_csv(content, path)
        else:
            tracks, name, rate, model = self._parse_txt(content, path)

        if not tracks:
            raise ParserError(
                f"AvidS6LParser: No tracks found in '{file_path}'. "
                f"Verify this is a valid VENUE/S6L session export."
            )

        for t in tracks:
            if t.group == GROUP_MISC:
                t.group = classify_track(t.name)
                t.color = GROUP_COLORS.get(t.group, "#95A5A6")

        tracks = detect_stereo_pairs(tracks)
        buses  = self._auto_buses(tracks)

        session = Session(
            console=      f"Avid {model}",
            session_name= name,
            sample_rate=  rate,
            bit_depth=    24,
            source_file=  str(path),
            tracks=       tracks,
            buses=        buses,
        )

        logger.info(
            f"[SUCCESS] AvidS6LParser: '{name}' loaded — {len(tracks)} tracks"
        )
        return session

    # ──────────────────────────────────────────────────────────────────
    # Sub-parsers
    # ──────────────────────────────────────────────────────────────────

    def _parse_csv(self, content: str, path: Path):
        """
        Parse VENUE CSV channel export.

        VENUE CSV formats vary by export type:

        Input Patchbay CSV:
            Input#,Name,Source,Gain,Phantom,...
            1,Kick In,Local 1,0,OFF,...

        Simple channel list:
            CH,Name
            1,Kick In
            2,Snare Top
        """
        tracks = []
        session_name = path.stem.replace("_", " ").title()
        sample_rate  = 48000
        model        = "S6L"

        # Detect model from content
        for m in self.AVID_MODELS:
            if m.lower() in content[:400].lower():
                model = m
                break

        try:
            reader = csv.reader(StringIO(content))
            rows   = list(reader)
        except Exception:
            return [], session_name, sample_rate, model

        # Detect header row and name column index
        name_col = 1  # default: second column is name
        ch_col   = 0  # default: first column is channel number

        if rows:
            header = [h.strip().lower() for h in rows[0]]
            for i, h in enumerate(header):
                if h in ("name", "channel name", "label", "ch name"):
                    name_col = i
                if h in ("#", "ch", "channel", "input", "input#", "ch#"):
                    ch_col = i

        skip_headers = {"#", "ch", "channel", "input", "input#", "name",
                        "channel name", "label"}

        for row in rows:
            if not row or len(row) <= max(ch_col, name_col):
                continue
            ch_raw   = row[ch_col].strip()
            name_raw = row[name_col].strip() if name_col < len(row) else ""

            if ch_raw.lower() in skip_headers or not ch_raw:
                continue
            try:
                ch_num = int(ch_raw)
                if not name_raw or ch_num < 1 or ch_num > 512:
                    continue
                tracks.append(Track(channel=ch_num, name=name_raw))
            except ValueError:
                continue

        tracks.sort(key=lambda t: t.channel)
        return tracks, session_name, sample_rate, model

    def _parse_txt(self, content: str, path: Path):
        """Parse plain text VENUE session export."""
        tracks       = []
        session_name = path.stem.replace("_", " ").title()
        sample_rate  = 48000
        model        = "S6L"

        for m in self.AVID_MODELS:
            if m.lower() in content[:300].lower():
                model = m
                break

        sn_match = re.search(
            r'(?:show|session|scene)\s*(?:name)?\s*[:\-]\s*(.+)',
            content, re.IGNORECASE
        )
        if sn_match:
            session_name = sn_match.group(1).strip()[:80]

        sr_match = re.search(r'(\d+\.?\d*)\s*k?hz', content, re.IGNORECASE)
        if sr_match:
            try:
                r = float(sr_match.group(1))
                sample_rate = int(r * 1000) if r < 400 else int(r)
            except ValueError:
                pass

        pattern = re.compile(
            r'^(\d{1,3})[:\.\s]+([A-Za-z][^\n\r]{1,40}?)\s*$', re.MULTILINE
        )
        garbage = {"channel", "input", "name", "avid", "venue", "s6l",
                   "patch", "output", "bus", "date", "show"}
        seen = set()

        for m in pattern.finditer(content):
            try:
                ch  = int(m.group(1))
                name = m.group(2).strip()
                if ch < 1 or ch > 512 or ch in seen:
                    continue
                if not name or name.lower() in garbage:
                    continue
                seen.add(ch)
                tracks.append(Track(channel=ch, name=name))
            except (ValueError, IndexError):
                continue

        tracks.sort(key=lambda t: t.channel)
        return tracks, session_name, sample_rate, model

    def _parse_xml(self, content: str, path: Path):
        """Parse VENUE XML system configuration export."""
        import xml.etree.ElementTree as ET

        session_name = path.stem.replace("_", " ").title()
        sample_rate  = 48000
        model        = "S6L"
        tracks       = []

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return self._parse_txt(content, path)

        # VENUE XML varies by software version; try common patterns
        for ch_tag in ["Channel", "Input", "InputChannel", "Strip"]:
            elements = list(root.iter(ch_tag))
            if not elements:
                continue
            for i, elem in enumerate(elements):
                ch_num = None
                for attr in ["Number", "number", "Index", "CH", "id"]:
                    val = elem.get(attr)
                    if val:
                        try:
                            ch_num = int(val)
                            break
                        except ValueError:
                            pass
                if ch_num is None:
                    ch_num = i + 1

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

    def _looks_like_csv(self, content: str) -> bool:
        """Heuristic: does this look like a CSV file?"""
        lines = content[:500].strip().split("\n")
        comma_lines = sum(1 for l in lines[:10] if l.count(",") >= 1)
        return comma_lines >= 3

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
