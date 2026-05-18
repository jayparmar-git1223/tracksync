"""
routing_view.py — Routing Matrix & Session Overview Widget

Provides a visual representation of the session routing structure.

Two views:
  1. MATRIX VIEW — grid showing which channels feed which buses
     (similar to REAPER routing matrix or Dante Controller)
  2. TREE VIEW   — hierarchical folder/group tree showing session structure

Both views update automatically when the session changes.

Usage (in GUI):
    from gui.routing_view import RoutingMatrixWidget, SessionTreeWidget

    matrix = RoutingMatrixWidget()
    matrix.load_session(session)

    tree = SessionTreeWidget()
    tree.load_session(session)
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSplitter, QTreeWidget, QTreeWidgetItem, QSizePolicy,
    QTabWidget,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPen

from models.session import Session
from models.track import Track, GROUP_COLORS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Session Tree Widget — hierarchical folder view
# ─────────────────────────────────────────────────────────────────────

class SessionTreeWidget(QTreeWidget):
    """
    Hierarchical tree view of the session structure.

    Shows:
    ┌─ DRUMS (10 tracks)
    │  ├─ ch1  Kick In
    │  ├─ ch2  Snare Top
    │  └─ ...
    ├─ VOCALS (4 tracks)
    │  └─ ch23 Lead Vox
    └─ Buses
       ├─ Drum Bus
       └─ Vocal Bus
    """

    TREE_STYLE = """
    QTreeWidget {
        background: #050A14;
        color: #CBD5E1;
        border: none;
        font-family: 'SF Mono', 'JetBrains Mono', 'Consolas', monospace;
        font-size: 11px;
    }
    QTreeWidget::item {
        padding: 3px 4px;
        border-bottom: 1px solid #0A0E1A;
    }
    QTreeWidget::item:selected { background: #1E293B; }
    QTreeWidget::item:hover    { background: #0F172A; }
    QHeaderView::section {
        background: #020509;
        color: #475569;
        border: none;
        border-bottom: 1px solid #1E293B;
        padding: 4px 8px;
        font-size: 10px;
        letter-spacing: 2px;
    }
    QTreeWidget::branch:has-children:!has-siblings:closed,
    QTreeWidget::branch:closed:has-children:has-siblings {
        image: none; border-image: none;
    }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHeaderLabels(["NAME", "CH", "TYPE", "OUTPUT"])
        self.setStyleSheet(self.TREE_STYLE)
        self.setAlternatingRowColors(False)
        self.setIndentation(16)
        self.setUniformRowHeights(True)

        header = self.header()
        header.setDefaultSectionSize(120)
        self.setColumnWidth(0, 200)
        self.setColumnWidth(1, 50)
        self.setColumnWidth(2, 70)

    def load_session(self, session: Session):
        """Populate the tree from a Session object."""
        self.clear()

        if not session or not session.tracks:
            placeholder = QTreeWidgetItem(self, ["No session loaded", "", "", ""])
            placeholder.setForeground(0, QBrush(QColor("#334155")))
            return

        # Group tracks into folder items
        groups_order = session.get_unique_groups()

        for group in groups_order:
            group_tracks = session.get_tracks_in_group(group)
            if not group_tracks:
                continue

            color = GROUP_COLORS.get(group, "#475569")
            q_color = QColor(color)

            # Folder item
            folder = QTreeWidgetItem(self)
            folder.setText(0, f"{group}  ({len(group_tracks)})")
            folder.setText(1, "")
            folder.setText(2, "folder")
            folder.setForeground(0, QBrush(q_color))
            folder.setFont(0, QFont("", -1, QFont.Weight.Bold))
            folder.setExpanded(True)

            for track in group_tracks:
                item = QTreeWidgetItem(folder)
                stereo = " ↔" if track.stereo_pair else ""
                item.setText(0, track.name + stereo)
                item.setText(1, str(track.channel))
                item.setText(2, track.track_type)
                item.setText(3, track.output)

                # Dim the channel number
                item.setForeground(1, QBrush(QColor("#475569")))
                item.setForeground(2, QBrush(QColor("#475569")))
                item.setForeground(3, QBrush(QColor("#475569")))

                # Color-code track name
                item.setForeground(0, QBrush(QColor("#CBD5E1")))

        # Buses section
        if session.buses:
            bus_root = QTreeWidgetItem(self)
            bus_root.setText(0, f"BUSES  ({len(session.buses)})")
            bus_root.setForeground(0, QBrush(QColor("#334155")))
            bus_root.setFont(0, QFont("", -1, QFont.Weight.Bold))
            bus_root.setExpanded(True)

            for bus in session.buses:
                b_item = QTreeWidgetItem(bus_root)
                b_item.setText(0, bus.name)
                b_item.setText(1, f"{len(bus.channels)} ch")
                b_item.setText(2, bus.bus_type)
                b_item.setForeground(0, QBrush(QColor("#64748B")))
                b_item.setForeground(1, QBrush(QColor("#334155")))


# ─────────────────────────────────────────────────────────────────────
# Routing Matrix Widget — channel × bus grid
# ─────────────────────────────────────────────────────────────────────

class RoutingCell(QFrame):
    """A single cell in the routing matrix grid."""

    def __init__(self, active: bool = False, color: str = "#1DB954", parent=None):
        super().__init__(parent)
        self.active = active
        self.cell_color = color
        self.setFixedSize(18, 18)
        self._update_style()

    def _update_style(self):
        if self.active:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {self.cell_color};
                    border-radius: 2px;
                    border: none;
                }}
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background: #0F172A;
                    border-radius: 2px;
                    border: 1px solid #1E293B;
                }
            """)


class RoutingMatrixWidget(QScrollArea):
    """
    Visual routing matrix showing which channels feed which buses.

    Rows = Tracks (console channels)
    Columns = Buses/Groups

    An active cell (■) means that track feeds that bus.

    Inspired by REAPER's routing matrix and Dante Controller.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setStyleSheet("""
            QScrollArea { border: none; background: #050A14; }
        """)
        self._session: Optional[Session] = None

        # Placeholder label
        self._placeholder = QLabel("Load a session to see the routing matrix")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #1E293B; font-size: 13px;")
        self.setWidget(self._placeholder)

    def load_session(self, session: Session):
        """Build the routing matrix from the session data."""
        self._session = session

        if not session or not session.tracks:
            self.setWidget(self._placeholder)
            return

        # Build the matrix grid
        grid_widget = self._build_matrix(session)
        self.setWidget(grid_widget)

    def _build_matrix(self, session: Session) -> QWidget:
        """
        Build the routing matrix as a grid of cells.

        Layout:
              [Bus 1] [Bus 2] [Bus 3]
        Ch 1:   ■       ·       ·
        Ch 2:   ■       ·       ·
        Ch 3:   ·       ■       ·
        """
        container = QWidget()
        container.setStyleSheet("background: #050A14;")

        # Get unique buses
        buses = session.buses if session.buses else []
        groups = session.get_unique_groups()

        # Main layout
        main = QVBoxLayout(container)
        main.setContentsMargins(16, 12, 16, 12)
        main.setSpacing(0)

        if not buses:
            lbl = QLabel("No buses defined. Apply a routing preset to see the matrix.")
            lbl.setStyleSheet("color: #334155; font-size: 12px; padding: 20px;")
            main.addWidget(lbl)
            return container

        # Header row (bus names)
        header_row = QHBoxLayout()
        header_row.setSpacing(2)

        # Corner spacer
        corner = QLabel("")
        corner.setFixedWidth(180)
        header_row.addWidget(corner)

        for bus in buses:
            bus_lbl = QLabel(bus.name[:12])
            bus_lbl.setFixedWidth(80)
            bus_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bus_lbl.setStyleSheet("color:#475569;font-size:9px;letter-spacing:1px;")
            bus_lbl.setWordWrap(True)
            header_row.addWidget(bus_lbl)

        header_row.addStretch()
        main.addLayout(header_row)

        # Separator
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background:#1E293B;max-height:1px;margin:4px 0;")
        main.addWidget(sep)

        # One row per track
        for track in session.tracks:
            row = QHBoxLayout()
            row.setSpacing(2)
            row.setContentsMargins(0, 1, 0, 1)

            # Track label
            color = GROUP_COLORS.get(track.group, "#475569")
            track_lbl = QLabel(f"  {track.channel:>3}  {track.name[:20]}")
            track_lbl.setFixedWidth(180)
            track_lbl.setStyleSheet(f"color:{color};font-size:11px;")
            row.addWidget(track_lbl)

            # One cell per bus
            for bus in buses:
                active = track.channel in bus.channels
                cell_color = GROUP_COLORS.get(track.group, "#1DB954")
                cell = RoutingCell(active=active, color=cell_color)
                cell_container = QWidget()
                cell_container.setFixedWidth(80)
                cl = QHBoxLayout(cell_container)
                cl.setContentsMargins(0, 0, 0, 0)
                cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cl.addWidget(cell)
                row.addWidget(cell_container)

            row.addStretch()
            main.addLayout(row)

        main.addStretch()
        return container


# ─────────────────────────────────────────────────────────────────────
# Combined Routing View (tabs: Tree + Matrix)
# ─────────────────────────────────────────────────────────────────────

class RoutingView(QWidget):
    """
    Combined routing view with tabs for Tree and Matrix views.

    This is the widget used in the main window's right panel
    when expanded to full routing view.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #050A14;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: #050A14; }
            QTabBar::tab {
                background: #050A14; color: #334155; border: none;
                padding: 6px 14px; font-size: 10px; letter-spacing: 1px;
            }
            QTabBar::tab:selected { color: #64748B; border-bottom: 1px solid #334155; }
        """)

        self.tree   = SessionTreeWidget()
        self.matrix = RoutingMatrixWidget()

        self.tabs.addTab(self.tree,   "STRUCTURE")
        self.tabs.addTab(self.matrix, "MATRIX")

        layout.addWidget(self.tabs)

    def load_session(self, session: Session):
        """Load a session into both sub-views."""
        self.tree.load_session(session)
        self.matrix.load_session(session)
