"""
digico_parser.py — DiGiCo Session Report Parser

Parses DiGiCo console session report files (.rtf format) into
a Universal Session object.

DiGiCo consoles (SD5, SD7, SD10, SD12, SD Rack, etc.) can export
session reports as RTF files containing all channel names, routing,
bus assignments, and session metadata.

This parser:
1. Reads the .rtf file
2. Strips RTF markup to get plain text
3. Extracts channel/track information using regex
4. Auto-classifies tracks into instrument groups
5. Detects stereo pairs
6. Returns a fully-populated Session object

Usage:
    from parser.digico_parser import DiGiCoParser

    parser = DiGiCoParser()
    session = parser.parse("show_report.rtf")
    print(session.tracks)
"""

import re
import logging
from pathlib import Path
from typing import Optional

# striprtf converts .rtf files to plain text
try:
    from striprtf.striprtf import rtf_to_text
except ImportError:
    rtf_to_text = None

from parser.base_parser import BaseParser, ParserError
from models.session import Session
from models.track import (
    Track,
    TRACK_TYPE_MONO,
    TRACK_TYPE_STEREO,
    GROUP_DRUMS,
    GROUP_VOCALS,
    GROUP_GUITARS,
    GROUP_KEYS,
    GROUP_BASS,
    GROUP_BRASS,
    GROUP_STRINGS,
    GROUP_EFFECTS,
    GROUP_MISC,
    GROUP_COLORS,
)
from models.bus import Bus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Auto-classification keyword dictionaries
#
# These keyword lists are used to automatically detect which instrument
# group a track belongs to based on its name. Add more keywords as
# needed for your specific workflow.
# ─────────────────────────────────────────────────────────────────────

GROUP_KEYWORDS: dict[str, list[str]] = {
    GROUP_DRUMS: [
        "kick", "kik", "bd", "bass drum",
        "snare", "sn",
        "tom", "t1", "t2", "t3", "t4",
        "hihat", "hi hat", "hh", "hat",
        "ride",
        "crash",
        "cymbal", "cym",
        "overhead", "oh ", "oh_", "ovhd", "over",
        "room", "amb", "ambient",
        "drum", "perc",
    ],
    GROUP_VOCALS: [
        "vox", "vocal", "voc",
        "lead", "ld vox", "ldvox",
        "bgv", "bv", "back", "backing",
        "choir", "adlib",
        "talk", "talkback", "speak",
    ],
    GROUP_GUITARS: [
        "gtr", "guitar", "git",
        "elec", "electric",
        "acoustic", "acou",
        "bass gtr", "bass guitar",
    ],
    GROUP_BASS: [
        "bass", "di", "d.i.",
        "sub bass",
    ],
    GROUP_KEYS: [
        "keys", "key", "piano", "pno",
        "organ", "org", "hammond", "b3",
        "synth", "nord", "moog", "prophet",
        "strings", "pad",
        "rhodes", "clav", "wurly",
    ],
    GROUP_BRASS: [
        "brass", "horn",
        "trumpet", "tpt", "trp",
        "trombone", "tbn",
        "sax", "saxophone", "alto", "tenor", "bari",
        "flugelhorn",
    ],
    GROUP_EFFECTS: [
        "fx", "reverb", "delay", "echo",
        "return", "aux ret", "stem",
        "playback", "tape", "track",
        "loop",
    ],
}


def classify_track(name: str) -> str:
    """
    Auto-detect the instrument group for a track based on its name.

    Checks the track name against each group's keyword list.
    Returns the first matching group, or GROUP_MISC if no match.

    Parameters
    ----------
    name : str
        The track name from the console (e.g. "Kick In", "BGV 1")

    Returns
    -------
    str
        A group constant like "DRUMS", "VOCALS", etc.
    """
    name_lower = name.lower().strip()

    for group, keywords in GROUP_KEYWORDS.items():
        for keyword in keywords:
            # Check if the keyword appears as a word boundary match
            # e.g. "kick" matches "Kick In" but not "Chicken"
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, name_lower):
                return group

    # Special case: two-letter abbreviations without word boundary
    # e.g. "OH L", "OH R" — "OH" alone won't match the word boundary
    for group, keywords in GROUP_KEYWORDS.items():
        for keyword in keywords:
            if name_lower.startswith(keyword):
                return group

    return GROUP_MISC


