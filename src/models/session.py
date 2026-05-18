"""
session.py — Universal Session Model

This is the MASTER SESSION MODEL for Live Console → DAW Mirror.

Every console parser produces a Session object.
Every DAW exporter reads from a Session object.

The Session is the universal translation layer between
live console sessions and DAW project files.

Architecture:

    Console Parser → Session → DAW Exporter
                         ↑
                   This file defines
                   the Session class.

The Session can be serialized to/from JSON for
saving, sharing, and debugging.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

# Import sub-models
from models.track import Track
from models.bus import Bus
from models.routing import Routing


@dataclass
class Session:
    """
    The Universal Session Model.

    This object is produced by a console parser and consumed by a DAW exporter.
    It is the single source of truth for all session data.

    Attributes
    ----------
    console : str
        The source console brand. e.g. "DiGiCo", "Yamaha", "Allen & Heath"
    session_name : str
        The name of the show/session.
    sample_rate : int
        The audio sample rate in Hz. e.g. 48000, 44100, 96000
    bit_depth : int
        The audio bit depth. e.g. 24, 32
    source_file : str
        The path to the original console session file that was parsed.
    tracks : List[Track]
        All tracks/channels in the session, in console channel order.
    groups : List[str]
        List of unique group names present in this session.
        e.g. ["DRUMS", "VOCALS", "GUITARS"]
    buses : List[Bus]
        All buses and subgroups in the session.
    routing : List[Routing]
        All routing assignments in the session.
    notes : str
        Any session-level notes or metadata.
    """

    console:      str          = "Unknown"
    session_name: str          = "Untitled Session"
    sample_rate:  int          = 48000
    bit_depth:    int          = 24
    source_file:  str          = ""
    tracks:       List[Track]  = field(default_factory=list)
    groups:       List[str]    = field(default_factory=list)
    buses:        List[Bus]    = field(default_factory=list)
    routing:      List[Routing] = field(default_factory=list)
    notes:        str          = ""

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    def get_tracks_in_group(self, group: str) -> List[Track]:
        """Returns all tracks belonging to a specific group."""
        return [t for t in self.tracks if t.group == group]

    def get_unique_groups(self) -> List[str]:
        """Returns a deduplicated, ordered list of group names."""
        seen = []
        for t in self.tracks:
            if t.group not in seen:
                seen.append(t.group)
        return seen

    def get_track_count(self) -> int:
        """Returns the total number of tracks in the session."""
        return len(self.tracks)

    # ------------------------------------------------------------------
    # Serialization: to/from dict and JSON
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        Converts the entire Session to a plain Python dictionary.

        This is the Universal Session JSON format.
        All exporters read from this structure.
        """
        return {
            "console":      self.console,
            "session_name": self.session_name,
            "sample_rate":  self.sample_rate,
            "bit_depth":    self.bit_depth,
            "source_file":  self.source_file,
            "track_count":  self.get_track_count(),
            "tracks":       [t.to_dict() for t in self.tracks],
            "groups":       self.get_unique_groups(),
            "buses":        [b.to_dict() for b in self.buses],
            "routing":      [r.to_dict() for r in self.routing],
            "notes":        self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """
        Reconstructs a Session from a plain Python dictionary.

        Use this to load a previously-saved Universal Session JSON
        back into memory for re-export to a different DAW.
        """
        return cls(
            console=      data.get("console", "Unknown"),
            session_name= data.get("session_name", "Untitled"),
            sample_rate=  data.get("sample_rate", 48000),
            bit_depth=    data.get("bit_depth", 24),
            source_file=  data.get("source_file", ""),
            tracks=       [Track.from_dict(t) for t in data.get("tracks", [])],
            buses=        [Bus.from_dict(b) for b in data.get("buses", [])],
            routing=      [Routing.from_dict(r) for r in data.get("routing", [])],
            notes=        data.get("notes", ""),
        )

    def save_json(self, path: str) -> None:
        """
        Saves the session as a Universal Session JSON file.

        Parameters
        ----------
        path : str
            The file path to write to. e.g. "output/arena_show.json"
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_json(cls, path: str) -> "Session":
        """
        Loads a Universal Session JSON file and returns a Session object.

        Parameters
        ----------
        path : str
            The path to the JSON file to load.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def __repr__(self) -> str:
        return (
            f"<Session console='{self.console}' "
            f"name='{self.session_name}' "
            f"tracks={self.get_track_count()}>"
        )
