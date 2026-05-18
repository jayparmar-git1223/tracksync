"""
rivage_parser.py — Yamaha RIVAGE PM Series Console Parser

Parses Yamaha RIVAGE PM scene/project files (.RIVAGEPM) into a
Universal Session object.

RIVAGE PM is Yamaha's top-of-the-line touring console series:
    RIVAGE PM10   — 144 input channels (96 assignable)
    RIVAGE PM7    — 72 input channels
    RIVAGE PM5    — 48 input channels
    RIVAGE PM3    — 24 input channels

File format: Yamaha MBDF (Musical Binary Data Format)
─────────────────────────────────────────────────────
The .RIVAGEPM file is a binary container with multiple zlib-compressed
data streams. The file structure is:

    [#YAMAHA MBDFProjectFile header]
    [MMS FIELD section index]
    [zlib stream 1: ProjectInfo]
    [zlib stream 2: Mixing parameters]
    [zlib stream 3: Mixing parameters (backup)]
    [zlib stream 4: Console parameters]
    ...
    [zlib stream N: ConsoleSetup — contains channel names]
    ...

Channel name extraction:
    The ConsoleSetup stream (identified by being the first large zlib
    stream ≥ 2 MB that contains 'ConsoleSetup') stores channel names
    in a fixed-stride binary array.

    Each channel record is 640 bytes wide.
    The name field is 16 bytes, null-padded, starting 8 bytes into
    each record (preceded by 8 x 0x01 "active" bytes).

    The array anchor is located by scanning for 8 × 0x01 bytes
    followed by a valid ASCII name, where the pattern repeats at
    640-byte stride for at least 10 channels.

Supported file extensions:
    .RIVAGEPM   — RIVAGE PM project file (all models)

Tested with:
    RIVAGE PM10 (firmware 4.x, 5.x)

Usage:
    from parser.rivage_parser import RIVAGEParser
    parser = RIVAGEParser()
    session = parser.parse("show.RIVAGEPM")
"""

import re
import zlib
import struct
import logging
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

# ─────────────────────────────────────────────────────────────────────
# Format constants (reverse-engineered from RIVAGE PM10 firmware 4.x)
# ─────────────────────────────────────────────────────────────────────

MBDF_MAGIC        = b"#YAMAHA MBDFProjectFile"
CHANNEL_STRIDE    = 640        # bytes per input channel record in ConsoleSetup
NAME_OFFSET       = 8          # bytes from start of record to name field
NAME_MAX_LEN      = 16         # max channel name length (null-padded)
ANCHOR_PREFIX     = b"\x01" * 8  # 8 x 0x01 bytes before each channel name
MIN_VALID_NAMES   = 8          # minimum alpha-starting names to accept an anchor

# Zlib magic bytes that identify the start of a compressed stream
ZLIB_HEADERS      = {0x789C, 0x78DA, 0x785E, 0x78ED, 0x7801}

# Model identifiers found in the file header
RIVAGE_MODELS     = ["PM10", "PM7", "PM5", "PM3"]

# Channel counts per model (max assignable input channels)
MODEL_CH_COUNT    = {
    "PM10": 96,
    "PM7":  72,
    "PM5":  48,
    "PM3":  24,
}


