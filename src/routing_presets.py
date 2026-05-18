"""
routing_presets.py — Routing Preset System

A routing preset is a named template that defines how tracks should be
grouped, colored, and routed in the output DAW session.

Presets are stored as JSON files in the templates/ directory.

Built-in presets:
    live_show        — Standard live touring setup (drums → drum bus, etc.)
    recording        — Studio recording template (more buses, stems)
    broadcast        — Broadcast/streaming optimized (submix structure)
    festival         — Festival/multi-act rig (minimal, portable)
    theatre          — Theatre/musical production setup
    playback         — Playback/click track focused rig

Custom presets:
    Users can save and load their own .preset.json files.

Usage:
    from routing_presets import PresetManager

    pm = PresetManager()
    session = pm.apply_preset(session, "live_show")
    presets = pm.list_presets()
"""

import json
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from models.session import Session
from models.track import Track, GROUP_MISC, GROUP_COLORS
from models.bus import Bus

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# ─────────────────────────────────────────────────────────────────────
# Preset data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class BusDefinition:
    """Defines a bus/subgroup to create in the DAW session."""
    name:     str
    groups:   list[str]      # Which instrument groups feed this bus
    color:    str = "#2C3E50"
    bus_type: str = "subgroup"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "groups": self.groups,
            "color": self.color,
            "bus_type": self.bus_type,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BusDefinition":
        return cls(
            name=     data["name"],
            groups=   data.get("groups", []),
            color=    data.get("color", "#2C3E50"),
            bus_type= data.get("bus_type", "subgroup"),
        )


@dataclass
class RoutingPreset:
    """
    A named routing template.

    Defines how tracks are organized (groups, buses, colors)
    when applied to a session.

    Attributes
    ----------
    name : str
        Display name of the preset. e.g. "Live Show"
    description : str
        Human-readable description of the preset.
    author : str
        Who created this preset.
    buses : list[BusDefinition]
        Bus definitions to create in the DAW session.
    group_overrides : dict[str, str]
        Force specific track name patterns to a group.
        e.g. {"click": "MISC", "timecode": "MISC"}
    color_overrides : dict[str, str]
        Override group colors. e.g. {"DRUMS": "#FF0000"}
    default_output : str
        Default output assignment for all tracks.
    """

    name:             str
    description:      str = ""
    author:           str = "Live Console DAW Mirror"
    buses:            list[BusDefinition] = field(default_factory=list)
    group_overrides:  dict[str, str]      = field(default_factory=dict)
    color_overrides:  dict[str, str]      = field(default_factory=dict)
    default_output:   str                 = "Main LR"
    tags:             list[str]           = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name":            self.name,
            "description":     self.description,
            "author":          self.author,
            "buses":           [b.to_dict() for b in self.buses],
            "group_overrides": self.group_overrides,
            "color_overrides": self.color_overrides,
            "default_output":  self.default_output,
            "tags":            self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoutingPreset":
        return cls(
            name=            data["name"],
            description=     data.get("description", ""),
            author=          data.get("author", ""),
            buses=           [BusDefinition.from_dict(b) for b in data.get("buses", [])],
            group_overrides= data.get("group_overrides", {}),
            color_overrides= data.get("color_overrides", {}),
            default_output=  data.get("default_output", "Main LR"),
            tags=            data.get("tags", []),
        )


# ─────────────────────────────────────────────────────────────────────
# Built-in presets
# ─────────────────────────────────────────────────────────────────────

