"""
reaper_exporter.py — REAPER Project File Exporter

Generates valid REAPER .rpp project files from a Universal Session object.

REAPER uses a plain-text, bracket-structured project format (.rpp)
that is relatively easy to generate programmatically.

This exporter creates:
- One track per session channel
- Correct track order and names
- Folder/group structure based on instrument groups
- Track colors (REAPER packed-integer RGB format)
- Basic routing structure
- Recording-ready track configuration

REAPER .rpp format overview:
    <REAPER_PROJECT ...>
      <TRACK>
        NAME "Track Name"
        ...
      </TRACK>
    </REAPER_PROJECT>

Reference: https://wiki.cockos.com/wiki/index.php/Project_File_Format

Usage:
    from exporters.reaper.reaper_exporter import REAPERExporter

    exporter = REAPERExporter()
    output = exporter.export(session, "output/arena_show.rpp")
    print(f"Saved: {output}")
"""

import logging
from pathlib import Path
from models.session import Session
from models.track import Track, GROUP_MISC
from exporters.base_exporter import BaseExporter, ExporterError

logger = logging.getLogger(__name__)


def hex_to_reaper_color(hex_color: str) -> int:
    """
    Convert a hex color string to REAPER's packed BGR integer format.

    REAPER stores colors as a packed 32-bit integer in BGR order
    with the format: 0x00BBGGRR + a fixed offset.

    Parameters
    ----------
    hex_color : str
        Hex color string, e.g. "#C0392B" or "C0392B"

    Returns
    -------
    int
        REAPER color integer.
    """
    hex_color = hex_color.lstrip("#")
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        # REAPER packs colors as BGR with high bit set
        return (b << 16) | (g << 8) | r | 0x01000000
    except (ValueError, IndexError):
        return 0x01808080  # Default grey


