"""
track.py — Track data model

Represents a single audio channel/track from a live console session.
This is one of the core building blocks of the Universal Session JSON.

A Track maps directly to a single fader/channel on the live console,
and will become a single track in the output DAW session.
"""

from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------
# Track type constants
# These mirror the channel types found on live consoles.
# --------------------------------------------------------------------
TRACK_TYPE_MONO   = "mono"
TRACK_TYPE_STEREO = "stereo"
TRACK_TYPE_AUX    = "aux"
TRACK_TYPE_GROUP  = "group"
TRACK_TYPE_MASTER = "master"
TRACK_TYPE_FX     = "fx"

# --------------------------------------------------------------------
# Auto-detected instrument group labels
# --------------------------------------------------------------------
GROUP_DRUMS   = "DRUMS"
GROUP_VOCALS  = "VOCALS"
GROUP_GUITARS = "GUITARS"
GROUP_KEYS    = "KEYS"
GROUP_BASS    = "BASS"
GROUP_BRASS   = "BRASS"
GROUP_STRINGS = "STRINGS"
GROUP_EFFECTS = "EFFECTS"
GROUP_MISC    = "MISC"

# --------------------------------------------------------------------
# Color assignments per group (used in REAPER and GUI)
# These are REAPER-style color integers (packed RGB).
# You can expand this mapping for other DAWs.
# --------------------------------------------------------------------
GROUP_COLORS: dict[str, str] = {
    GROUP_DRUMS:   "#C0392B",   # Red
    GROUP_VOCALS:  "#2980B9",   # Blue
    GROUP_GUITARS: "#27AE60",   # Green
    GROUP_KEYS:    "#8E44AD",   # Purple
    GROUP_BASS:    "#E67E22",   # Orange
    GROUP_BRASS:   "#F1C40F",   # Yellow
    GROUP_STRINGS: "#1ABC9C",   # Teal
    GROUP_EFFECTS: "#7F8C8D",   # Grey
    GROUP_MISC:    "#95A5A6",   # Light Grey
}


@dataclass
class Track:
    """
    Represents a single track/channel from a live console session.

    Attributes
    ----------
    channel : int
        The physical channel number on the console (1-based).
    name : str
        The track label as it appears on the console fader strip.
    track_type : str
        One of: mono, stereo, aux, group, master, fx.
    group : str
        Auto-detected or user-assigned instrument group label.
        e.g. "DRUMS", "VOCALS", "GUITARS"
    output : str
        The bus/output this track routes to on the console.
        e.g. "Drum Bus", "Main LR", "Mix Bus"
    color : str
        Hex color string for DAW track coloring.
        Auto-assigned from GROUP_COLORS based on group.
    stereo_pair : Optional[int]
        If this is part of a stereo pair, the channel number of the partner.
        e.g. OH L (ch 3) and OH R (ch 4) → stereo_pair = 4 for ch 3.
    mute : bool
        Whether the track was muted on the console.
    solo : bool
        Whether the track was soloed on the console.
    notes : str
        Any additional notes or metadata.
    """

    channel:      int
    name:         str
    track_type:   str   = TRACK_TYPE_MONO
    group:        str   = GROUP_MISC
    output:       str   = "Main LR"
    color:        str   = "#95A5A6"
    stereo_pair:  Optional[int] = None
    mute:         bool  = False
    solo:         bool  = False
    notes:        str   = ""

    def __post_init__(self):
        """
        Called automatically after __init__.
        Assigns a color based on the group if no custom color was given.
        """
        if self.color == "#95A5A6" and self.group in GROUP_COLORS:
            self.color = GROUP_COLORS[self.group]

    def to_dict(self) -> dict:
        """
        Serializes this Track to a plain Python dictionary.
        Used when building the Universal Session JSON.
        """
        return {
            "channel":     self.channel,
            "name":        self.name,
            "type":        self.track_type,
            "group":       self.group,
            "output":      self.output,
            "color":       self.color,
            "stereo_pair": self.stereo_pair,
            "mute":        self.mute,
            "solo":        self.solo,
            "notes":       self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        """
        Creates a Track instance from a plain dictionary.
        Used when loading a Universal Session JSON back into memory.
        """
        return cls(
            channel=     data.get("channel", 0),
            name=        data.get("name", "Untitled"),
            track_type=  data.get("type", TRACK_TYPE_MONO),
            group=       data.get("group", GROUP_MISC),
            output=      data.get("output", "Main LR"),
            color=       data.get("color", "#95A5A6"),
            stereo_pair= data.get("stereo_pair"),
            mute=        data.get("mute", False),
            solo=        data.get("solo", False),
            notes=       data.get("notes", ""),
        )

    def __repr__(self) -> str:
        return f"<Track ch={self.channel} name='{self.name}' type={self.track_type} group={self.group}>"
