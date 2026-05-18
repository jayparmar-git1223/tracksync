# -*- mode: python ; coding: utf-8 -*-
"""
LiveConsoleDawMirror.spec — PyInstaller Build Specification

Builds Live Console → DAW Mirror into a standalone executable.

Build commands:
    # macOS / Linux:
    pyinstaller LiveConsoleDawMirror.spec

    # Windows:
    pyinstaller LiveConsoleDawMirror.spec

    # Output in:
    dist/LiveConsoleDawMirror (folder mode)
    dist/LiveConsoleDawMirror.app (macOS app bundle)

Manual one-liner (simpler):
    pyinstaller --onefile --windowed --name LiveConsoleDawMirror app.py

Notes:
- PySide6 requires --windowed (no console) for a clean GUI app
- The spec includes all src/ modules via pathex
- Templates and assets are included as datas
- On macOS, add an icon with --icon=assets/icon.icns
"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(SPECPATH)
SRC_DIR      = str(PROJECT_ROOT / "src")

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / "app.py")],
    pathex=[SRC_DIR, str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Include all template files
        (str(PROJECT_ROOT / "templates"), "templates"),
        # Include assets (icons, etc.) if they exist
        (str(PROJECT_ROOT / "assets"),    "assets"),
    ],
    hiddenimports=[
        # Ensure all parser modules are included
        "parser.digico_parser",
        "parser.yamaha_parser",
        "parser.allen_heath_parser",
        "parser.avid_parser",
        "parser.base_parser",
        # All exporters
        "exporters.reaper.reaper_exporter",
        "exporters.cubase.cubase_exporter",
        "exporters.nuendo.nuendo_exporter",
        "exporters.protools.protools_exporter",
        "exporters.ableton.ableton_exporter",
        "exporters.logic.logic_exporter",
        # GUI modules
        "gui.main_window",
        "gui.track_table",
        "gui.routing_view",
        "gui.settings_dialog",
        # Core modules
        "models.session",
        "models.track",
        "models.bus",
        "models.routing",
        "registry",
        "routing_presets",
        "session_diff",
        "settings",
        "logger",
        "dante_patchsheet",
        "template_engine",
        "osc_integration",
        # PySide6 modules needed
        "PySide6.QtWidgets",
        "PySide6.QtCore",
        "PySide6.QtGui",
        # Standard library
        "xml.etree.ElementTree",
        "xml.dom.minidom",
        "csv",
        "gzip",
        "struct",
        "socket",
        "hashlib",
        "logging.handlers",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused modules
        "numpy", "pandas", "matplotlib", "scipy",
        "PIL", "cv2", "tensorflow",
        "tkinter", "wx",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LiveConsoleDawMirror",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                      # No terminal window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/icon.icns",          # Uncomment and set path for custom icon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LiveConsoleDawMirror",
)

# macOS App Bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Live Console DAW Mirror.app",
        # icon="assets/icon.icns",
        bundle_identifier="io.liveconsole.dawmirror",
        info_plist={
            "CFBundleName":              "Live Console DAW Mirror",
            "CFBundleDisplayName":       "Live Console DAW Mirror",
            "CFBundleVersion":           "1.0.0",
            "CFBundleShortVersionString":"1.0.0",
            "NSHighResolutionCapable":   True,
            "LSMinimumSystemVersion":    "10.14",
            "NSRequiresAquaSystemAppearance": False,  # Allow dark mode
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeExtensions": ["rtf"],
                    "CFBundleTypeName":       "DiGiCo Session Report",
                    "CFBundleTypeRole":       "Viewer",
                },
                {
                    "CFBundleTypeExtensions": ["json"],
                    "CFBundleTypeName":       "Live Console Session JSON",
                    "CFBundleTypeRole":       "Editor",
                },
            ],
        },
    )
