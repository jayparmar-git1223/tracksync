"""
main_window.py — Main Application Window

Live Console → DAW Mirror
Professional audio workflow utility

This is the root PySide6 window. It assembles all panels and
coordinates the core application workflow:

    Load Session File
         ↓
    Parse (DiGiCo RTF → Universal JSON)
         ↓
    Display in Track Table
         ↓
    Select DAW Target
         ↓
    Export DAW Project File

Layout:
    ┌─────────────────────────────────────────────────────────┐
    │  HEADER: Live Console → DAW Mirror                      │
    ├────────┬──────────────────────────────┬─────────────────┤
    │  LEFT  │    CENTER (Track Table)      │    RIGHT        │
    │  Panel │                              │  Session Info   │
    ├────────┴──────────────────────────────┴─────────────────┤
    │  LOG PANEL  │  Progress  │         [GENERATE SESSION]   │
    └─────────────────────────────────────────────────────────┘
"""

import sys
import logging
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QProgressBar,
    QTextEdit, QFrame, QComboBox, QSplitter,
    QStatusBar, QMessageBox, QApplication, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QSize
from PySide6.QtGui import QFont, QIcon, QColor, QPalette, QDragEnterEvent, QDropEvent

from gui.track_table import TrackTableWidget
from gui.routing_view import RoutingView
from models.session import Session

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Worker Thread — keeps the GUI responsive during parse/export
# ─────────────────────────────────────────────────────────────────────

class WorkerSignals(QObject):
    """Signals emitted by the worker thread back to the GUI."""
    progress       = Signal(int)          # 0–100
    status         = Signal(str)          # status bar message
    log            = Signal(str, str)     # (level, message)
    session_ready  = Signal(object)       # Session object after parse
    export_done    = Signal(str)          # output file path
    error          = Signal(str)          # error message


class ParseWorker(QThread):
    """Runs the console parser in a background thread."""

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.log.emit("INFO", f"[INFO] Loading: {self.file_path}")
            self.signals.progress.emit(10)

            suffix = Path(self.file_path).suffix.lower()

            # Universal Session JSON — load directly, no parser needed
            if suffix == ".json":
                session = Session.load_json(self.file_path)
                self.signals.progress.emit(100)
                self.signals.log.emit("INFO",
                    f"[SUCCESS] Loaded JSON: {session.get_track_count()} tracks")
                self.signals.session_ready.emit(session)
                return

            # Use the registry to auto-detect the right parser
            from registry import get_parser, detect_parser_for_file

            parser = get_parser(suffix)
            if parser is None:
                parser = detect_parser_for_file(self.file_path)

            if parser is None:
                self.signals.error.emit(
                    f"No parser available for \'{Path(self.file_path).name}\'\n\n"
                    f"Supported console formats:\n"
                    f"  • DiGiCo SD Range          .rtf\n"
                    f"  • Yamaha RIVAGE PM         .RIVAGEPM\n"
                    f"  • Yamaha CL/QL             .cel  .csv\n"
                    f"  • Allen & Heath dLive/SQ   .scene  .csv\n"
                    f"  • Avid S6L / VENUE         .csv\n"
                    f"  • Universal Session JSON   .json"
                )
                return

            self.signals.log.emit("INFO",
                f"[INFO] Using: {parser.__class__.__name__}")
            self.signals.progress.emit(30)

            session = parser.parse(self.file_path)
            self.signals.progress.emit(90)

            self.signals.log.emit("INFO",
                f"[SUCCESS] Parsed {session.get_track_count()} tracks"
                f" from {session.console}")
            self.signals.progress.emit(100)
            self.signals.session_ready.emit(session)

        except FileNotFoundError as e:
            self.signals.error.emit(f"File not found:\n{e}")
        except Exception as e:
            self.signals.error.emit(f"Parse error:\n{e}")
            logger.exception("ParseWorker crashed")


