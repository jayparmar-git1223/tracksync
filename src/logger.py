"""
logger.py — Professional Logging System

Sets up the application-wide logging configuration.

Log levels used throughout the app:
    [INFO]    — Normal operation messages
    [WARNING] — Non-fatal issues (e.g. a track name couldn't be parsed)
    [ERROR]   — Recoverable errors
    [SUCCESS] — Key milestone completions (custom level via INFO)
    [DEBUG]   — Verbose developer output

Logs are written to:
    - Console (terminal) in development
    - logs/session_export.log  (file, always)
    - The GUI log panel (via the signal system)

Usage:
    from logger import setup_logging
    setup_logging()

    import logging
    logger = logging.getLogger(__name__)
    logger.info("[SUCCESS] Session exported successfully")
"""

import logging
import logging.handlers
from pathlib import Path


def setup_logging(log_dir: str = "logs", level: int = logging.DEBUG) -> None:
    """
    Configure the global logging system.

    Creates the log directory if it doesn't exist.
    Sets up both file and console handlers.

    Parameters
    ----------
    log_dir : str
        Directory where log files are stored.
    level : int
        The minimum log level to capture.
        logging.DEBUG captures everything.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_file = log_path / "session_export.log"

    # ── Root logger ──────────────────────────────────────────────────
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers (important for repeated calls in tests)
    root_logger.handlers.clear()

    # ── Formatter ────────────────────────────────────────────────────
    # Format: 2024-01-15 14:23:01 | INFO | digico_parser | [INFO] Parsing started
    fmt = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # ── File handler (rotating, max 5MB, keep 3 backups) ─────────────
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # ── Console handler ───────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    root_logger.info(f"[INFO] Logging initialized → {log_file}")


class GUILogHandler(logging.Handler):
    """
    A custom logging handler that forwards log records to the GUI.

    This allows the application log panel to display real-time
    log messages as the session is being parsed and exported.

    Usage (in GUI code):
        handler = GUILogHandler(signal_callback=self.on_log_message)
        logging.getLogger().addHandler(handler)

    The callback receives (level: str, message: str).
    """

    def __init__(self, signal_callback):
        """
        Parameters
        ----------
        signal_callback : callable
            A function that accepts (level: str, message: str).
            In PySide6 this is typically a Qt signal.
        """
        super().__init__()
        self.signal_callback = signal_callback

    def emit(self, record: logging.LogRecord) -> None:
        """
        Called by the logging framework for each log record.
        Forwards the record to the GUI callback.
        """
        try:
            level   = record.levelname
            message = self.format(record)
            self.signal_callback(level, message)
        except Exception:
            self.handleError(record)
