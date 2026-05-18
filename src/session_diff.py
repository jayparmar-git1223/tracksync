"""
session_diff.py — Session Comparison Tool

Compare two Universal Session objects and produce a structured diff.
Useful for:
  - Comparing soundcheck vs showtime sessions
  - Verifying a DAW template matches the console layout
  - Spotting track renames, additions, or reorders between shows
  - QA before exporting to DAW

Usage:
    from session_diff import SessionDiff

    diff = SessionDiff(session_a, session_b)
    report = diff.report()
    print(report)

    changes = diff.compare()
    for change in changes:
        print(change)
"""

import logging
from dataclasses import dataclass
from typing import Optional
from models.session import Session
from models.track import Track

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Change types
# ─────────────────────────────────────────────────────────────────────

CHANGE_ADDED     = "ADDED"      # Track exists in B but not in A
CHANGE_REMOVED   = "REMOVED"    # Track exists in A but not in B
CHANGE_RENAMED   = "RENAMED"    # Same channel, different name
CHANGE_REORDERED = "REORDERED"  # Same name, different channel
CHANGE_TYPE      = "TYPE"       # Track type changed (mono→stereo)
CHANGE_GROUP     = "GROUP"      # Group assignment changed
CHANGE_OUTPUT    = "OUTPUT"     # Output routing changed
CHANGE_META      = "META"       # Session-level metadata changed


@dataclass
class TrackChange:
    """Represents a single difference between two sessions."""
    change_type: str         # One of the CHANGE_* constants above
    channel_a:   Optional[int]  # Channel in session A (None if added)
    channel_b:   Optional[int]  # Channel in session B (None if removed)
    name_a:      Optional[str]  # Track name in session A
    name_b:      Optional[str]  # Track name in session B
    detail:      str = ""       # Human-readable description of the change

    def __str__(self) -> str:
        ch_a = f"ch{self.channel_a}" if self.channel_a else "—"
        ch_b = f"ch{self.channel_b}" if self.channel_b else "—"
        return f"[{self.change_type:<10}] {ch_a:>5} → {ch_b:<5}  {self.detail}"


@dataclass
class MetaChange:
    """Represents a session-level metadata change."""
    field:   str
    value_a: str
    value_b: str

    def __str__(self) -> str:
        return f"[META      ]  {self.field}: '{self.value_a}' → '{self.value_b}'"


# ─────────────────────────────────────────────────────────────────────
# SessionDiff engine
# ─────────────────────────────────────────────────────────────────────

