"""
settings_dialog.py — Application Settings Dialog

A professional dark-themed settings dialog for Live Console → DAW Mirror.

Sections:
  - Export Settings (default DAW, output directory, behavior)
  - Parser Settings (auto-detect, sample rate, console hints)
  - Routing Presets (default preset, auto-apply)
  - GUI Settings (font size, display options)
  - Logging (level, file output)
  - About

Usage:
    from gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(settings, parent=self)
    if dialog.exec() == QDialog.Accepted:
        # settings already saved by dialog
        pass
"""

import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QComboBox, QCheckBox, QSpinBox, QLineEdit,
    QPushButton, QFileDialog, QFrame, QScrollArea,
    QDialogButtonBox, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)

DIALOG_STYLE = """
QDialog {
    background: #0A0E1A;
    color: #CBD5E1;
    font-family: 'SF Mono', 'JetBrains Mono', 'Consolas', monospace;
    font-size: 12px;
}
QTabWidget::pane {
    background: #050A14;
    border: 1px solid #1E293B;
    border-radius: 4px;
}
QTabBar::tab {
    background: #0A0E1A;
    color: #475569;
    border: none;
    padding: 8px 20px;
    font-size: 11px;
    letter-spacing: 1px;
}
QTabBar::tab:selected {
    background: #050A14;
    color: #1DB954;
    border-bottom: 2px solid #1DB954;
}
QTabBar::tab:hover { color: #94A3B8; }
QGroupBox {
    border: 1px solid #1E293B;
    border-radius: 4px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    color: #475569;
    font-size: 10px;
    letter-spacing: 2px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QLabel { color: #94A3B8; }
QLabel[role="heading"] { color: #64748B; font-size: 10px; letter-spacing: 1px; }
QComboBox, QLineEdit, QSpinBox {
    background: #0F172A;
    color: #CBD5E1;
    border: 1px solid #1E293B;
    border-radius: 4px;
    padding: 5px 8px;
    min-width: 180px;
}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border-color: #1DB954; }
QComboBox QAbstractItemView {
    background: #1E293B; color: #CBD5E1;
    border: 1px solid #334155; selection-background-color: #334155;
}
QCheckBox { color: #94A3B8; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #334155; border-radius: 3px; background: #0F172A;
}
QCheckBox::indicator:checked { background: #1DB954; border-color: #1DB954; }
QCheckBox::indicator:hover { border-color: #475569; }
QDialogButtonBox QPushButton {
    background: transparent; color: #CBD5E1;
    border: 1px solid #334155; border-radius: 4px;
    padding: 7px 20px; min-width: 80px;
}
QDialogButtonBox QPushButton:hover { background: #1E293B; border-color: #475569; }
QDialogButtonBox QPushButton[text="OK"] {
    background: #1DB954; color: #000; border: none; font-weight: 700;
}
QDialogButtonBox QPushButton[text="OK"]:hover { background: #1ED760; }
"""


def _section(title: str) -> QLabel:
    lbl = QLabel(title.upper())
    lbl.setProperty("role", "heading")
    lbl.setStyleSheet("color:#475569;font-size:10px;letter-spacing:2px;padding:8px 0 3px 0;")
    return lbl


def _divider() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("background:#1E293B;border:none;max-height:1px;margin:4px 0;")
    return f


