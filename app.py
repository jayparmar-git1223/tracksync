"""
app.py — Application Entry Point

Live Console → DAW Mirror
Version 1.0.0

Run this file to start the application:
    python app.py

Or build a standalone executable with PyInstaller:
    pyinstaller --onefile --windowed app.py

This file:
1. Sets up the logging system
2. Creates the QApplication
3. Launches the main window
"""

import sys
import os
import logging

# ── Add src/ to the Python path ─────────────────────────────────────
# This allows all imports like `from models.session import Session`
# to work whether running from the project root or from src/.
SRC_DIR = os.path.join(os.path.dirname(__file__), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# ── Set up logging before importing anything else ───────────────────
from logger import setup_logging
setup_logging(log_dir="logs")

logger = logging.getLogger(__name__)

# ── Now import Qt and the GUI ────────────────────────────────────────
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from gui.main_window import MainWindow


def main():
    """Application entry point."""

    # High-DPI support (PySide6 handles this automatically in Qt 6)
    app = QApplication(sys.argv)
    app.setApplicationName("Live Console DAW Mirror")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Live Console")

    # Set the application-wide dark palette as fallback
    app.setStyle("Fusion")

    logger.info("[INFO] Starting Live Console → DAW Mirror")

    # Launch the main window
    window = MainWindow()
    window.show()

    # Run the Qt event loop
    exit_code = app.exec()
    logger.info(f"[INFO] Application exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