class SessionDiff:
    """
    Compares two Session objects and produces a structured diff.

    The diff covers:
    - Track additions and removals
    - Track renames (same channel, different name)
    - Track reorders (same name, different channel)
    - Type changes (mono ↔ stereo)
    - Group reassignments
    - Output routing changes
    - Session metadata changes (sample rate, console, etc.)

    Usage:
        diff = SessionDiff(session_before, session_after)
        changes = diff.compare()
        print(diff.report())
    """

    def __init__(self, session_a: Session, session_b: Session,
                 label_a: str = "Session A", label_b: str = "Session B"):
        """
        Parameters
        ----------
        session_a : Session
            The "before" or "reference" session.
        session_b : Session
            The "after" or "comparison" session.
        label_a : str
            Display label for session A in reports.
        label_b : str
            Display label for session B in reports.
        """
        self.session_a = session_a
        self.session_b = session_b
        self.label_a   = label_a
        self.label_b   = label_b
        self._changes: list[TrackChange | MetaChange] = []
        self._compared = False

    def compare(self) -> list:
        """
        Run the comparison and return a list of changes.

        Returns
        -------
        list
            List of TrackChange and MetaChange objects.
        """
        self._changes = []

        # Index tracks by channel and by name
        tracks_a_by_ch   = {t.channel: t for t in self.session_a.tracks}
        tracks_b_by_ch   = {t.channel: t for t in self.session_b.tracks}
        tracks_a_by_name = {t.name.strip().lower(): t for t in self.session_a.tracks}
        tracks_b_by_name = {t.name.strip().lower(): t for t in self.session_b.tracks}

        all_channels = sorted(set(tracks_a_by_ch) | set(tracks_b_by_ch))

        for ch in all_channels:
            in_a = ch in tracks_a_by_ch
            in_b = ch in tracks_b_by_ch

            if in_a and not in_b:
                # Track was removed
                t = tracks_a_by_ch[ch]
                # Check if it reappeared at a different channel (reorder)
                name_lower = t.name.strip().lower()
                if name_lower in tracks_b_by_name:
                    t_b = tracks_b_by_name[name_lower]
                    self._changes.append(TrackChange(
                        change_type= CHANGE_REORDERED,
                        channel_a=   ch,
                        channel_b=   t_b.channel,
                        name_a=      t.name,
                        name_b=      t_b.name,
                        detail=      f"'{t.name}' moved from ch{ch} → ch{t_b.channel}",
                    ))
                else:
                    self._changes.append(TrackChange(
                        change_type= CHANGE_REMOVED,
                        channel_a=   ch,
                        channel_b=   None,
                        name_a=      t.name,
                        name_b=      None,
                        detail=      f"ch{ch} '{t.name}' removed",
                    ))

            elif not in_a and in_b:
                # Track was added
                t = tracks_b_by_ch[ch]
                name_lower = t.name.strip().lower()
                # Only flag as added if it didn't move from somewhere else
                if name_lower not in tracks_a_by_name:
                    self._changes.append(TrackChange(
                        change_type= CHANGE_ADDED,
                        channel_a=   None,
                        channel_b=   ch,
                        name_a=      None,
                        name_b=      t.name,
                        detail=      f"ch{ch} '{t.name}' added",
                    ))

            elif in_a and in_b:
                # Track exists in both — check for field changes
                t_a = tracks_a_by_ch[ch]
                t_b = tracks_b_by_ch[ch]

                if t_a.name.strip().lower() != t_b.name.strip().lower():
                    self._changes.append(TrackChange(
                        change_type= CHANGE_RENAMED,
                        channel_a=   ch,
                        channel_b=   ch,
                        name_a=      t_a.name,
                        name_b=      t_b.name,
                        detail=      f"ch{ch}: '{t_a.name}' → '{t_b.name}'",
                    ))

                if t_a.track_type != t_b.track_type:
                    self._changes.append(TrackChange(
                        change_type= CHANGE_TYPE,
                        channel_a=   ch,
                        channel_b=   ch,
                        name_a=      t_a.name,
                        name_b=      t_b.name,
                        detail=      f"ch{ch} '{t_a.name}': {t_a.track_type} → {t_b.track_type}",
                    ))

                if t_a.group != t_b.group:
                    self._changes.append(TrackChange(
                        change_type= CHANGE_GROUP,
                        channel_a=   ch,
                        channel_b=   ch,
                        name_a=      t_a.name,
                        name_b=      t_b.name,
                        detail=      f"ch{ch} '{t_a.name}' group: {t_a.group} → {t_b.group}",
                    ))

                if t_a.output != t_b.output:
                    self._changes.append(TrackChange(
                        change_type= CHANGE_OUTPUT,
                        channel_a=   ch,
                        channel_b=   ch,
                        name_a=      t_a.name,
                        name_b=      t_b.name,
                        detail=      f"ch{ch} '{t_a.name}' output: '{t_a.output}' → '{t_b.output}'",
                    ))

        # ── Metadata changes ─────────────────────────────────────────
        meta_fields = [
            ("session_name", self.session_a.session_name, self.session_b.session_name),
            ("console",      self.session_a.console,      self.session_b.console),
            ("sample_rate",  str(self.session_a.sample_rate), str(self.session_b.sample_rate)),
            ("bit_depth",    str(self.session_a.bit_depth),   str(self.session_b.bit_depth)),
        ]
        for field, val_a, val_b in meta_fields:
            if val_a != val_b:
                self._changes.append(MetaChange(field=field, value_a=val_a, value_b=val_b))

        self._compared = True
        return self._changes

    def has_changes(self) -> bool:
        """Returns True if there are any differences between sessions."""
        if not self._compared:
            self.compare()
        return len(self._changes) > 0

    def count_by_type(self) -> dict[str, int]:
        """Returns a count of changes grouped by change type."""
        if not self._compared:
            self.compare()
        counts: dict[str, int] = {}
        for c in self._changes:
            key = c.change_type if isinstance(c, TrackChange) else "META"
            counts[key] = counts.get(key, 0) + 1
        return counts

    def report(self) -> str:
        """
        Generate a human-readable diff report.

        Returns
        -------
        str
            Formatted text report.
        """
        if not self._compared:
            self.compare()

        lines = [
            "=" * 64,
            "SESSION COMPARISON REPORT",
            "=" * 64,
            f"  A: {self.label_a}  ({self.session_a.session_name})",
            f"     {self.session_a.get_track_count()} tracks | {self.session_a.console}",
            f"",
            f"  B: {self.label_b}  ({self.session_b.session_name})",
            f"     {self.session_b.get_track_count()} tracks | {self.session_b.console}",
            "",
            "─" * 64,
        ]

        if not self._changes:
            lines += [
                "  ✓ NO DIFFERENCES FOUND",
                "  Sessions are identical.",
                "",
            ]
        else:
            counts = self.count_by_type()
            summary_parts = [f"{v} {k}" for k, v in counts.items()]
            lines += [
                f"  {len(self._changes)} DIFFERENCE(S) FOUND: {', '.join(summary_parts)}",
                "",
            ]

            # Group changes by type
            for change_type in [CHANGE_ADDED, CHANGE_REMOVED, CHANGE_RENAMED,
                                 CHANGE_REORDERED, CHANGE_TYPE, CHANGE_GROUP,
                                 CHANGE_OUTPUT, "META"]:

                type_changes = [
                    c for c in self._changes
                    if (isinstance(c, TrackChange) and c.change_type == change_type) or
                       (isinstance(c, MetaChange) and change_type == "META")
                ]
                if not type_changes:
                    continue

                label = {
                    CHANGE_ADDED:     "ADDED TRACKS",
                    CHANGE_REMOVED:   "REMOVED TRACKS",
                    CHANGE_RENAMED:   "RENAMED TRACKS",
                    CHANGE_REORDERED: "REORDERED TRACKS",
                    CHANGE_TYPE:      "TYPE CHANGES",
                    CHANGE_GROUP:     "GROUP CHANGES",
                    CHANGE_OUTPUT:    "OUTPUT CHANGES",
                    "META":           "METADATA CHANGES",
                }.get(change_type, change_type)

                lines.append(f"  {label}")
                lines.append("  " + "─" * 40)
                for c in type_changes:
                    lines.append(f"    {c}")
                lines.append("")

        lines += [
            "─" * 64,
            "END OF REPORT",
            "=" * 64,
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize the diff result to a dictionary for JSON export."""
        if not self._compared:
            self.compare()

        return {
            "session_a": self.session_a.session_name,
            "session_b": self.session_b.session_name,
            "total_changes": len(self._changes),
            "counts": self.count_by_type(),
            "changes": [
                {
                    "type":      c.change_type if isinstance(c, TrackChange) else "META",
                    "channel_a": c.channel_a if isinstance(c, TrackChange) else None,
                    "channel_b": c.channel_b if isinstance(c, TrackChange) else None,
                    "name_a":    c.name_a if isinstance(c, TrackChange) else c.field,
                    "name_b":    c.name_b if isinstance(c, TrackChange) else None,
                    "detail":    c.detail if isinstance(c, TrackChange) else f"{c.value_a} → {c.value_b}",
                }
                for c in self._changes
            ],
        }