class REAPERExporter(BaseExporter):
    """
    Exports a Universal Session to a REAPER .rpp project file.

    The generated project will have:
    - All tracks in console channel order
    - Tracks grouped by instrument type using REAPER folders
    - Track names matching the console exactly
    - Track colors assigned per instrument group
    - Stereo tracks configured as stereo items
    - Basic recording-ready configuration

    Example usage:
        exporter = REAPERExporter()
        path = exporter.export(session, "output/show.rpp")
    """

    # REAPER sample rate / tempo settings
    DEFAULT_BPM    = 120.0
    DEFAULT_METER  = "4/4"

    def __init__(self):
        super().__init__(daw_name="REAPER", file_extension=".rpp")

    def export(self, session: Session, output_path: str) -> str:
        """
        Export a Session to a REAPER .rpp project file.

        Parameters
        ----------
        session : Session
            The session to export.
        output_path : str
            Path for the output .rpp file.

        Returns
        -------
        str
            The path to the written .rpp file.
        """
        if not session.tracks:
            raise ExporterError("REAPERExporter: Session has no tracks to export.")

        self.logger.info(
            f"[INFO] REAPERExporter: Exporting '{session.session_name}' "
            f"({len(session.tracks)} tracks) → REAPER"
        )

        # Ensure output directory exists, fix extension
        out_path = self._ensure_output_dir(output_path)

        # Build the .rpp content
        rpp_lines = self._build_rpp(session)

        # Write to disk
        out_path.write_text("\n".join(rpp_lines), encoding="utf-8")

        self.logger.info(f"[SUCCESS] REAPERExporter: Written to '{out_path}'")
        return str(out_path)

    # ──────────────────────────────────────────────────────────────────
    # RPP construction
    # ──────────────────────────────────────────────────────────────────

    def _build_rpp(self, session: Session) -> list[str]:
        """
        Build the complete .rpp file as a list of text lines.

        The RPP format uses an indented bracket structure.
        We build it as a flat list of strings, then join with newlines.
        """
        lines = []

        # ── Project header ──────────────────────────────────────────
        lines += self._project_header(session)

        # ── Track blocks ────────────────────────────────────────────
        # We group tracks by instrument group and use REAPER folder tracks
        # to create a folder per group.

        groups_order = session.get_unique_groups()
        grouped: dict[str, list[Track]] = {}

        for group in groups_order:
            grouped[group] = session.get_tracks_in_group(group)

        for group in groups_order:
            group_tracks = grouped[group]
            if not group_tracks:
                continue

            # Create a folder track for this group (if more than 1 track)
            if len(group_tracks) > 1:
                lines += self._folder_track(group, group_tracks, is_start=True)
                for track in group_tracks:
                    lines += self._track_block(track, is_folder_child=True)
                lines += self._folder_end_track()
            else:
                # Solo track — no folder wrapper needed
                lines += self._track_block(group_tracks[0], is_folder_child=False)

        # ── Project footer ──────────────────────────────────────────
        lines.append("</REAPER_PROJECT>")

        return lines

    def _project_header(self, session: Session) -> list[str]:
        """Generate the REAPER project file header."""
        return [
            f'<REAPER_PROJECT 0.1 "6.0/linux64" 1600000000',
            f'  RIPPLE 0',
            f'  GROUPOVERRIDE 0 0 0',
            f'  AUTOXFADE 129',
            f'  ENVATTACH 3',
            f'  POOLEDENVATTACH 0',
            f'  MIXERUIFLAGS 11 48',
            f'  PEAKGAIN 1',
            f'  FEEDBACK 0',
            f'  PANLAW 1',
            f'  PROJOFFS 0 0 0',
            f'  MAXPROJLEN 0 600',
            f'  GRID 3199 8 1 8 1 0 0 0',
            f'  TIMEMODE 1 5 -1 30 0 0 -1',
            f'  VIDEO_CONFIG 0 0 256',
            f'  PANMODE 3',
            f'  CURSOR 0',
            f'  ZOOM 100 0 0',
            f'  VZOOMEX 6 0',
            f'  USE_REC_CFG 0',
            f'  RECMODE 1',
            f'  SMPTESYNC 0 30 100 40 1000 300 0 0 0 0 0',
            f'  LOOP 0',
            f'  LOOPGRAN 0 4',
            f'  RECORD_PATH "" ""',
            f'  <RECORD_CFG',
            f'    ZXZlAw==',
            f'  >',
            f'  <APPLYFX_CFG',
            f'  >',
            f'  RENDER_FILE ""',
            f'  RENDER_PATTERN ""',
            f'  RENDER_FMT 0 2 0',
            f'  RENDER_1X 0',
            f'  RENDER_RANGE 1 0 0 18 1000',
            f'  RENDER_RESAMPLE 3 0 1',
            f'  RENDER_ADDTOPROJ 0',
            f'  RENDER_STEMS 0',
            f'  RENDER_DITHER 0',
            f'  TIMELOCKMODE 1',
            f'  TEMPOENVLOCKMODE 1',
            f'  ITEMMIX 1',
            f'  DEFPITCHMODE 589824 0',
            f'  TAKELANE 1',
            f'  SAMPLERATE {session.sample_rate} 0 0',
            f'  <RENDER_CFG2',
            f'  >',
            f'  LOCK 0',
            f'  <METRONOME 6 2',
            f'    VOL 0.25 0.125',
            f'    FREQ 800 1600 1',
            f'    BEATLEN 4',
            f'    SAMPLES "" ""',
            f'    PATTERN 2863311530 2863311529',
            f'    MULT 1',
            f'  >',
            f'  GLOBAL_AUTO -1',
            f'  TEMPO 120 4 4',
            f'  PLAYBACKDEV 0',
            f'  RECDEV 0',
            f'  FILTERFLAG 1',
            f'  PROJNAME "{session.session_name}"',
            f'  AUTHOR ""',
            f'  <NOTES 0 2',
            f'    Generated by Live Console DAW Mirror',
            f'    Console: {session.console}',
            f'    Source: {session.source_file}',
            f'  >',
            f'  RENDER_STEMS 0',
        ]

    def _folder_track(
        self,
        group_name: str,
        tracks: list[Track],
        is_start: bool,
    ) -> list[str]:
        """
        Generate a REAPER folder track (group/bus track).

        In REAPER, folder tracks are regular tracks with:
          ISBUS 1 → marks as folder start
          Children follow immediately after
          A "folder end" track closes the folder
        """
        color = hex_to_reaper_color(tracks[0].color if tracks else "#444444")
        return [
            f'  <TRACK',
            f'    NAME "{group_name}"',
            f'    PEAKCOL {color}',
            f'    BEAT -1',
            f'    AUTOMODE 0',
            f'    VOLPAN 1 0 -1 -1 1',
            f'    MUTESOLO 0 0 0',
            f'    IPHASE 0',
            f'    PLAYOFFS 0 1',
            f'    ISBUS 1 -1',
            f'    BUSCOMP 0 0 0 0 0',
            f'    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0',
            f'    FREEMODE 0',
            f'    SEL 0',
            f'    REC 0 0 1 0 0 0 0 0',
            f'    VU 2',
            f'    TRACKHEIGHT 0 0 0 0 0 0',
            f'    INQ 0 0 0 0.5 100 0 0 100',
            f'    NCHAN 2',
            f'    FX 1',
            f'    TRACKID {{{self._generate_guid(group_name)}}}',
            f'  >',
        ]

    def _folder_end_track(self) -> list[str]:
        """Generate the closing 'folder end' track for a REAPER folder."""
        return [
            f'  <TRACK',
            f'    NAME ""',
            f'    BEAT -1',
            f'    AUTOMODE 0',
            f'    VOLPAN 1 0 -1 -1 1',
            f'    MUTESOLO 0 0 0',
            f'    IPHASE 0',
            f'    PLAYOFFS 0 1',
            f'    ISBUS 2 -1',
            f'    BUSCOMP 0 0 0 0 0',
            f'    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0',
            f'    FREEMODE 0',
            f'    SEL 0',
            f'    REC 0 0 1 0 0 0 0 0',
            f'    VU 2',
            f'    TRACKHEIGHT 0 0 0 0 0 0',
            f'    INQ 0 0 0 0.5 100 0 0 100',
            f'    NCHAN 2',
            f'    FX 1',
            f'  >',
        ]

    def _track_block(self, track: Track, is_folder_child: bool = False) -> list[str]:
        """
        Generate a REAPER track block for a single audio track.

        Parameters
        ----------
        track : Track
            The track to generate.
        is_folder_child : bool
            If True, this track is inside a folder and needs
            the ISBUS flag to signal it's a child.
        """
        color     = hex_to_reaper_color(track.color)
        nchan     = 2 if track.track_type == "stereo" else 2  # REAPER defaults to 2
        mute_val  = 1 if track.mute else 0
        isbus_val = "0 0" if not is_folder_child else "0 0"

        return [
            f'  <TRACK',
            f'    NAME "{track.name}"',
            f'    PEAKCOL {color}',
            f'    BEAT -1',
            f'    AUTOMODE 0',
            f'    VOLPAN 1 0 -1 -1 1',
            f'    MUTESOLO {mute_val} 0 0',
            f'    IPHASE 0',
            f'    PLAYOFFS 0 1',
            f'    ISBUS {isbus_val}',
            f'    BUSCOMP 0 0 0 0 0',
            f'    SHOWINMIX 1 0.6667 0.5 1 0.5 0 0 0',
            f'    FREEMODE 0',
            f'    SEL 0',
            f'    REC 0 0 1 0 0 0 0 0',
            f'    VU 2',
            f'    TRACKHEIGHT 0 0 0 0 0 0',
            f'    INQ 0 0 0 0.5 100 0 0 100',
            f'    NCHAN {nchan}',
            f'    FX 1',
            f'    TRACKID {{{self._generate_guid(track.name + str(track.channel))}}}',
            f'  >',
        ]

    def _generate_guid(self, seed: str) -> str:
        """
        Generate a deterministic GUID-like string for REAPER track IDs.
        Uses the seed string to keep GUIDs stable across re-exports.
        """
        import hashlib
        h = hashlib.md5(seed.encode()).hexdigest()
        return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}".upper()