def detect_stereo_pairs(tracks: list[Track]) -> list[Track]:
    """
    Detect and mark stereo pairs in a track list.

    Looks for common naming conventions:
    - "OH L" / "OH R"
    - "Kick L" / "Kick R"
    - "Keys L" / "Keys R"
    - "GTR 1L" / "GTR 1R"

    Marks paired tracks with their partner's channel number
    and sets track_type to TRACK_TYPE_STEREO.

    Parameters
    ----------
    tracks : list[Track]
        The track list to process.

    Returns
    -------
    list[Track]
        The same track list with stereo pairs annotated.
    """
    # Build a lookup: name → track
    name_map = {t.name.strip(): t for t in tracks}

    # Common L/R suffix patterns
    left_patterns  = [" L", " l", "_L", "_l", "L", "l", " Left", " left"]
    right_patterns = [" R", " r", "_R", "_r", "R", "r", " Right", " right"]

    for track in tracks:
        name = track.name.strip()

        # Skip already-paired tracks
        if track.stereo_pair is not None:
            continue

        # Try to find a matching R partner for this L track
        for l_suffix, r_suffix in zip(left_patterns, right_patterns):
            if name.endswith(l_suffix):
                base = name[: -len(l_suffix)]
                partner_name = base + r_suffix

                if partner_name in name_map:
                    partner = name_map[partner_name]
                    # Mark the pair
                    track.stereo_pair   = partner.channel
                    partner.stereo_pair = track.channel
                    track.track_type    = TRACK_TYPE_STEREO
                    partner.track_type  = TRACK_TYPE_STEREO
                    logger.info(
                        f"[INFO] Stereo pair detected: "
                        f"ch{track.channel} '{track.name}' ↔ "
                        f"ch{partner.channel} '{partner.name}'"
                    )
                    break

    return tracks