class RIVAGEParser(BaseParser):
    """
    Parser for Yamaha RIVAGE PM series console project files.

    Extracts all user-assigned channel names from the RIVAGE PM
    binary project file format (MBDF) and returns a Universal Session.

    The parser:
      1. Validates the MBDF file header
      2. Finds all zlib-compressed data streams in the file
      3. Decompresses and identifies the ConsoleSetup stream
      4. Locates the channel name array via anchor pattern matching
      5. Extracts up to 96 channel names at 640-byte stride
      6. Auto-classifies tracks into instrument groups
      7. Detects stereo pairs by L/R naming convention

    Supported console models:
        RIVAGE PM10, PM7, PM5, PM3

    Example usage:
        parser = RIVAGEParser()
        session = parser.parse("show.RIVAGEPM")
        print(f"Loaded {session.get_track_count()} tracks from {session.console}")
    """

    def __init__(self):
        super().__init__(console_name="Yamaha RIVAGE PM")

    def parse(self, file_path: str) -> Session:
        """
        Parse a Yamaha RIVAGE PM project file.

        Parameters
        ----------
        file_path : str
            Path to the .RIVAGEPM file.

        Returns
        -------
        Session
            Fully-populated Universal Session object.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ParserError
            If the file is not a valid RIVAGE PM project,
            or if no channel names can be extracted.
        """
        logger.info(f"[INFO] RIVAGEParser: Starting parse of '{file_path}'")

        path = self._validate_file(file_path)
        raw  = path.read_bytes()

        # Step 1 — Validate MBDF magic header
        if not raw.startswith(MBDF_MAGIC):
            raise ParserError(
                f"RIVAGEParser: '{file_path}' is not a valid Yamaha MBDF file. "
                f"Expected header: {MBDF_MAGIC!r}"
            )

        logger.info("[INFO] RIVAGEParser: Valid MBDF header confirmed")

        # Step 2 — Extract console model and session name
        model       = self._extract_model(raw)
        session_name = path.stem.replace("_", " ").replace("-", " ").title()
        max_channels = MODEL_CH_COUNT.get(model, 96)

        logger.info(f"[INFO] RIVAGEParser: Console model: RIVAGE {model}, max_channels={max_channels}")

        # Step 3 — Find and decompress all zlib streams
        streams = self._find_zlib_streams(raw)
        logger.info(f"[INFO] RIVAGEParser: Found {len(streams)} zlib streams")

        # Step 4 — Find the ConsoleSetup stream (contains channel names)
        setup_data = self._find_setup_stream(streams)
        if setup_data is None:
            raise ParserError(
                f"RIVAGEParser: Could not find ConsoleSetup stream in '{file_path}'. "
                f"The file may be corrupt or use an unsupported firmware version."
            )

        logger.info(f"[INFO] RIVAGEParser: ConsoleSetup stream: {len(setup_data):,} bytes")

        # Step 5 — Extract sample rate
        sample_rate = self._extract_sample_rate(setup_data)

        # Step 6 — Extract channel names
        ch_names = self._extract_channel_names(setup_data, max_channels)

        if not ch_names:
            # Fallback: try all streams
            logger.warning("[WARNING] RIVAGEParser: ConsoleSetup gave no names, trying all streams...")
            for stream_data in streams:
                ch_names = self._extract_channel_names(stream_data, max_channels)
                if ch_names:
                    logger.info(f"[INFO] RIVAGEParser: Found names in fallback stream")
                    break

        if not ch_names:
            raise ParserError(
                f"RIVAGEParser: No channel names found in '{file_path}'. "
                f"The session may use all default names, or the format differs "
                f"from the supported RIVAGE PM firmware versions."
            )

        logger.info(f"[INFO] RIVAGEParser: Extracted {len(ch_names)} named channels")

        # Step 7 — Build Track objects
        tracks = self._build_tracks(ch_names)

        # Step 8 — Auto-classify and detect stereo pairs
        for track in tracks:
            if track.group == GROUP_MISC:
                track.group = classify_track(track.name)
                track.color = GROUP_COLORS.get(track.group, "#95A5A6")

        tracks = detect_stereo_pairs(tracks)

        # Step 9 — Build buses from groups
        buses = self._build_buses(tracks)

        session = Session(
            console=       f"Yamaha RIVAGE {model}",
            session_name=  session_name,
            sample_rate=   sample_rate,
            bit_depth=     24,
            source_file=   str(path),
            tracks=        tracks,
            buses=         buses,
        )

        logger.info(
            f"[SUCCESS] RIVAGEParser: '{session_name}' loaded — "
            f"{len(tracks)} tracks, {len(buses)} buses, {sample_rate} Hz"
        )
        return session

    # ──────────────────────────────────────────────────────────────────
    # Private methods
    # ──────────────────────────────────────────────────────────────────

    def _extract_model(self, raw: bytes) -> str:
        """Extract the RIVAGE PM model identifier from the file header."""
        for model in RIVAGE_MODELS:
            if model.encode() in raw[:200]:
                return model
        return "PM10"  # safe default

    def _find_zlib_streams(self, raw: bytes) -> list[bytes]:
        """
        Find and decompress all zlib streams in the MBDF file.

        Returns a list of decompressed byte strings, sorted by
        decompressed size (largest first, as the ConsoleSetup stream
        is typically one of the largest).

        Only streams that decompress successfully to > 10 KB are returned.
        """
        streams = []
        seen_offsets = set()

        for i in range(len(raw) - 2):
            word = struct.unpack_from(">H", raw, i)[0]
            if word not in ZLIB_HEADERS:
                continue
            if i in seen_offsets:
                continue

            try:
                decompressed = zlib.decompress(raw[i:])
                size = len(decompressed)
                if size > 10_000:
                    streams.append((size, i, decompressed))
                    seen_offsets.add(i)
                    # Skip ahead past this stream's compressed data
                    # (approximate — next stream will be found naturally)
            except zlib.error:
                pass

        # Sort by decompressed size, largest first
        streams.sort(key=lambda x: -x[0])
        logger.debug(f"[DEBUG] RIVAGEParser: Streams by size: {[(s, hex(o)) for s,o,_ in streams[:8]]}")

        return [data for _, _, data in streams]

    def _find_setup_stream(self, streams: list[bytes]) -> Optional[bytes]:
        """
        Identify the ConsoleSetup stream from the list of decompressed streams.

        The ConsoleSetup stream:
        - Is typically 2–4 MB decompressed
        - Contains the string b'ConsoleSetup' or b'RIVAGE' near the start
        - Contains the channel name anchor pattern at the expected offset

        Falls back to trying all large streams (> 500 KB) if no marker found.
        """
        MARKERS = [b"ConsoleSetup", b"stup", b"Console\x00\x00\x00"]

        # Primary: find stream containing ConsoleSetup marker
        for stream in streams:
            for marker in MARKERS:
                pos = stream.find(marker)
                if 0 <= pos < 5000:
                    logger.debug(
                        f"[DEBUG] RIVAGEParser: ConsoleSetup stream found "
                        f"({len(stream):,} bytes, marker '{marker!r}' at 0x{pos:x})"
                    )
                    return stream

        # Fallback: return the largest stream ≥ 2 MB
        for stream in streams:
            if len(stream) >= 2_000_000:
                logger.debug(
                    f"[DEBUG] RIVAGEParser: Using largest stream as fallback "
                    f"({len(stream):,} bytes)"
                )
                return stream

        return None

    def _extract_sample_rate(self, data: bytes) -> int:
        """
        Extract the sample rate from a decompressed MBDF stream.

        RIVAGE PM stores sample rate as the string "INT48000" or "INT96000"
        in the ConsoleSetup stream.
        """
        if b"INT96000" in data:
            return 96000
        if b"INT88200" in data:
            return 88200
        # Default: 48 kHz (universal in live sound)
        return 48000

    def _extract_channel_names(
        self, data: bytes, max_channels: int = 96
    ) -> dict[int, str]:
        """
        Extract channel names from a decompressed MBDF setup stream.

        Locates the channel name array by scanning for the 8 × 0x01
        anchor pattern that precedes each channel name field.

        The anchor that produces the most valid, alpha-starting channel
        names at CHANNEL_STRIDE (640) byte intervals is chosen.

        Parameters
        ----------
        data : bytes
            Decompressed MBDF stream data.
        max_channels : int
            Maximum number of channels to extract.

        Returns
        -------
        dict[int, str]
            Mapping of 1-based channel number → channel name.
            Only channels with non-empty, non-default names are included.
        """
        best_anchor = self._find_best_anchor(data, max_channels)
        if best_anchor < 0:
            return {}

        name_start = best_anchor + len(ANCHOR_PREFIX)
        ch_names   = {}

        for i in range(max_channels):
            pos = name_start + i * CHANNEL_STRIDE
            if pos + NAME_MAX_LEN > len(data):
                break

            raw_name = data[pos : pos + NAME_MAX_LEN]
            null     = raw_name.find(b"\x00")
            if null < 0:
                null = NAME_MAX_LEN

            name = raw_name[:null].decode("ascii", errors="replace").strip()

            # Filter out empty, default, and garbage names
            if self._is_valid_name(name):
                ch_names[i + 1] = name

        return ch_names

    def _find_best_anchor(self, data: bytes, max_channels: int) -> int:
        """
        Find the byte offset of the best channel name array anchor.

        Scans for all occurrences of ANCHOR_PREFIX (8 × 0x01) and scores
        each based on how many valid, alpha-starting names appear at
        CHANNEL_STRIDE intervals from that anchor.

        Returns the offset of the highest-scoring anchor, or -1 if none found.
        """
        best_offset = -1
        best_score  = 0

        for m in re.finditer(re.escape(ANCHOR_PREFIX), data):
            anchor_pos = m.start()
            name_pos   = m.end()

            alpha_count = 0
            any_count   = 0

            for i in range(min(max_channels, 30)):
                pos = name_pos + i * CHANNEL_STRIDE
                if pos + NAME_MAX_LEN > len(data):
                    break

                raw = data[pos : pos + NAME_MAX_LEN]
                null = raw.find(b"\x00")
                if null < 0:
                    null = NAME_MAX_LEN
                part = raw[:null]

                if 2 <= len(part) <= 15 and all(0x20 <= b <= 0x7E for b in part):
                    any_count += 1
                    if 65 <= part[0] <= 122:  # starts with A-z
                        alpha_count += 1

            # Score: alpha names count double
            score = alpha_count * 2 + any_count

            if score > best_score and alpha_count >= 3:
                best_score  = score
                best_offset = anchor_pos

        if best_offset >= 0:
            logger.debug(
                f"[DEBUG] RIVAGEParser: Best anchor at 0x{best_offset:08x} "
                f"(score={best_score})"
            )

        return best_offset

    def _is_valid_name(self, name: str) -> bool:
        """
        Return True if a name string is a valid, user-assigned channel name.

        Filters out:
        - Empty strings
        - Default RIVAGE names (CH 01, Input 1, etc.)
        - Names made entirely of dashes or dots
        - Very short single-char names
        - Names containing non-printable characters
        - Known schema/metadata keywords
        """
        if not name or len(name) < 2:
            return False

        # Filter garbage/default patterns
        if re.match(r"^-+$", name):          return False
        if re.match(r"^\d+$", name):         return False
        if re.match(r"^CH\s*\d+$", name):    return False
        if re.match(r"^Input\s*\d+$", name): return False
        if name.lower() in {
            "undefined", "noname", "empty", "unused",
            "ch", "input", "output", "bus", "mix",
        }:
            return False

        # Must contain at least one alphabetic character
        if not any(c.isalpha() for c in name):
            return False

        # Must be printable ASCII
        if not all(0x20 <= ord(c) <= 0x7E for c in name):
            return False

        return True

    def _build_tracks(self, ch_names: dict[int, str]) -> list[Track]:
        """Build Track objects from the extracted channel name dictionary."""
        tracks = []
        for channel, name in sorted(ch_names.items()):
            tracks.append(Track(
                channel=    channel,
                name=       name,
                track_type= TRACK_TYPE_MONO,
                group=      GROUP_MISC,
                output=     "Main LR",
            ))
        return tracks

    def _build_buses(self, tracks: list[Track]) -> list[Bus]:
        """Auto-create buses from detected instrument groups."""
        groups = {}
        for t in tracks:
            groups.setdefault(t.group, []).append(t.channel)

        buses = []
        for group, channels in groups.items():
            if group != GROUP_MISC and len(channels) >= 2:
                buses.append(Bus(
                    name=     f"{group.title()} Bus",
                    bus_type= "subgroup",
                    channels= sorted(channels),
                    color=    GROUP_COLORS.get(group, "#2C3E50"),
                ))
        return buses
