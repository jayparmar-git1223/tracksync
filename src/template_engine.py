"""
template_engine.py — Session Template Engine

Allows engineers to define session templates that are populated
with real track data from a console session.

Use cases:
  - Venue has a house rig with fixed track counts/routing
  - Engineer has a personal template they always start from
  - Broadcast template with fixed stem structure
  - IEM mix template that needs channel names but fixed routing

A template is a JSON file that defines the expected track slots
and how to map incoming console channels into them.

Example template (house_rig.template.json):
  {
    "name": "House Rig Template",
    "description": "Venue fixed I/O template",
    "slots": [
      { "slot": 1,  "label": "Kick",       "group": "DRUMS",  "hw_input": 1  },
      { "slot": 2,  "label": "Snare",      "group": "DRUMS",  "hw_input": 2  },
      { "slot": 32, "label": "Lead Vox",   "group": "VOCALS", "hw_input": 32 }
    ],
    "buses": [
      { "name": "Drum Bus",  "slots": [1,2,3,4,5,6,7,8,9,10] },
      { "name": "Vocal Bus", "slots": [32,33,34,35] }
    ]
  }

When applied to a console session, the template maps incoming tracks
into the template slots by name-matching or positional assignment.

Usage:
    from template_engine import TemplateEngine, SessionTemplate

    engine = TemplateEngine()
    template = engine.load_template("templates/house_rig.template.json")
    filled = engine.apply_template(session, template)
    print(filled.tracks)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from models.session import Session
from models.track import Track, GROUP_MISC, GROUP_COLORS
from models.bus import Bus

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


# ─────────────────────────────────────────────────────────────────────
# Template data model
# ─────────────────────────────────────────────────────────────────────

@dataclass
class TemplateSlot:
    """One track slot in a session template."""
    slot:       int           # Slot number in the template (1-based)
    label:      str           # Expected track name/label (used for matching)
    group:      str = GROUP_MISC
    hw_input:   int = 0       # Physical hardware input number (0 = same as slot)
    output:     str = "Main LR"
    required:   bool = True   # If True, warn when slot is unfilled
    notes:      str = ""

    def to_dict(self) -> dict:
        return {
            "slot": self.slot, "label": self.label, "group": self.group,
            "hw_input": self.hw_input, "output": self.output,
            "required": self.required, "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TemplateSlot":
        return cls(
            slot=     data.get("slot", 0),
            label=    data.get("label", ""),
            group=    data.get("group", GROUP_MISC),
            hw_input= data.get("hw_input", 0),
            output=   data.get("output", "Main LR"),
            required= data.get("required", True),
            notes=    data.get("notes", ""),
        )


@dataclass
class TemplateBus:
    """Bus definition within a template."""
    name:  str
    slots: list[int] = field(default_factory=list)
    color: str = "#2C3E50"

    def to_dict(self) -> dict:
        return {"name": self.name, "slots": self.slots, "color": self.color}

    @classmethod
    def from_dict(cls, data: dict) -> "TemplateBus":
        return cls(
            name=  data.get("name", "Bus"),
            slots= data.get("slots", []),
            color= data.get("color", "#2C3E50"),
        )


@dataclass
class SessionTemplate:
    """A complete session template definition."""
    name:        str
    description: str = ""
    author:      str = ""
    version:     str = "1.0"
    console:     str = ""           # Target console brand (optional)
    daw:         str = ""           # Target DAW (optional)
    slots:       list[TemplateSlot] = field(default_factory=list)
    buses:       list[TemplateBus]  = field(default_factory=list)
    notes:       str = ""

    @property
    def slot_count(self) -> int:
        return len(self.slots)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "author": self.author, "version": self.version,
            "console": self.console, "daw": self.daw,
            "slots": [s.to_dict() for s in self.slots],
            "buses": [b.to_dict() for b in self.buses],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionTemplate":
        return cls(
            name=        data.get("name", "Untitled Template"),
            description= data.get("description", ""),
            author=      data.get("author", ""),
            version=     data.get("version", "1.0"),
            console=     data.get("console", ""),
            daw=         data.get("daw", ""),
            slots=       [TemplateSlot.from_dict(s) for s in data.get("slots", [])],
            buses=       [TemplateBus.from_dict(b) for b in data.get("buses", [])],
            notes=       data.get("notes", ""),
        )


# ─────────────────────────────────────────────────────────────────────
# Template Engine
# ─────────────────────────────────────────────────────────────────────

class TemplateEngine:
    """
    Applies session templates to Universal Session objects.

    The engine can map incoming console tracks to template slots using:
      1. EXACT NAME MATCH   — track name exactly matches slot label
      2. FUZZY NAME MATCH   — normalized name comparison (case/space insensitive)
      3. POSITIONAL MATCH   — map by channel number order
      4. KEYWORD MATCH      — match by group/keyword pattern

    Unfilled required slots generate warnings.
    Extra tracks (not matched to any slot) are appended at the end.

    Example:
        engine = TemplateEngine()
        template = engine.load_template("templates/house_rig.template.json")
        filled_session = engine.apply_template(session, template)
    """

    def __init__(self, templates_dir: Optional[str] = None):
        self.templates_dir = Path(templates_dir) if templates_dir else TEMPLATES_DIR
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self._write_builtin_templates()

    def load_template(self, path: str) -> SessionTemplate:
        """
        Load a template from a JSON file.

        Parameters
        ----------
        path : str
            Path to the template .json file. If just a name (no slash),
            looks in the templates directory.
        """
        p = Path(path)
        if not p.exists():
            # Try in templates dir
            p = self.templates_dir / path
            if not p.exists():
                p = self.templates_dir / (path + ".template.json")

        if not p.exists():
            raise FileNotFoundError(f"Template not found: {path}")

        with open(p, encoding="utf-8") as f:
            data = json.load(f)

        template = SessionTemplate.from_dict(data)
        logger.info(
            f"[INFO] TemplateEngine: Loaded template '{template.name}' "
            f"({template.slot_count} slots)"
        )
        return template

    def save_template(self, template: SessionTemplate, filename: Optional[str] = None) -> str:
        """Save a template to the templates directory."""
        slug = filename or self._slugify(template.name)
        path = self.templates_dir / f"{slug}.template.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(template.to_dict(), f, indent=2)
        logger.info(f"[INFO] TemplateEngine: Saved template '{template.name}' → {path}")
        return str(path)

    def list_templates(self) -> list[SessionTemplate]:
        """List all available templates in the templates directory."""
        templates = []
        for p in sorted(self.templates_dir.glob("*.template.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    templates.append(SessionTemplate.from_dict(json.load(f)))
            except Exception as e:
                logger.warning(f"[WARNING] TemplateEngine: Could not load {p}: {e}")
        return templates

    def apply_template(
        self,
        session: Session,
        template: SessionTemplate,
        match_strategy: str = "smart",
    ) -> Session:
        """
        Apply a template to a session.

        Maps incoming tracks to template slots, then rebuilds the
        session track list in template slot order.

        Parameters
        ----------
        session : Session
            The source session (from console parser).
        template : SessionTemplate
            The template to apply.
        match_strategy : str
            One of: "exact", "fuzzy", "positional", "smart"
            "smart" tries exact, then fuzzy, then positional.

        Returns
        -------
        Session
            A new Session with tracks reordered/renamed to match the template.
        """
        logger.info(
            f"[INFO] TemplateEngine: Applying template '{template.name}' "
            f"to '{session.session_name}' ({session.get_track_count()} tracks)"
        )

        # Build track lookup
        tracks_by_ch   = {t.channel: t for t in session.tracks}
        tracks_by_name = {t.name.strip().lower(): t for t in session.tracks}
        matched_channels = set()

        # Result track list (one slot → one track)
        result_tracks: list[Track] = []

        for slot in template.slots:
            matched_track = None

            # Strategy: exact name match
            slot_name_lower = slot.label.strip().lower()
            if slot_name_lower in tracks_by_name:
                matched_track = tracks_by_name[slot_name_lower]

            # Strategy: fuzzy name match
            if not matched_track and match_strategy in ("fuzzy", "smart"):
                matched_track = self._fuzzy_match(slot.label, session.tracks, matched_channels)

            # Strategy: positional match (hw_input → channel number)
            if not matched_track and slot.hw_input > 0:
                matched_track = tracks_by_ch.get(slot.hw_input)

            # Strategy: positional by slot number
            if not matched_track and match_strategy in ("positional", "smart"):
                matched_track = tracks_by_ch.get(slot.slot)

            if matched_track:
                matched_channels.add(matched_track.channel)
                # Create a copy with the slot's metadata applied
                new_track = Track(
                    channel=    slot.slot,
                    name=       matched_track.name,    # Keep console name
                    track_type= matched_track.track_type,
                    group=      slot.group if slot.group != GROUP_MISC else matched_track.group,
                    output=     slot.output,
                    color=      GROUP_COLORS.get(slot.group or matched_track.group, "#95A5A6"),
                    stereo_pair= matched_track.stereo_pair,
                    mute=       matched_track.mute,
                    notes=      slot.notes,
                )
                result_tracks.append(new_track)
            else:
                if slot.required:
                    logger.warning(
                        f"[WARNING] TemplateEngine: Slot {slot.slot} '{slot.label}' "
                        f"could not be matched to any track"
                    )
                # Add an empty placeholder track
                result_tracks.append(Track(
                    channel=    slot.slot,
                    name=       slot.label or f"EMPTY {slot.slot}",
                    group=      slot.group,
                    output=     slot.output,
                    notes=      "UNFILLED SLOT",
                ))

        # Append unmatched tracks at the end (preserving any extras from console)
        unmatched = [t for t in session.tracks if t.channel not in matched_channels]
        next_slot = max((s.slot for s in template.slots), default=0) + 1
        for t in unmatched:
            t_copy = Track(
                channel=    next_slot,
                name=       t.name,
                track_type= t.track_type,
                group=      t.group,
                output=     t.output,
                color=      t.color,
                notes=      f"Unmatched from ch{t.channel}",
            )
            result_tracks.append(t_copy)
            next_slot += 1

        # Rebuild buses from template
        new_buses = []
        for tbus in template.buses:
            new_buses.append(Bus(
                name=     tbus.name,
                bus_type= "subgroup",
                channels= tbus.slots,
                color=    tbus.color,
            ))

        # Build output session
        result = Session(
            console=      session.console,
            session_name= session.session_name,
            sample_rate=  session.sample_rate,
            bit_depth=    session.bit_depth,
            source_file=  session.source_file,
            tracks=       result_tracks,
            buses=        new_buses if new_buses else session.buses,
            notes=        f"Applied template: {template.name}",
        )

        matched_count = sum(1 for t in result_tracks if "UNFILLED" not in t.notes)
        logger.info(
            f"[SUCCESS] TemplateEngine: Applied '{template.name}' — "
            f"{matched_count}/{len(template.slots)} slots filled, "
            f"{len(unmatched)} unmatched tracks appended"
        )
        return result

    def session_to_template(self, session: Session, name: str = "") -> SessionTemplate:
        """
        Convert a session into a template.

        This is the reverse operation — take a session that worked
        well and save it as a reusable template.

        Parameters
        ----------
        session : Session
            Source session to convert.
        name : str
            Template name. Defaults to session name.
        """
        slots = [
            TemplateSlot(
                slot=     t.channel,
                label=    t.name,
                group=    t.group,
                hw_input= t.channel,
                output=   t.output,
            )
            for t in session.tracks
        ]

        buses = [
            TemplateBus(
                name=  b.name,
                slots= b.channels,
                color= b.color,
            )
            for b in session.buses
        ]

        return SessionTemplate(
            name=        name or f"{session.session_name} Template",
            description= f"Generated from {session.session_name} ({session.console})",
            author=      "Live Console DAW Mirror",
            console=     session.console,
            slots=       slots,
            buses=       buses,
        )

    def _fuzzy_match(
        self, label: str, tracks: list[Track], already_matched: set
    ) -> Optional[Track]:
        """
        Fuzzy name match: try normalized comparison.

        Normalizes both the slot label and track names:
        - lowercase
        - strip whitespace
        - remove non-alphanumeric characters
        - try prefix match
        """
        def normalize(s: str) -> str:
            return re.sub(r'[^a-z0-9]', '', s.lower().strip())

        label_norm = normalize(label)
        label_words = set(label.lower().split())

        best_match = None
        best_score = 0

        for t in tracks:
            if t.channel in already_matched:
                continue

            name_norm  = normalize(t.name)
            name_words = set(t.name.lower().split())

            # Exact normalized match
            if label_norm == name_norm:
                return t

            # Prefix match (e.g. "Kick" matches "Kick In")
            if name_norm.startswith(label_norm) or label_norm.startswith(name_norm):
                score = len(label_norm)
                if score > best_score:
                    best_score = score
                    best_match = t

            # Word overlap score
            overlap = len(label_words & name_words)
            if overlap > 0 and overlap > best_score:
                best_score = overlap
                best_match = t

        return best_match if best_score > 0 else None

    @staticmethod
    def _slugify(name: str) -> str:
        return re.sub(r'[^a-z0-9_]', '_', name.lower().replace(" ", "_"))

    def _write_builtin_templates(self):
        """Write built-in templates to disk."""
        builtin = [
            SessionTemplate(
                name="Standard Live Show",
                description="32-channel live show template with standard drum/vocal/GTR/keys structure",
                slots=[
                    TemplateSlot(1,  "Kick In",    "DRUMS",   1),
                    TemplateSlot(2,  "Kick Out",   "DRUMS",   2),
                    TemplateSlot(3,  "Snare Top",  "DRUMS",   3),
                    TemplateSlot(4,  "Snare Bot",  "DRUMS",   4),
                    TemplateSlot(5,  "Hi Hat",     "DRUMS",   5),
                    TemplateSlot(6,  "Ride",       "DRUMS",   6),
                    TemplateSlot(7,  "Tom 1",      "DRUMS",   7),
                    TemplateSlot(8,  "Tom 2",      "DRUMS",   8),
                    TemplateSlot(9,  "Tom 3",      "DRUMS",   9),
                    TemplateSlot(10, "Floor Tom",  "DRUMS",  10),
                    TemplateSlot(11, "OH L",       "DRUMS",  11),
                    TemplateSlot(12, "OH R",       "DRUMS",  12),
                    TemplateSlot(13, "Room L",     "DRUMS",  13),
                    TemplateSlot(14, "Room R",     "DRUMS",  14),
                    TemplateSlot(15, "Bass DI",    "BASS",   15),
                    TemplateSlot(16, "Bass Amp",   "BASS",   16),
                    TemplateSlot(17, "GTR L",      "GUITARS",17),
                    TemplateSlot(18, "GTR R",      "GUITARS",18),
                    TemplateSlot(19, "Keys L",     "KEYS",   19),
                    TemplateSlot(20, "Keys R",     "KEYS",   20),
                    TemplateSlot(21, "Lead Vox",   "VOCALS", 21),
                    TemplateSlot(22, "BGV 1",      "VOCALS", 22),
                    TemplateSlot(23, "BGV 2",      "VOCALS", 23),
                    TemplateSlot(24, "BGV 3",      "VOCALS", 24),
                ],
                buses=[
                    TemplateBus("Drum Bus",  list(range(1, 15))),
                    TemplateBus("Bass Bus",  [15, 16]),
                    TemplateBus("GTR Bus",   [17, 18]),
                    TemplateBus("Keys Bus",  [19, 20]),
                    TemplateBus("Vocal Bus", list(range(21, 25))),
                ],
            ),
            SessionTemplate(
                name="Broadcast IEM Mix",
                description="IEM broadcast mix template with stems and intercom",
                slots=[
                    TemplateSlot(1,  "Kick",       "DRUMS",   1, "Drum Stem"),
                    TemplateSlot(2,  "Snare",      "DRUMS",   2, "Drum Stem"),
                    TemplateSlot(3,  "OH L",       "DRUMS",   3, "Drum Stem"),
                    TemplateSlot(4,  "OH R",       "DRUMS",   4, "Drum Stem"),
                    TemplateSlot(5,  "Bass",       "BASS",    5, "Music Stem"),
                    TemplateSlot(6,  "GTR",        "GUITARS",  6, "Music Stem"),
                    TemplateSlot(7,  "Keys",       "KEYS",    7, "Music Stem"),
                    TemplateSlot(8,  "Lead Vox",   "VOCALS",  8, "Vocal Stem"),
                    TemplateSlot(9,  "BGV",        "VOCALS",  9, "Vocal Stem"),
                    TemplateSlot(10, "Click",      "MISC",   10, "Click Out"),
                    TemplateSlot(11, "Timecode",   "MISC",   11, "TC Out"),
                ],
                buses=[
                    TemplateBus("Drum Stem",  [1, 2, 3, 4]),
                    TemplateBus("Music Stem", [5, 6, 7]),
                    TemplateBus("Vocal Stem", [8, 9]),
                    TemplateBus("Click Out",  [10]),
                ],
            ),
        ]

        for template in builtin:
            slug = self._slugify(template.name)
            path = self.templates_dir / f"{slug}.template.json"
            if not path.exists():
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(template.to_dict(), f, indent=2)
                except Exception as e:
                    logger.debug(f"[DEBUG] TemplateEngine: Could not write {slug}: {e}")