class DiGiCoParser(BaseParser):
    """
    Parser for DiGiCo console session report files (.rtf).

    DiGiCo consoles export session reports as RTF documents.
    This parser extracts all channel and routing data from those reports.

    Supported console models:
        SD5, SD7, SD10, SD12, SD11, SD8, SD9, SD-Rack
        (Any DiGiCo that exports RTF session reports)

    Example usage:
        parser = DiGiCoParser()
        session = parser.parse("/path/to/show_report.rtf")
        print(f"Loaded {session.get_track_count()} tracks")
    """

    def __init__(self):
        super().__init__(console_name="DiGiCo")

    def parse(self, file_path: str) -> Session:
        """
        Parse a DiGiCo RTF session report file.

        Parameters
        ----------
        file_path : str
            Path to the .rtf session report file.

        Returns
        -------
        Session
            A fully-populated Universal Session object.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ParserError
            If the file cannot be decoded or parsed.
        """
        logger.info(f"[INFO] DiGiCoParser: Starting parse of '{file_path}'")

        # Step 1: Validate the file exists and is readable
        path = self._validate_file(file_path)

        # Step 2: Read raw RTF content
        raw_rtf = self._read_rtf_file(path)

        # Step 3: Convert RTF → plain text
        plain_text = self._strip_rtf(raw_rtf)

        if not plain_text or len(plain_text.strip()) < 10:
            raise ParserError(
                f"DiGiCoParser: Could not extract readable text from '{file_path}'. "
                f"The file may be corrupt or in an unsupported RTF format."
            )

        logger.info(f"[INFO] DiGiCoParser: Extracted {len(plain_text)} chars of plain text")

        # Step 4: Extract session metadata
        session_name = self._extract_session_name(plain_text, path)
        sample_rate  = self._extract_sample_rate(plain_text)

        # Step 5: Extract all channels/tracks
        tracks = self._extract_channels(plain_text)

        if not tracks:
            logger.warning(
                "[WARNING] DiGiCoParser: No tracks found. "
                "The report format may differ from expected. "
                "Attempting fallback extraction..."
            )
            tracks = self._fallback_extract(plain_text)

        if not tracks:
            raise ParserError(
                f"DiGiCoParser: No tracks could be extracted from '{file_path}'. "
                f"Please check that this is a valid DiGiCo session report."
            )

        logger.info(f"[INFO] DiGiCoParser: Found {len(tracks)} tracks")

        # Step 6: Auto-classify tracks into groups
        for track in tracks:
            if track.group == GROUP_MISC:
                track.group = classify_track(track.name)
                track.color = GROUP_COLORS.get(track.group, "#95A5A6")

        # Step 7: Detect stereo pairs
        tracks = detect_stereo_pairs(tracks)

        # Step 8: Extract buses
        buses = self._extract_buses(plain_text, tracks)

        # Step 9: Build and return the Session
        session = Session(
            console=      "DiGiCo",
            session_name= session_name,
            sample_rate=  sample_rate,
            bit_depth=    24,
            source_file=  str(path),
            tracks=       tracks,
            buses=        buses,
        )

        logger.info(
            f"[SUCCESS] DiGiCoParser: Session '{session_name}' loaded — "
            f"{len(tracks)} tracks, {len(buses)} buses"
        )

        return session

    # ──────────────────────────────────────────────────────────────────
    # Private methods
    # ──────────────────────────────────────────────────────────────────

    def _read_rtf_file(self, path: Path) -> str:
        """Read raw RTF bytes from file, trying multiple encodings."""
        encodings = ["utf-8", "latin-1", "cp1252", "ascii"]

        for encoding in encodings:
            try:
                return path.read_text(encoding=encoding, errors="replace")
            except Exception:
                continue

        # Last resort: read as bytes and decode with replace
        return path.read_bytes().decode("latin-1", errors="replace")

    def _strip_rtf(self, raw_rtf: str) -> str:
        """
        Convert RTF markup to plain text.

        Uses the striprtf library if available.
        Falls back to a basic regex-based RTF stripper.
        """
        if rtf_to_text:
            try:
                text = rtf_to_text(raw_rtf)
                # Clean up excessive whitespace
                text = re.sub(r'\n{3,}', '\n\n', text)
                return text
            except Exception as e:
                logger.warning(f"[WARNING] striprtf failed: {e}. Using fallback RTF stripper.")

        # Fallback: manual RTF stripping with regex
        return self._manual_rtf_strip(raw_rtf)

    def _manual_rtf_strip(self, rtf: str) -> str:
        """
        Basic RTF-to-text conversion using regex.
        Used as a fallback when striprtf is unavailable or fails.

        Preserves newlines so multi-space channel patterns remain detectable.
        """
        text = rtf

        # Remove RTF control words (e.g. \rtf1, \ansi, \f0, \fs20)
        # but preserve newlines
        text = re.sub(r'\\[a-z*]+\-?\d*[ ]?', '', text)

        # Remove curly braces (RTF group delimiters)
        text = re.sub(r'[{}]', '', text)

        # Remove remaining lone backslashes
        text = re.sub(r'\\', '', text)

        # Collapse multiple spaces on a single line to double-space
        # (preserves the "1   Kick In" format after RTF stripping)
        lines = []
        for line in text.split('\n'):
            # Collapse 3+ spaces to 2 to keep structure, strip edges
            line = re.sub(r' {3,}', '   ', line)
            lines.append(line)

        return '\n'.join(lines).strip()

    def _extract_session_name(self, text: str, path: Path) -> str:
        """
        Attempt to extract the session name from the report text.
        Falls back to the filename if not found.
        """
        # DiGiCo reports often have "Show Name:" or "Session:" fields
        patterns = [
            r'show\s+name\s*[:\-]\s*(.+)',
            r'session\s+name\s*[:\-]\s*(.+)',
            r'session\s*[:\-]\s*(.+)',
            r'show\s*[:\-]\s*(.+)',
            r'console\s+name\s*[:\-]\s*(.+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()[:80]  # Limit length
                if name:
                    return name

        # Fall back to the filename without extension
        return path.stem.replace("_", " ").replace("-", " ").title()

    def _extract_sample_rate(self, text: str) -> int:
        """
        Extract the sample rate from the session report.
        Returns 48000 as the default if not found.
        """
        # Look for sample rate mentions like "48kHz", "96kHz", "44.1kHz"
        pattern = r'(\d+\.?\d*)\s*k?hz'
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            rate_str = match.group(1)
            try:
                rate = float(rate_str)
                # Handle kHz values (e.g., "48" → 48000, "44.1" → 44100)
                if rate < 400:
                    rate = int(rate * 1000)
                else:
                    rate = int(rate)
                # Validate it's a sensible sample rate
                if rate in (44100, 48000, 88200, 96000, 176400, 192000):
                    return rate
            except ValueError:
                pass

        logger.info("[INFO] Sample rate not found in report, defaulting to 48000 Hz")
        return 48000

    def _extract_channels(self, text: str) -> list[Track]:
        """
        Extract channel/track information from DiGiCo session report text.

        DiGiCo reports typically have a channel list section with entries like:
            1   Kick In
            2   Snare Top
            3   OH L
            4   OH R

        Or in a table format with additional columns for output, bus, etc.

        This method tries multiple patterns to handle different report formats.

        Returns
        -------
        list[Track]
            List of Track objects in channel order.
        """
        tracks = []

        # ── Pattern 1: "  1   Track Name" (number + 2+ spaces + name) ──
        # Original DiGiCo report format (before RTF strip)
        pattern_1 = re.compile(
            r'^\s*(\d{1,3})\s{2,}([A-Za-z0-9][^\n\r]{1,40}?)(?:\s{2,}|\t|$)',
            re.MULTILINE
        )

        # ── Pattern 2: "1 Track Name" (number + 1+ space + name, per line) ──
        # Common after RTF stripping collapses whitespace
        pattern_2 = re.compile(
            r'^(\d{1,3})\s+([A-Za-z][A-Za-z0-9 _\-\.\/\#]{1,39}?)\s*$',
            re.MULTILINE
        )

        # ── Pattern 3: "CH 1 : Track Name" ──
        pattern_3 = re.compile(
            r'ch(?:annel)?\s*(\d{1,3})\s*[:\-]\s*([A-Za-z0-9][^\n\r]{1,40})',
            re.MULTILINE | re.IGNORECASE
        )

        # ── Pattern 4: Tab-separated "1\tKick In" ──
        pattern_4 = re.compile(
            r'^(\d{1,3})\t([^\t\n\r]{2,40})',
            re.MULTILINE
        )

        # Try each pattern and use the one with the most valid results
        candidates = []
        for pattern in [pattern_1, pattern_2, pattern_3, pattern_4]:
            matches = list(pattern.finditer(text))
            if len(matches) > len(candidates):
                candidates = matches

        if not candidates:
            return []

        seen_channels = set()
        for match in candidates:
            try:
                ch_num = int(match.group(1))
                ch_name = match.group(2).strip()

                if ch_num < 1 or ch_num > 512:
                    continue
                if len(ch_name) < 2:
                    continue
                if ch_num in seen_channels:
                    continue
                if self._is_garbage_name(ch_name):
                    continue

                seen_channels.add(ch_num)
                tracks.append(Track(
                    channel=    ch_num,
                    name=       ch_name,
                    track_type= TRACK_TYPE_MONO,
                    group=      GROUP_MISC,
                ))

            except (ValueError, IndexError):
                continue

        tracks.sort(key=lambda t: t.channel)
        return tracks

    def _fallback_extract(self, text: str) -> list[Track]:
        """
        Last-resort track extraction.

        Tries to find any numbered list of names in the document,
        even if the format is completely non-standard.
        """
        logger.info("[INFO] DiGiCoParser: Running fallback extraction...")

        tracks = []
        # Very broad pattern: any line starting with a number and having text
        pattern = re.compile(r'^(\d{1,3})[.\s:]+([A-Za-z][^\n\r]{1,50})', re.MULTILINE)
        matches = list(pattern.finditer(text))

        seen = set()
        for m in matches:
            ch = int(m.group(1))
            name = m.group(2).strip()
            if ch < 1 or ch > 256 or ch in seen or self._is_garbage_name(name):
                continue
            seen.add(ch)
            tracks.append(Track(channel=ch, name=name))

        tracks.sort(key=lambda t: t.channel)
        return tracks

    def _is_garbage_name(self, name: str) -> bool:
        """
        Returns True if the extracted name looks like RTF garbage or
        a section header rather than a real track name.
        """
        name_lower = name.lower().strip()

        garbage_keywords = [
            "page", "copyright", "version", "report", "digico",
            "channel", "input", "output", "bus", "aux", "matrix",
            "master", "console", "session", "show", "total",
            "date", "time", "operator",
        ]

        if any(name_lower.startswith(g) for g in garbage_keywords):
            return True

        # Skip if the name is all numbers or symbols
        if re.match(r'^[\d\s\-_.]+$', name):
            return True

        # Skip very short names (likely garbage)
        if len(name.strip()) < 2:
            return True

        return False

    def _extract_buses(self, text: str, tracks: list[Track]) -> list[Bus]:
        """
        Extract bus/subgroup information from the session report.

        Creates standard buses based on detected groups if explicit
        bus information isn't found in the report.
        """
        buses = []

        # Try to find explicit bus names in the report
        bus_pattern = re.compile(
            r'(?:bus|group|subgroup|aux)\s*(\d+)\s*[:\-]\s*([^\n\r]+)',
            re.IGNORECASE
        )

        found_buses = {}
        for match in bus_pattern.finditer(text):
            bus_name = match.group(2).strip()
            if bus_name and not self._is_garbage_name(bus_name):
                found_buses[bus_name] = Bus(name=bus_name, bus_type="subgroup")

        if found_buses:
            buses = list(found_buses.values())
        else:
            # Auto-create buses from detected groups
            groups_found = set(t.group for t in tracks)
            for group in groups_found:
                if group != GROUP_MISC:
                    bus = Bus(
                        name=     f"{group.title()} Bus",
                        bus_type= "subgroup",
                        channels= [t.channel for t in tracks if t.group == group],
                        color=    GROUP_COLORS.get(group, "#2C3E50"),
                    )
                    buses.append(bus)

        return buses