class ExportWorker(QThread):
    """Runs the DAW exporter in a background thread."""

    def __init__(self, session: Session, daw: str, output_path: str):
        super().__init__()
        self.session     = session
        self.daw         = daw
        self.output_path = output_path
        self.signals     = WorkerSignals()

    def run(self):
        try:
            self.signals.progress.emit(10)
            self.signals.log.emit("INFO", f"[INFO] Exporting → {self.daw}...")

            # Use registry for all DAW lookup
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from registry import get_exporter
            exporter = get_exporter(self.daw)

            if not exporter:
                # Fallback for names with spaces
                daw_map = {
                    "REAPER": "REAPER", "Cubase": "Cubase", "Nuendo": "Nuendo",
                    "Pro Tools": "Pro Tools", "Ableton Live": "Ableton Live",
                    "Logic Pro": "Logic Pro",
                }
                exporter = get_exporter(daw_map.get(self.daw, self.daw))

            if not exporter:
                self.signals.error.emit(f"Unknown DAW: {self.daw}")
                return

            self.signals.progress.emit(50)
            out = exporter.export(self.session, self.output_path)
            self.signals.progress.emit(100)
            self.signals.log.emit("INFO", f"[SUCCESS] Exported: {out}")
            self.signals.export_done.emit(out)

        except Exception as e:
            self.signals.error.emit(f"Export error: {e}")
            logger.exception("ExportWorker crashed")


# ─────────────────────────────────────────────────────────────────────
# Styled widgets
# ─────────────────────────────────────────────────────────────────────

class SectionLabel(QLabel):
    """A styled section header label."""
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QLabel {
                color: #7F8C9A;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
                text-transform: uppercase;
                padding: 8px 0 4px 0;
            }
        """)


class ActionButton(QPushButton):
    """Primary action button — dark bordered style."""
    def __init__(self, text: str, accent: bool = False, parent=None):
        super().__init__(text, parent)
        if accent:
            self.setStyleSheet("""
                QPushButton {
                    background: #1DB954;
                    color: #000000;
                    border: none;
                    border-radius: 4px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 700;
                    letter-spacing: 1px;
                }
                QPushButton:hover {
                    background: #1ED760;
                }
                QPushButton:pressed {
                    background: #17A34A;
                }
                QPushButton:disabled {
                    background: #1A3326;
                    color: #2D6644;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #CBD5E1;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: #1E293B;
                    border-color: #475569;
                    color: #F1F5F9;
                }
                QPushButton:pressed {
                    background: #0F172A;
                }
                QPushButton:disabled {
                    color: #334155;
                    border-color: #1E293B;
                }
            """)


class Divider(QFrame):
    """Horizontal separator line."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet("background: #1E293B; border: none; max-height: 1px;")