BUILTIN_PRESETS: dict[str, RoutingPreset] = {

    "live_show": RoutingPreset(
        name="Live Show",
        description="Standard live touring template. Drums, vocals, guitars, keys, and brass each get a dedicated subgroup bus.",
        author="Live Console DAW Mirror",
        tags=["live", "touring", "concert"],
        buses=[
            BusDefinition("Drum Bus",   ["DRUMS"],   "#7B241C"),
            BusDefinition("Vocal Bus",  ["VOCALS"],  "#1A5276"),
            BusDefinition("GTR Bus",    ["GUITARS"],  "#1E8449"),
            BusDefinition("Keys Bus",   ["KEYS"],    "#6C3483"),
            BusDefinition("Bass Bus",   ["BASS"],    "#784212"),
            BusDefinition("Brass Bus",  ["BRASS"],   "#7D6608"),
            BusDefinition("FX Bus",     ["EFFECTS"], "#2C3E50"),
        ],
        group_overrides={
            "click":     "MISC",
            "tc":        "MISC",
            "timecode":  "MISC",
            "playback":  "EFFECTS",
            "stems":     "EFFECTS",
        },
        default_output="Main LR",
    ),

    "recording": RoutingPreset(
        name="Recording Session",
        description="Studio recording optimized. Stem buses, detailed group structure, and marker tracks.",
        author="Live Console DAW Mirror",
        tags=["recording", "studio", "tracking"],
        buses=[
            BusDefinition("Drum Stem",   ["DRUMS"],   "#7B241C"),
            BusDefinition("Vocal Stem",  ["VOCALS"],  "#1A5276"),
            BusDefinition("GTR Stem",    ["GUITARS"],  "#1E8449"),
            BusDefinition("Keys Stem",   ["KEYS"],    "#6C3483"),
            BusDefinition("Bass Stem",   ["BASS"],    "#784212"),
            BusDefinition("Brass Stem",  ["BRASS"],   "#7D6608"),
            BusDefinition("Perc Stem",   ["DRUMS"],   "#7B241C"),
            BusDefinition("Mix Bus",     [],          "#2C3E50"),
        ],
        group_overrides={
            "ref":  "MISC",
            "talk": "MISC",
        },
        default_output="Mix Bus",
    ),

    "broadcast": RoutingPreset(
        name="Broadcast / Streaming",
        description="Broadcast and streaming optimized. Clean submix structure with commentary and intercom routing.",
        author="Live Console DAW Mirror",
        tags=["broadcast", "streaming", "radio", "tv"],
        buses=[
            BusDefinition("Music Bus",    ["DRUMS", "GUITARS", "BASS", "KEYS", "BRASS"], "#1A5276"),
            BusDefinition("Vocal Bus",    ["VOCALS"],  "#7B241C"),
            BusDefinition("FX Bus",       ["EFFECTS"], "#2C3E50"),
            BusDefinition("PGM Bus",      [],          "#1E8449"),  # Programme bus
            BusDefinition("Commentary",   [],          "#6C3483"),
        ],
        group_overrides={
            "pres":   "VOCALS",
            "host":   "VOCALS",
            "talent": "VOCALS",
            "comm":   "MISC",
            "itv":    "MISC",
        },
        default_output="PGM Bus",
    ),

    "festival": RoutingPreset(
        name="Festival Rig",
        description="Minimal, portable festival setup. Fast changeover focus.",
        author="Live Console DAW Mirror",
        tags=["festival", "outdoor", "changeover"],
        buses=[
            BusDefinition("Band Bus",  ["DRUMS", "BASS", "GUITARS", "KEYS", "BRASS"], "#7B241C"),
            BusDefinition("Vox Bus",   ["VOCALS"],   "#1A5276"),
        ],
        default_output="Main LR",
    ),

    "theatre": RoutingPreset(
        name="Theatre / Musical",
        description="Theatre and musical production optimized. Lavalier mics, orchestra pit, and playback tracks.",
        author="Live Console DAW Mirror",
        tags=["theatre", "musical", "production", "lavs"],
        buses=[
            BusDefinition("Lavs Bus",    ["VOCALS"],   "#1A5276"),
            BusDefinition("Orch Bus",    ["STRINGS", "BRASS", "KEYS"], "#7D6608"),
            BusDefinition("Playback Bus",["EFFECTS"],  "#6C3483"),
            BusDefinition("FX Bus",      ["EFFECTS"],  "#2C3E50"),
        ],
        group_overrides={
            "lav":      "VOCALS",
            "lapel":    "VOCALS",
            "headset":  "VOCALS",
            "pit":      "STRINGS",
            "pb":       "EFFECTS",
            "track":    "EFFECTS",
        },
        default_output="Main LR",
    ),

    "playback": RoutingPreset(
        name="Playback / Click Rig",
        description="Playback engineer focused. Click, timecode, stems, and IEM monitoring.",
        author="Live Console DAW Mirror",
        tags=["playback", "click", "stems", "iem"],
        buses=[
            BusDefinition("Stems Bus",  ["EFFECTS"], "#6C3483"),
            BusDefinition("IEM Mix",    [],          "#1A5276"),
            BusDefinition("Click Out",  ["MISC"],    "#7B241C"),
        ],
        group_overrides={
            "click":    "MISC",
            "clk":      "MISC",
            "tc":       "MISC",
            "timecode": "MISC",
            "stem":     "EFFECTS",
            "pb":       "EFFECTS",
            "track":    "EFFECTS",
        },
        default_output="Stems Bus",
    ),
}


# ─────────────────────────────────────────────────────────────────────
# Preset Manager
# ─────────────────────────────────────────────────────────────────────