def _dir_row(label: str, setting_key: str, settings) -> tuple[QWidget, QLineEdit]:
    """Create a row with a label, text input, and browse button."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label); lbl.setFixedWidth(160)
    edit = QLineEdit(str(settings.get(setting_key, "")))
    btn = QPushButton("Browse")
    btn.setFixedWidth(70)
    btn.setStyleSheet("""
        QPushButton { background: transparent; color: #475569;
            border: 1px solid #1E293B; border-radius: 3px; padding: 4px 8px; font-size: 11px; }
        QPushButton:hover { color: #94A3B8; border-color: #334155; }
    """)

    def _browse():
        d = QFileDialog.getExistingDirectory(row, f"Select {label}")
        if d: edit.setText(d)

    btn.clicked.connect(_browse)
    layout.addWidget(lbl); layout.addWidget(edit, 1); layout.addWidget(btn)
    return row, edit


class SettingsDialog(QDialog):
    """
    Application settings dialog.

    Opens modally. All changes are applied to the Settings object
    when the user clicks OK.

    Parameters
    ----------
    settings : Settings
        The application settings object to read from and write to.
    parent : QWidget
        The parent window.
    """

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings — Live Console → DAW Mirror")
        self.setMinimumSize(640, 520)
        self.setModal(True)
        self.setStyleSheet(DIALOG_STYLE)
        self._widgets: dict[str, object] = {}  # key → widget
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._tab_export(),   "Export")
        tabs.addTab(self._tab_parser(),   "Parser")
        tabs.addTab(self._tab_presets(),  "Presets")
        tabs.addTab(self._tab_gui(),      "Display")
        tabs.addTab(self._tab_logging(),  "Logging")
        tabs.addTab(self._tab_about(),    "About")
        layout.addWidget(tabs)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._on_reset
        )
        layout.addWidget(buttons)

    # ──────────────────────────────────────────────────────────────────
    # Tab builders
    # ──────────────────────────────────────────────────────────────────

    def _tab_export(self) -> QWidget:
        tab = self._scrollable_tab()
        layout = tab.layout()

        layout.addWidget(_section("Default DAW"))
        daw_combo = QComboBox()
        daw_combo.addItems(["REAPER", "Cubase", "Nuendo", "Pro Tools", "Ableton Live", "Logic Pro"])
        daw_combo.setCurrentText(self.settings.get("default_daw", "REAPER"))
        self._widgets["default_daw"] = daw_combo
        layout.addWidget(self._labeled_row("Default DAW", daw_combo))

        layout.addWidget(_divider())
        layout.addWidget(_section("Output Directory"))

        out_row, out_edit = _dir_row("Output directory", "last_output_dir", self.settings)
        self._widgets["last_output_dir"] = out_edit
        layout.addWidget(out_row)

        in_row, in_edit = _dir_row("Last input directory", "last_input_dir", self.settings)
        self._widgets["last_input_dir"] = in_edit
        layout.addWidget(in_row)

        layout.addWidget(_divider())
        layout.addWidget(_section("Export Behavior"))

        for key, label in [
            ("auto_open_after_export",    "Open exported file after export"),
            ("overwrite_without_confirm", "Overwrite existing files without confirmation"),
            ("include_timestamps",        "Include generation timestamps in exported files"),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(bool(self.settings.get(key, False)))
            self._widgets[key] = cb
            layout.addWidget(cb)

        layout.addStretch()
        return tab

    def _tab_parser(self) -> QWidget:
        tab = self._scrollable_tab()
        layout = tab.layout()

        layout.addWidget(_section("Auto-Detection"))
        for key, label in [
            ("auto_detect_stereo_pairs", "Auto-detect stereo pairs (L/R naming)"),
            ("auto_classify_groups",     "Auto-classify tracks into instrument groups"),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(bool(self.settings.get(key, True)))
            self._widgets[key] = cb
            layout.addWidget(cb)

        layout.addWidget(_divider())
        layout.addWidget(_section("Default Session Parameters"))

        sr_combo = QComboBox()
        sr_combo.addItems(["44100", "48000", "88200", "96000", "192000"])
        sr_combo.setCurrentText(str(self.settings.get("default_sample_rate", 48000)))
        self._widgets["default_sample_rate"] = sr_combo
        layout.addWidget(self._labeled_row("Default sample rate", sr_combo))

        bd_combo = QComboBox()
        bd_combo.addItems(["16", "24", "32"])
        bd_combo.setCurrentText(str(self.settings.get("default_bit_depth", 24)))
        self._widgets["default_bit_depth"] = bd_combo
        layout.addWidget(self._labeled_row("Default bit depth", bd_combo))

        layout.addWidget(_divider())
        layout.addWidget(_section("Console Hint"))
        console_combo = QComboBox()
        console_combo.addItems(["Auto-detect", "DiGiCo", "Yamaha", "Allen & Heath", "Avid S6L"])
        cur = self.settings.get("default_console", "Auto-detect")
        console_combo.setCurrentText(cur if cur in ["DiGiCo","Yamaha","Allen & Heath","Avid S6L"] else "Auto-detect")
        self._widgets["default_console"] = console_combo
        layout.addWidget(self._labeled_row("Preferred console brand", console_combo))

        layout.addStretch()
        return tab

    def _tab_presets(self) -> QWidget:
        tab = self._scrollable_tab()
        layout = tab.layout()

        layout.addWidget(_section("Routing Presets"))

        preset_combo = QComboBox()
        try:
            from routing_presets import PresetManager
            pm = PresetManager()
            for p in pm.list_presets():
                preset_combo.addItem(p.name)
            default = self.settings.get("default_preset", "live_show")
            # Find matching item
            for i in range(preset_combo.count()):
                if pm._slugify(preset_combo.itemText(i)) == default:
                    preset_combo.setCurrentIndex(i)
                    break
        except Exception:
            preset_combo.addItems(["live_show", "recording", "broadcast",
                                    "festival", "theatre", "playback"])

        self._widgets["default_preset"] = preset_combo
        layout.addWidget(self._labeled_row("Default routing preset", preset_combo))

        auto_cb = QCheckBox("Auto-apply default preset when loading a session")
        auto_cb.setChecked(bool(self.settings.get("auto_apply_preset", False)))
        self._widgets["auto_apply_preset"] = auto_cb
        layout.addWidget(auto_cb)

        layout.addWidget(_divider())
        layout.addWidget(_section("Custom Presets"))

        presets_row, presets_edit = _dir_row("Custom presets folder", "custom_presets_dir", self.settings)
        self._widgets["custom_presets_dir"] = presets_edit
        layout.addWidget(presets_row)

        layout.addStretch()
        return tab

    def _tab_gui(self) -> QWidget:
        tab = self._scrollable_tab()
        layout = tab.layout()

        layout.addWidget(_section("Display"))
        for key, label in [
            ("show_channel_numbers", "Show channel numbers in track table"),
            ("show_group_colors",    "Color-code tracks by instrument group"),
            ("show_stereo_pairs",    "Highlight stereo pairs"),
            ("remember_window_size", "Remember window size on exit"),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(bool(self.settings.get(key, True)))
            self._widgets[key] = cb
            layout.addWidget(cb)

        layout.addWidget(_divider())
        layout.addWidget(_section("Font Size"))
        font_spin = QSpinBox()
        font_spin.setRange(9, 18)
        font_spin.setValue(int(self.settings.get("font_size", 12)))
        self._widgets["font_size"] = font_spin
        layout.addWidget(self._labeled_row("Interface font size (px)", font_spin))

        layout.addStretch()
        return tab

    def _tab_logging(self) -> QWidget:
        tab = self._scrollable_tab()
        layout = tab.layout()

        layout.addWidget(_section("Log Level"))
        level_combo = QComboBox()
        level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        level_combo.setCurrentText(self.settings.get("log_level", "INFO"))
        self._widgets["log_level"] = level_combo
        layout.addWidget(self._labeled_row("Minimum log level", level_combo))

        layout.addWidget(_divider())
        log_cb = QCheckBox("Write logs to file (logs/session_export.log)")
        log_cb.setChecked(bool(self.settings.get("log_to_file", True)))
        self._widgets["log_to_file"] = log_cb
        layout.addWidget(log_cb)

        max_spin = QSpinBox()
        max_spin.setRange(50, 5000)
        max_spin.setSingleStep(50)
        max_spin.setValue(int(self.settings.get("max_log_lines", 500)))
        self._widgets["max_log_lines"] = max_spin
        layout.addWidget(self._labeled_row("Max lines in GUI log panel", max_spin))

        layout.addStretch()
        return tab

    def _tab_about(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        for line, style in [
            ("Live Console → DAW Mirror", "color:#1DB954;font-size:18px;font-weight:700;"),
            ("Version 1.0.0",             "color:#475569;font-size:12px;"),
            ("",                          ""),
            ("Professional live console session translation engine.",
             "color:#94A3B8;font-size:12px;"),
            ("Automatically mirrors live console sessions into DAW project files.",
             "color:#64748B;font-size:11px;"),
            ("", ""),
            ("Supported Consoles (Input)",     "color:#475569;font-size:10px;letter-spacing:2px;"),
            ("DiGiCo SD Range (.rtf)",         "color:#94A3B8;font-size:11px;"),
            ("Yamaha CL/QL Series (.cel, .csv)","color:#94A3B8;font-size:11px;"),
            ("Allen & Heath dLive/SQ/Avantis", "color:#94A3B8;font-size:11px;"),
            ("Avid S6L / VENUE (.csv)",        "color:#94A3B8;font-size:11px;"),
            ("", ""),
            ("Supported DAWs (Output)",        "color:#475569;font-size:10px;letter-spacing:2px;"),
            ("REAPER (.rpp)",                  "color:#94A3B8;font-size:11px;"),
            ("Cubase / Nuendo (Track Archive XML)", "color:#94A3B8;font-size:11px;"),
            ("Pro Tools (Session Info Text)",  "color:#94A3B8;font-size:11px;"),
            ("Ableton Live (.als)",            "color:#94A3B8;font-size:11px;"),
            ("Logic Pro (Channel Strip XML)",  "color:#94A3B8;font-size:11px;"),
            ("", ""),
            ("Built with Python 3.12 + PySide6", "color:#334155;font-size:10px;"),
        ]:
            lbl = QLabel(line)
            if style:
                lbl.setStyleSheet(style)
            layout.addWidget(lbl)

        layout.addStretch()
        return tab

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    def _scrollable_tab(self) -> QWidget:
        """Create a scrollable tab page."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        scroll.setWidget(inner)

        # Wrap scroll area in a plain widget so we can return a QWidget
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(scroll)
        wrapper.layout = lambda: layout   # expose inner layout
        return wrapper

    def _labeled_row(self, label: str, widget) -> QWidget:
        """A label + widget side by side."""
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 2, 0, 2)
        lbl = QLabel(label); lbl.setFixedWidth(220)
        rl.addWidget(lbl); rl.addWidget(widget); rl.addStretch()
        return row

    # ──────────────────────────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────────────────────────

    def _on_ok(self):
        """Collect all widget values and save to settings."""
        for key, widget in self._widgets.items():
            if isinstance(widget, QCheckBox):
                self.settings.set(key, widget.isChecked())
            elif isinstance(widget, QComboBox):
                val = widget.currentText()
                # Convert numeric strings back to int
                if key in ("default_sample_rate", "default_bit_depth",
                            "font_size", "max_log_lines"):
                    try:
                        val = int(val)
                    except ValueError:
                        pass
                self.settings.set(key, val)
            elif isinstance(widget, QLineEdit):
                self.settings.set(key, widget.text().strip())
            elif isinstance(widget, QSpinBox):
                self.settings.set(key, widget.value())

        logger.info("[INFO] Settings: Saved from dialog")
        self.accept()

    def _on_reset(self):
        """Reset all settings to defaults and close."""
        self.settings.reset_to_defaults()
        logger.info("[INFO] Settings: Reset to defaults")
        self.reject()  # Close without saving (already saved by reset)