# ─────────────────────────────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """
    The root application window for Live Console → DAW Mirror.

    Manages the complete workflow from file load to DAW export.
    Uses worker threads for all file I/O and parsing.
    """

    APP_NAME    = "Live Console → DAW Mirror"
    APP_VERSION = "1.0.0"

    def __init__(self):
        super().__init__()
        self.session: Session | None = None  # Currently loaded session
        self._setup_window()
        self._apply_dark_theme()
        self._build_ui()
        self._connect_signals()
        self._update_ui_state()
        logger.info(f"[INFO] {self.APP_NAME} v{self.APP_VERSION} started")

    # ──────────────────────────────────────────────────────────────────
    # Window setup
    # ──────────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle(self.APP_NAME)
        self.setMinimumSize(1200, 780)
        self.resize(1440, 860)
        # Allow drag-and-drop of session files onto the window
        self.setAcceptDrops(True)

    def _apply_dark_theme(self):
        """Apply a professional dark theme to the entire application."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0A0E1A;
                color: #CBD5E1;
                font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
                font-size: 12px;
            }

            QScrollBar:vertical {
                background: #0F172A;
                width: 8px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #475569; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

            QScrollBar:horizontal {
                background: #0F172A;
                height: 8px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background: #334155;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover { background: #475569; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

            QComboBox {
                background: #0F172A;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QComboBox:hover { border-color: #475569; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: #1E293B;
                color: #CBD5E1;
                border: 1px solid #334155;
                selection-background-color: #334155;
            }

            QTextEdit {
                background: #050A14;
                color: #4ADE80;
                border: 1px solid #1E293B;
                border-radius: 4px;
                font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
                font-size: 11px;
                padding: 6px;
            }

            QProgressBar {
                background: #0F172A;
                border: 1px solid #1E293B;
                border-radius: 4px;
                height: 6px;
                text-align: center;
                color: transparent;
            }
            QProgressBar::chunk {
                background: #1DB954;
                border-radius: 3px;
            }

            QStatusBar {
                background: #050A14;
                color: #475569;
                border-top: 1px solid #1E293B;
                font-size: 11px;
            }

            QSplitter::handle {
                background: #1E293B;
                width: 2px;
                height: 2px;
            }

            QMessageBox {
                background: #0F172A;
                color: #CBD5E1;
            }
            QMessageBox QPushButton {
                background: #1E293B;
                color: #CBD5E1;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 6px 16px;
                min-width: 80px;
            }
        """)

    # ──────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        """Assemble all UI panels into the main window layout."""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Header
        root_layout.addWidget(self._build_header())

        # Main content area (left + center + right)
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.addWidget(self._build_left_panel())
        content_splitter.addWidget(self._build_center_panel())
        content_splitter.addWidget(self._build_right_panel())
        content_splitter.setSizes([220, 800, 260])
        content_splitter.setCollapsible(0, False)
        content_splitter.setCollapsible(1, False)
        root_layout.addWidget(content_splitter, stretch=1)

        # Bottom panel (logs + progress + export button)
        root_layout.addWidget(Divider())
        root_layout.addWidget(self._build_bottom_panel())

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready — drag a console session file here or use Load Session")

    def _build_header(self) -> QWidget:
        """Build the top header bar."""
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet("""
            QWidget {
                background: #050A14;
                border-bottom: 1px solid #1E293B;
            }
        """)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)

        # App title
        title = QLabel("⬤  LIVE CONSOLE  →  DAW MIRROR")
        title.setStyleSheet("""
            QLabel {
                color: #1DB954;
                font-size: 14px;
                font-weight: 700;
                letter-spacing: 3px;
            }
        """)
        layout.addWidget(title)
        layout.addStretch()

        # Version badge
        version = QLabel(f"v{self.APP_VERSION}")
        version.setStyleSheet("color: #334155; font-size: 11px;")
        layout.addWidget(version)

        return header

    def _build_left_panel(self) -> QWidget:
        """Build the left control panel."""
        panel = QWidget()
        panel.setFixedWidth(220)
        panel.setStyleSheet("background: #050A14; border-right: 1px solid #1E293B;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        # ── Session section ──────────────────────────────────────────
        layout.addWidget(SectionLabel("SESSION"))

        self.btn_load = ActionButton("⬆  Load Session", parent=self)
        self.btn_load.clicked.connect(self._on_load_session)
        layout.addWidget(self.btn_load)

        self.btn_save_json = ActionButton("↓  Save as JSON", parent=self)
        self.btn_save_json.clicked.connect(self._on_save_json)
        layout.addWidget(self.btn_save_json)

        layout.addSpacing(8)
        layout.addWidget(Divider())
        layout.addSpacing(8)

        # ── Export section ───────────────────────────────────────────
        layout.addWidget(SectionLabel("TARGET DAW"))

        self.daw_combo = QComboBox()
        self.daw_combo.addItems(["REAPER", "Cubase", "Nuendo", "Pro Tools", "Ableton Live", "Logic Pro"])
        layout.addWidget(self.daw_combo)

        layout.addSpacing(8)
        layout.addWidget(Divider())
        layout.addSpacing(8)

        # ── Session info ─────────────────────────────────────────────
        layout.addWidget(SectionLabel("SESSION INFO"))

        self.lbl_console      = self._info_label("Console", "—")
        self.lbl_tracks       = self._info_label("Tracks", "—")
        self.lbl_sample_rate  = self._info_label("Sample Rate", "—")
        self.lbl_bit_depth    = self._info_label("Bit Depth", "—")

        for lbl in [self.lbl_console, self.lbl_tracks, self.lbl_sample_rate, self.lbl_bit_depth]:
            layout.addWidget(lbl)

        layout.addStretch()

        # ── Routing & tools section ──────────────────────────────────
        layout.addWidget(Divider())
        layout.addSpacing(4)
        layout.addWidget(SectionLabel("ROUTING & TOOLS"))

        self.btn_apply_preset = ActionButton("⟳  Apply Preset", parent=self)
        self.btn_apply_preset.clicked.connect(self._on_apply_preset)
        layout.addWidget(self.btn_apply_preset)

        self.btn_export_dante = ActionButton("⬡  Dante Patch Sheet", parent=self)
        self.btn_export_dante.clicked.connect(self._on_export_dante)
        layout.addWidget(self.btn_export_dante)

        self.btn_session_diff = ActionButton("≠  Compare Sessions", parent=self)
        self.btn_session_diff.clicked.connect(self._on_session_diff)
        layout.addWidget(self.btn_session_diff)

        layout.addSpacing(4)
        layout.addWidget(Divider())
        layout.addSpacing(4)

        self.btn_settings = ActionButton("⚙  Settings", parent=self)
        self.btn_settings.clicked.connect(self._on_open_settings)
        layout.addWidget(self.btn_settings)

        return panel

    def _info_label(self, label: str, value: str) -> QWidget:
        """Create a two-line info display (label + value)."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(1)

        lbl = QLabel(label.upper())
        lbl.setStyleSheet("color: #475569; font-size: 10px; letter-spacing: 1px;")

        val = QLabel(value)
        val.setStyleSheet("color: #94A3B8; font-size: 12px;")
        val.setObjectName(f"info_{label.lower().replace(' ', '_')}")

        layout.addWidget(lbl)
        layout.addWidget(val)
        return container

    def _build_center_panel(self) -> QWidget:
        """Build the center track table panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sub-header
        subheader = QWidget()
        subheader.setFixedHeight(38)
        subheader.setStyleSheet("background: #050A14; border-bottom: 1px solid #1E293B;")
        sh_layout = QHBoxLayout(subheader)
        sh_layout.setContentsMargins(16, 0, 16, 0)

        self.lbl_session_name = QLabel("No Session Loaded")
        self.lbl_session_name.setStyleSheet("color: #64748B; font-size: 12px;")
        sh_layout.addWidget(self.lbl_session_name)
        sh_layout.addStretch()

        self.lbl_track_count = QLabel("")
        self.lbl_track_count.setStyleSheet("color: #334155; font-size: 11px;")
        sh_layout.addWidget(self.lbl_track_count)

        layout.addWidget(subheader)

        # Drop zone overlay (shown when no session loaded)
        self.drop_zone = DropZone(self)
        layout.addWidget(self.drop_zone)

        # Track table (shown when session loaded)
        self.track_table = TrackTableWidget()
        self.track_table.setVisible(False)
        layout.addWidget(self.track_table, stretch=1)

        return panel

    def _build_right_panel(self) -> QWidget:
        """Build the right routing/session view panel."""
        panel = QWidget()
        panel.setStyleSheet("background: #050A14; border-left: 1px solid #1E293B;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Section header
        header = QWidget()
        header.setFixedHeight(32)
        header.setStyleSheet("background: #020509; border-bottom: 1px solid #1E293B;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 0, 12, 0)
        lbl = QLabel("SESSION OVERVIEW")
        lbl.setStyleSheet("color:#334155;font-size:10px;letter-spacing:2px;")
        hl.addWidget(lbl)
        layout.addWidget(header)

        # Routing view (tree + matrix tabs)
        self.routing_view = RoutingView()
        layout.addWidget(self.routing_view, stretch=1)

        # Text preview (fallback / summary)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Load a session to see preview...")
        self.preview_text.setFixedHeight(120)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background: #020509;
                color: #475569;
                border: none;
                border-top: 1px solid #1E293B;
                font-size: 10px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.preview_text)
        return panel

    def _build_bottom_panel(self) -> QWidget:
        """Build the bottom log + export panel."""
        panel = QWidget()
        panel.setFixedHeight(180)
        panel.setStyleSheet("background: #050A14;")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        # Log area
        log_section = QWidget()
        log_layout = QVBoxLayout(log_section)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_header.addWidget(SectionLabel("ACTIVITY LOG"))
        log_header.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(50, 20)
        clear_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #334155;
                border: 1px solid #1E293B;
                border-radius: 3px;
                font-size: 10px;
            }
            QPushButton:hover { color: #64748B; border-color: #334155; }
        """)
        clear_btn.clicked.connect(lambda: self.log_panel.clear())
        log_header.addWidget(clear_btn)
        log_layout.addLayout(log_header)

        self.log_panel = QTextEdit()
        self.log_panel.setReadOnly(True)
        self.log_panel.setStyleSheet("""
            QTextEdit {
                background: #020509;
                color: #22C55E;
                border: 1px solid #1E293B;
                border-radius: 4px;
                font-family: 'SF Mono', 'JetBrains Mono', 'Consolas', monospace;
                font-size: 11px;
                padding: 6px;
            }
        """)
        log_layout.addWidget(self.log_panel)
        layout.addWidget(log_section, stretch=1)

        # Export controls (right side of bottom panel)
        export_section = QWidget()
        export_section.setFixedWidth(240)
        export_layout = QVBoxLayout(export_section)
        export_layout.setContentsMargins(0, 0, 0, 0)
        export_layout.setSpacing(8)
        export_layout.addWidget(SectionLabel("EXPORT"))

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(6)
        export_layout.addWidget(self.progress_bar)

        self.lbl_progress = QLabel("Idle")
        self.lbl_progress.setStyleSheet("color: #475569; font-size: 11px;")
        export_layout.addWidget(self.lbl_progress)

        export_layout.addStretch()

        self.btn_generate = ActionButton("⚡  GENERATE SESSION", accent=True, parent=self)
        self.btn_generate.setFixedHeight(48)
        self.btn_generate.clicked.connect(self._on_generate)
        export_layout.addWidget(self.btn_generate)

        layout.addWidget(export_section)

        return panel

    # ──────────────────────────────────────────────────────────────────
    # Signal connections
    # ──────────────────────────────────────────────────────────────────

    def _connect_signals(self):
        """Wire up all UI signals and slots."""
        # Logging → GUI forwarding
        from logger import GUILogHandler
        handler = GUILogHandler(signal_callback=self._on_log_message)
        handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(handler)

    # ──────────────────────────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────────────────────────

    def _on_load_session(self):
        """Open file dialog to load a console session file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Console Session",
            "",
            "All Console Sessions (*.rtf *.RIVAGEPM *.cel *.scene *.csv *.json);; DiGiCo (.rtf);;Yamaha RIVAGE PM (.RIVAGEPM);;Yamaha CL/QL (.cel);; Allen & Heath (.scene);;CSV Sessions (.csv);;JSON Sessions (.json);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, file_path: str):
        """Start the parse worker for the given file."""
        self._log(f"[INFO] Loading: {file_path}")
        self.progress_bar.setValue(0)
        self.lbl_progress.setText("Parsing...")
        self.btn_generate.setEnabled(False)

        self._parse_worker = ParseWorker(file_path)
        self._parse_worker.signals.progress.connect(self.progress_bar.setValue)
        self._parse_worker.signals.log.connect(self._on_log_message)
        self._parse_worker.signals.session_ready.connect(self._on_session_ready)
        self._parse_worker.signals.error.connect(self._on_error)
        self._parse_worker.start()

    def _on_session_ready(self, session: Session):
        """Called when the parser has finished and returned a Session."""
        self.session = session

        # Update track table
        self.drop_zone.setVisible(False)
        self.track_table.setVisible(True)
        self.track_table.load_session(session)

        # Update routing view
        self.routing_view.load_session(session)

        # Update info panel
        self.lbl_session_name.setText(session.session_name)
        self.lbl_session_name.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        self.lbl_track_count.setText(f"{session.get_track_count()} tracks")

        self._update_info_labels(session)
        self._update_preview(session)
        self._update_ui_state()
        self.status_bar.showMessage(
            f"Loaded: {session.session_name}  |  "
            f"{session.get_track_count()} tracks  |  "
            f"{session.console}"
        )
        self.lbl_progress.setText("Parse complete")

    def _on_apply_preset(self):
        """Apply a routing preset to the current session."""
        if not self.session:
            return

        from PySide6.QtWidgets import QInputDialog
        try:
            from routing_presets import PresetManager
            pm = PresetManager()
            presets = pm.list_presets()
            preset_names = [p.name for p in presets]

            name, ok = QInputDialog.getItem(
                self, "Apply Routing Preset",
                "Select a routing preset to apply:",
                preset_names, 0, False
            )
            if ok and name:
                self.session = pm.apply_preset(self.session, name)
                self.track_table.load_session(self.session)
                self.routing_view.load_session(self.session)
                self._update_preview(self.session)
                self._log(f"[SUCCESS] Applied preset: {name}")
                self.status_bar.showMessage(f"Preset applied: {name}")
        except Exception as e:
            self._on_error(f"Could not apply preset: {e}")

    def _on_export_dante(self):
        """Export a Dante patch sheet for the current session."""
        if not self.session:
            return

        from PySide6.QtWidgets import QInputDialog
        console_device, ok1 = QInputDialog.getText(
            self, "Dante Patch Sheet",
            "Console Dante device name:", text=f"{self.session.console} Interface"
        )
        if not ok1:
            return
        daw_device, ok2 = QInputDialog.getText(
            self, "Dante Patch Sheet",
            "DAW Dante device name:", text="DAW Interface"
        )
        if not ok2:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Dante Patch Sheet",
            f"output/{self.session.session_name}_dante",
            "All Files (*)"
        )
        if not path:
            return

        try:
            from dante_patchsheet import DantePatchSheetExporter
            exporter = DantePatchSheetExporter(
                console_device=console_device,
                daw_device=daw_device,
            )
            outputs = exporter.export(self.session, path)
            self._log(f"[SUCCESS] Dante patch sheet exported: {list(outputs.values())}")
            self.status_bar.showMessage(f"Dante patch sheet: {len(outputs)} files exported")
            QMessageBox.information(
                self, "Dante Patch Sheet Exported",
                "Files exported:\n\n" + "\n".join(outputs.values())
            )
        except Exception as e:
            self._on_error(f"Dante export failed: {e}")

    def _on_session_diff(self):
        """Compare the current session against another file."""
        if not self.session:
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Compare With Session",
            "", "Session Files (*.rtf *.json);;All Files (*)"
        )
        if not path:
            return

        try:
            from pathlib import Path as _Path
            suffix = _Path(path).suffix.lower()
            if suffix == ".json":
                session_b = Session.load_json(path)
            else:
                from registry import detect_parser_for_file
                parser = detect_parser_for_file(path)
                if not parser:
                    self._on_error(f"No parser found for {path}")
                    return
                session_b = parser.parse(path)

            from session_diff import SessionDiff
            diff = SessionDiff(
                self.session, session_b,
                label_a=self.session.session_name,
                label_b=session_b.session_name,
            )
            report = diff.report()

            # Show in log panel
            self.log_panel.append("\n" + report)
            scrollbar = self.log_panel.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

            count = len(diff.compare())
            self.status_bar.showMessage(
                f"Session diff: {count} difference(s) between "
                f"'{self.session.session_name}' and '{session_b.session_name}'"
            )
        except Exception as e:
            self._on_error(f"Session diff failed: {e}")

    def _on_open_settings(self):
        """Open the settings dialog."""
        try:
            from gui.settings_dialog import SettingsDialog
            from settings import Settings
            s = Settings()
            dialog = SettingsDialog(s, parent=self)
            dialog.exec()
        except Exception as e:
            self._log(f"[WARNING] Could not open settings: {e}")

    def _on_generate(self):
        """Export the current session to the selected DAW format."""
        if not self.session:
            return

        daw = self.daw_combo.currentText()

        # File extension per DAW
        ext_map = {
            "REAPER":       "*.rpp",
            "Cubase":       "*.xml",
            "Nuendo":       "*.xml",
            "Pro Tools":    "*.txt",
            "Ableton Live": "*.als",
            "Logic Pro":    "*.txt",
        }
        ext = ext_map.get(daw, "*.*")

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {daw} Session",
            f"output/{self.session.session_name}",
            f"{daw} Session ({ext});;All Files (*)"
        )

        if not output_path:
            return

        self._log(f"[INFO] Exporting → {daw}: {output_path}")
        self.progress_bar.setValue(0)
        self.lbl_progress.setText(f"Exporting → {daw}...")
        self.btn_generate.setEnabled(False)

        # Get the potentially-edited session from the table
        edited_session = self.track_table.get_session()
        if edited_session:
            self.session = edited_session

        self._export_worker = ExportWorker(self.session, daw, output_path)
        self._export_worker.signals.progress.connect(self.progress_bar.setValue)
        self._export_worker.signals.log.connect(self._on_log_message)
        self._export_worker.signals.export_done.connect(self._on_export_done)
        self._export_worker.signals.error.connect(self._on_error)
        self._export_worker.start()

    def _on_export_done(self, output_path: str):
        """Called when export completes successfully."""
        self.btn_generate.setEnabled(True)
        self.lbl_progress.setText("Export complete ✓")
        self.status_bar.showMessage(f"Exported: {output_path}")
        QMessageBox.information(
            self,
            "Export Complete",
            f"Session exported successfully!\n\n{output_path}"
        )

    def _on_save_json(self):
        """Save the current session as a Universal Session JSON file."""
        if not self.session:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Universal Session JSON",
            f"output/{self.session.session_name}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        if path:
            self.session.save_json(path)
            self._log(f"[SUCCESS] Session saved as JSON: {path}")
            self.status_bar.showMessage(f"Saved: {path}")

    def _on_error(self, message: str):
        """Display an error dialog and reset progress."""
        self.btn_generate.setEnabled(self.session is not None)
        self.lbl_progress.setText("Error")
        self._log(f"[ERROR] {message}")
        QMessageBox.critical(self, "Error", message)

    def _on_log_message(self, level: str, message: str):
        """Append a log message to the GUI log panel."""
        self._log(message)

    def _log(self, message: str):
        """Append a line to the activity log panel."""
        self.log_panel.append(message)
        # Auto-scroll to bottom
        scrollbar = self.log_panel.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ──────────────────────────────────────────────────────────────────
    # UI state management
    # ──────────────────────────────────────────────────────────────────

    def _update_ui_state(self):
        """Enable/disable controls based on current application state."""
        has_session = self.session is not None
        self.btn_generate.setEnabled(has_session)
        self.btn_save_json.setEnabled(has_session)
        self.daw_combo.setEnabled(has_session)
        self.btn_apply_preset.setEnabled(has_session)
        self.btn_export_dante.setEnabled(has_session)
        self.btn_session_diff.setEnabled(has_session)

    def _update_info_labels(self, session: Session):
        """Update the session info labels in the left panel."""
        def _set(widget: QWidget, value: str):
            val_label = widget.findChild(QLabel, widget.children()[2].objectName())
            if val_label:
                val_label.setText(value)

        # Update via direct label access
        for child in self.lbl_console.findChildren(QLabel):
            if child.styleSheet().startswith("color: #94"):
                child.setText(session.console)
                break

        for child in self.lbl_tracks.findChildren(QLabel):
            if child.styleSheet().startswith("color: #94"):
                child.setText(str(session.get_track_count()))
                break

        for child in self.lbl_sample_rate.findChildren(QLabel):
            if child.styleSheet().startswith("color: #94"):
                child.setText(f"{session.sample_rate} Hz")
                break

        for child in self.lbl_bit_depth.findChildren(QLabel):
            if child.styleSheet().startswith("color: #94"):
                child.setText(f"{session.bit_depth}-bit")
                break

    def _update_preview(self, session: Session):
        """Update the right panel session preview with session data."""
        lines = [
            f"SESSION: {session.session_name}",
            f"CONSOLE: {session.console}",
            f"TRACKS:  {session.get_track_count()}",
            f"RATE:    {session.sample_rate} Hz / {session.bit_depth}-bit",
            "",
            "─" * 32,
            "GROUPS",
            "─" * 32,
        ]

        for group in session.get_unique_groups():
            tracks = session.get_tracks_in_group(group)
            lines.append(f"  {group} ({len(tracks)} tracks)")

        lines += ["", "─" * 32, "TRACKS", "─" * 32]

        for t in session.tracks:
            stereo = f" ↔ {t.stereo_pair}" if t.stereo_pair else ""
            lines.append(f"  {t.channel:>3}  {t.name:<22} {t.group[:8]}{stereo}")

        if session.buses:
            lines += ["", "─" * 32, "BUSES", "─" * 32]
            for b in session.buses:
                lines.append(f"  {b.name}")

        self.preview_text.setPlainText("\n".join(lines))

    # ──────────────────────────────────────────────────────────────────
    # Drag & Drop
    # ──────────────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept drag events for .rtf, .json, and .RIVAGEPM files."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith((".rtf", ".json", ".rivagepm", ".cel", ".scene", ".csv")):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle dropped session files."""
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".rtf", ".json", ".rivagepm", ".cel", ".scene", ".csv")):
                self._load_file(path)
                break


# ─────────────────────────────────────────────────────────────────────
# Drop Zone widget (shown before a session is loaded)
# ─────────────────────────────────────────────────────────────────────

class DropZone(QWidget):
    """
    A large drag-and-drop target shown in the center panel
    when no session has been loaded yet.
    """

    def __init__(self, main_window: MainWindow):
        super().__init__()
        self.main_window = main_window
        self.setAcceptDrops(True)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("⬡")
        icon.setStyleSheet("color: #1E293B; font-size: 64px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel("Drop Console Session Here")
        title.setStyleSheet("color: #334155; font-size: 18px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("DiGiCo .rtf  •  Yamaha .RIVAGEPM  •  Allen & Heath .scene  •  CSV  •  JSON")
        subtitle.setStyleSheet("color: #1E293B; font-size: 12px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".rtf", ".json", ".rivagepm", ".cel", ".scene", ".csv")):
                self.main_window._load_file(path)
                break
