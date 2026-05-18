"""
track_table.py — Editable Track Table Widget

Displays all session tracks in a professional, editable table.
Columns: CH | Track Name | Type | Group | Output | Color

The table is fully editable — engineers can rename tracks,
change groups, re-assign outputs, and adjust types directly
in the table before exporting.

The table preserves all changes back into the session model.
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QWidget, QHBoxLayout, QComboBox, QLabel, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont

from models.session import Session
from models.track import (
    Track,
    TRACK_TYPE_MONO, TRACK_TYPE_STEREO,
    GROUP_DRUMS, GROUP_VOCALS, GROUP_GUITARS,
    GROUP_KEYS, GROUP_BASS, GROUP_BRASS,
    GROUP_STRINGS, GROUP_EFFECTS, GROUP_MISC,
    GROUP_COLORS,
)

logger = logging.getLogger(__name__)

# Column indices
COL_CHANNEL = 0
COL_NAME    = 1
COL_TYPE    = 2
COL_GROUP   = 3
COL_OUTPUT  = 4
COL_COLOR   = 5

COLUMN_HEADERS = ["CH", "TRACK NAME", "TYPE", "GROUP", "OUTPUT", "COLOR"]

ALL_GROUPS = [
    GROUP_DRUMS, GROUP_VOCALS, GROUP_GUITARS,
    GROUP_KEYS, GROUP_BASS, GROUP_BRASS,
    GROUP_STRINGS, GROUP_EFFECTS, GROUP_MISC,
]

ALL_TYPES = [TRACK_TYPE_MONO, TRACK_TYPE_STEREO, "aux", "group", "master"]


class ColorSwatch(QWidget):
    """A small colored rectangle used in the color column."""

    def __init__(self, hex_color: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        self.swatch = QLabel()
        self.swatch.setFixedSize(20, 14)
        self.swatch.setStyleSheet(f"""
            background: {hex_color};
            border-radius: 3px;
            border: 1px solid rgba(255,255,255,0.1);
        """)

        self.label = QLabel(hex_color)
        self.label.setStyleSheet("color: #475569; font-size: 10px;")

        layout.addWidget(self.swatch)
        layout.addWidget(self.label)
        layout.addStretch()


class TrackTableWidget(QTableWidget):
    """
    An editable table displaying all tracks in the current session.

    Users can:
    - Edit track names (double-click)
    - Change track type via dropdown
    - Change group assignment via dropdown
    - Edit output assignment

    The table stores track objects so changes can be read back
    with get_session().
    """

    session_changed = Signal()   # Emitted when any cell is edited

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: list[Track] = []
        self._setup_table()

    def _setup_table(self):
        """Configure the table appearance and behavior."""
        self.setColumnCount(len(COLUMN_HEADERS))
        self.setHorizontalHeaderLabels(COLUMN_HEADERS)

        # Styling
        self.setStyleSheet("""
            QTableWidget {
                background: #050A14;
                color: #CBD5E1;
                border: none;
                gridline-color: #1E293B;
                selection-background-color: #1E293B;
                selection-color: #F1F5F9;
                font-size: 12px;
                font-family: 'SF Mono', 'JetBrains Mono', 'Consolas', monospace;
            }
            QTableWidget::item {
                padding: 0 8px;
                border-bottom: 1px solid #0F172A;
            }
            QTableWidget::item:selected {
                background: #1E293B;
            }
            QHeaderView::section {
                background: #020509;
                color: #475569;
                border: none;
                border-bottom: 1px solid #1E293B;
                border-right: 1px solid #1E293B;
                padding: 6px 8px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            QComboBox {
                background: transparent;
                color: #CBD5E1;
                border: none;
                font-size: 12px;
                font-family: 'SF Mono', 'JetBrains Mono', 'Consolas', monospace;
            }
            QComboBox::drop-down { border: none; }
        """)

        # Column widths
        header = self.horizontalHeader()
        header.setSectionResizeMode(COL_CHANNEL, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_NAME,    QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_TYPE,    QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_GROUP,   QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_OUTPUT,  QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_COLOR,   QHeaderView.ResizeMode.Fixed)

        self.setColumnWidth(COL_CHANNEL, 50)
        self.setColumnWidth(COL_TYPE,   90)
        self.setColumnWidth(COL_GROUP,  110)
        self.setColumnWidth(COL_COLOR,  100)

        # Behavior
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(False)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.verticalHeader().setDefaultSectionSize(30)

        # Connect editing signal
        self.itemChanged.connect(self._on_item_changed)

    def load_session(self, session: Session):
        """
        Populate the table with tracks from a Session object.

        Parameters
        ----------
        session : Session
            The session whose tracks to display.
        """
        # Store reference to tracks for editing
        self._tracks = list(session.tracks)

        # Block signals while building the table to prevent spurious events
        self.blockSignals(True)
        self.setRowCount(len(self._tracks))

        for row, track in enumerate(self._tracks):
            self._populate_row(row, track)

        self.blockSignals(False)
        logger.info(f"[INFO] TrackTable: Loaded {len(self._tracks)} tracks")

    def _populate_row(self, row: int, track: Track):
        """Populate a single table row from a Track object."""
        # CH (read-only)
        ch_item = QTableWidgetItem(str(track.channel))
        ch_item.setFlags(ch_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        ch_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        ch_item.setForeground(QBrush(QColor("#475569")))
        self.setItem(row, COL_CHANNEL, ch_item)

        # Track Name (editable)
        name_item = QTableWidgetItem(track.name)
        name_item.setForeground(QBrush(QColor("#F1F5F9")))
        # Add a left border in the track's group color
        self.setItem(row, COL_NAME, name_item)

        # Type (combobox)
        type_combo = QComboBox()
        type_combo.addItems(ALL_TYPES)
        idx = type_combo.findText(track.track_type)
        if idx >= 0:
            type_combo.setCurrentIndex(idx)
        type_combo.currentTextChanged.connect(
            lambda text, r=row: self._on_type_changed(r, text)
        )
        self.setCellWidget(row, COL_TYPE, type_combo)

        # Group (combobox)
        group_combo = QComboBox()
        group_combo.addItems(ALL_GROUPS)
        idx = group_combo.findText(track.group)
        if idx >= 0:
            group_combo.setCurrentIndex(idx)
        group_combo.currentTextChanged.connect(
            lambda text, r=row: self._on_group_changed(r, text)
        )
        self.setCellWidget(row, COL_GROUP, group_combo)

        # Output (editable)
        output_item = QTableWidgetItem(track.output)
        output_item.setForeground(QBrush(QColor("#94A3B8")))
        self.setItem(row, COL_OUTPUT, output_item)

        # Color swatch (read-only display)
        swatch = ColorSwatch(track.color)
        self.setCellWidget(row, COL_COLOR, swatch)

        # Row background tint based on group
        self._apply_row_color(row, track.group)

    def _apply_row_color(self, row: int, group: str):
        """Apply a subtle group-based tint to the channel number cell."""
        hex_color = GROUP_COLORS.get(group, "#334155")
        # Create a dark tinted version of the group color
        try:
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            tinted = f"rgba({r},{g},{b},0.15)"
        except Exception:
            tinted = "rgba(100,100,100,0.1)"

        ch_item = self.item(row, COL_CHANNEL)
        if ch_item:
            ch_item.setBackground(QBrush(QColor(hex_color).darker(400)))

    def _on_item_changed(self, item: QTableWidgetItem):
        """Handle cell edits — update the Track object."""
        row = item.row()
        col = item.column()

        if row >= len(self._tracks):
            return

        track = self._tracks[row]

        if col == COL_NAME:
            old_name = track.name
            track.name = item.text().strip()
            logger.info(f"[INFO] Track ch{track.channel}: renamed '{old_name}' → '{track.name}'")

        elif col == COL_OUTPUT:
            track.output = item.text().strip()

        self.session_changed.emit()

    def _on_type_changed(self, row: int, track_type: str):
        """Handle type combobox changes."""
        if row < len(self._tracks):
            self._tracks[row].track_type = track_type
            self.session_changed.emit()

    def _on_group_changed(self, row: int, group: str):
        """Handle group combobox changes — also update color."""
        if row < len(self._tracks):
            self._tracks[row].group = group
            self._tracks[row].color = GROUP_COLORS.get(group, "#95A5A6")
            # Update the color swatch
            swatch = ColorSwatch(self._tracks[row].color)
            self.setCellWidget(row, COL_COLOR, swatch)
            self._apply_row_color(row, group)
            self.session_changed.emit()

    def get_session(self) -> Optional[Session]:
        """
        Returns an updated Session object reflecting any table edits.

        Reads the current track list (with any user edits applied)
        and returns a copy of the session with updated tracks.

        Returns None if no session has been loaded.
        """
        if not self._tracks:
            return None

        # Build a minimal session from the current track state
        from models.session import Session
        return Session(tracks=self._tracks)