class PresetManager:
    """
    Manages routing presets — loading, saving, and applying them to sessions.

    Built-in presets are always available.
    Custom presets are loaded from and saved to the templates/ directory.

    Example usage:
        pm = PresetManager()

        # List all available presets
        for preset in pm.list_presets():
            print(preset.name, preset.description)

        # Apply a preset to a session
        session = pm.apply_preset(session, "live_show")

        # Save a custom preset
        my_preset = RoutingPreset(name="My Show", ...)
        pm.save_preset(my_preset, "my_show")

        # Load a custom preset
        preset = pm.load_preset("my_show")
    """

    def __init__(self, templates_dir: Optional[str] = None):
        """
        Parameters
        ----------
        templates_dir : str, optional
            Path to the templates directory for custom presets.
            Defaults to the project's templates/ folder.
        """
        self.templates_dir = Path(templates_dir) if templates_dir else TEMPLATES_DIR
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        # Cache of loaded presets (name → RoutingPreset)
        self._cache: dict[str, RoutingPreset] = dict(BUILTIN_PRESETS)

        # Write built-in presets to disk on first run
        self._write_builtin_presets()

    def list_presets(self) -> list[RoutingPreset]:
        """
        Return all available presets (built-in + custom).

        Returns
        -------
        list[RoutingPreset]
            All presets, built-in first, then custom alphabetically.
        """
        self._load_custom_presets()
        return list(self._cache.values())

    def get_preset(self, preset_name: str) -> Optional[RoutingPreset]:
        """
        Get a preset by name (case-insensitive, slug-matched).

        Parameters
        ----------
        preset_name : str
            The preset name or slug. e.g. "live_show" or "Live Show"

        Returns
        -------
        RoutingPreset or None
        """
        key = self._slugify(preset_name)
        return self._cache.get(key)

    def apply_preset(self, session: Session, preset_name: str) -> Session:
        """
        Apply a routing preset to a session.

        This modifies track outputs, group assignments (where overrides exist),
        and rebuilds the bus list according to the preset definition.

        Parameters
        ----------
        session : Session
            The session to apply the preset to.
        preset_name : str
            Name of the preset to apply.

        Returns
        -------
        Session
            The modified session (same object, mutated in place).
        """
        preset = self.get_preset(preset_name)
        if not preset:
            logger.warning(f"[WARNING] PresetManager: Preset '{preset_name}' not found.")
            return session

        logger.info(f"[INFO] PresetManager: Applying preset '{preset.name}' to '{session.session_name}'")

        # ── Apply group overrides ────────────────────────────────────
        for track in session.tracks:
            name_lower = track.name.lower()
            for keyword, group in preset.group_overrides.items():
                if keyword in name_lower:
                    track.group = group
                    break

        # ── Apply color overrides ────────────────────────────────────
        effective_colors = dict(GROUP_COLORS)
        effective_colors.update(preset.color_overrides)

        for track in session.tracks:
            track.color = effective_colors.get(track.group, "#95A5A6")

        # ── Apply default output ─────────────────────────────────────
        for track in session.tracks:
            if track.output in ("Main LR", "") or not track.output:
                track.output = preset.default_output

        # ── Rebuild buses from preset definition ─────────────────────
        new_buses = []
        for bus_def in preset.buses:
            # Collect channels from the specified groups
            channels = []
            for group in bus_def.groups:
                channels.extend(t.channel for t in session.tracks if t.group == group)

            new_buses.append(Bus(
                name=     bus_def.name,
                bus_type= bus_def.bus_type,
                channels= sorted(set(channels)),
                color=    bus_def.color,
            ))

        session.buses = new_buses

        logger.info(
            f"[SUCCESS] PresetManager: Applied '{preset.name}' — "
            f"{len(new_buses)} buses created"
        )

        return session

    def save_preset(self, preset: RoutingPreset, filename: Optional[str] = None) -> str:
        """
        Save a custom preset to the templates directory.

        Parameters
        ----------
        preset : RoutingPreset
            The preset to save.
        filename : str, optional
            The filename slug (without extension). Defaults to slugified name.

        Returns
        -------
        str
            Path to the saved .preset.json file.
        """
        slug = filename or self._slugify(preset.name)
        path = self.templates_dir / f"{slug}.preset.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(preset.to_dict(), f, indent=2)

        self._cache[slug] = preset
        logger.info(f"[INFO] PresetManager: Saved preset '{preset.name}' → {path}")
        return str(path)

    def load_preset(self, filename: str) -> Optional[RoutingPreset]:
        """
        Load a preset from a .preset.json file.

        Parameters
        ----------
        filename : str
            The slug name or full path.

        Returns
        -------
        RoutingPreset or None
        """
        path = self.templates_dir / f"{filename}.preset.json"
        if not path.exists():
            path = Path(filename)

        if not path.exists():
            logger.warning(f"[WARNING] PresetManager: Preset file not found: {filename}")
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        preset = RoutingPreset.from_dict(data)
        slug = self._slugify(preset.name)
        self._cache[slug] = preset
        return preset

    def _load_custom_presets(self):
        """Scan the templates directory and load any .preset.json files."""
        for path in self.templates_dir.glob("*.preset.json"):
            slug = path.stem.replace(".preset", "")
            if slug not in BUILTIN_PRESETS and slug not in self._cache:
                try:
                    self.load_preset(slug)
                except Exception as e:
                    logger.warning(f"[WARNING] PresetManager: Failed to load {path}: {e}")

    def _write_builtin_presets(self):
        """Write built-in presets to disk so users can inspect/edit them."""
        for slug, preset in BUILTIN_PRESETS.items():
            path = self.templates_dir / f"{slug}.preset.json"
            if not path.exists():
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(preset.to_dict(), f, indent=2)
                except Exception as e:
                    logger.warning(f"[WARNING] PresetManager: Could not write preset {slug}: {e}")

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a display name to a file slug. e.g. 'Live Show' → 'live_show'"""
        return name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
