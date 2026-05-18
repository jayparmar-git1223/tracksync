"""
settings.py — Application Settings & Preferences

Manages persistent application settings stored in a JSON config file.

Settings are loaded on startup and saved whenever changed.
The config file is stored in:
    - macOS:    ~/Library/Application Support/LiveConsoleDawMirror/settings.json
    - Windows:  %APPDATA%/LiveConsoleDawMirror/settings.json
    - Linux:    ~/.config/LiveConsoleDawMirror/settings.json

Usage:
    from settings import Settings
    s = Settings()

    # Read a setting
    s.get("default_daw")            # → "REAPER"
    s.get("last_output_dir")        # → "/home/user/sessions"

    # Write a setting
    s.set("default_daw", "Cubase")

    # Access as attributes
    s.theme                         # → "dark"
    s.auto_detect_stereo_pairs      # → True
"""

import json
import logging
import platform
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

APP_NAME = "LiveConsoleDawMirror"


def get_config_dir() -> Path:
    """
    Returns the platform-appropriate config directory for the app.

    Returns
    -------
    Path
        The config directory path. Created if it doesn't exist.
    """
    system = platform.system()

    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    elif system == "Windows":
        import os
        base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    else:
        # Linux and others — follow XDG Base Directory spec
        base = Path.home() / ".config" / APP_NAME

    base.mkdir(parents=True, exist_ok=True)
    return base


# ─────────────────────────────────────────────────────────────────────
# Default settings
# ─────────────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {

    # ── Export settings ──────────────────────────────────────────────
    "default_daw":               "REAPER",
    "last_output_dir":           "output",
    "last_input_dir":            "",
    "auto_open_after_export":    False,
    "overwrite_without_confirm": False,

    # ── Parser settings ──────────────────────────────────────────────
    "auto_detect_stereo_pairs":  True,
    "auto_classify_groups":      True,
    "default_console":           "DiGiCo",
    "default_sample_rate":       48000,
    "default_bit_depth":         24,

    # ── Preset settings ──────────────────────────────────────────────
    "default_preset":            "live_show",
    "auto_apply_preset":         False,
    "custom_presets_dir":        "",

    # ── GUI settings ─────────────────────────────────────────────────
    "theme":                     "dark",
    "font_size":                 12,
    "show_channel_numbers":      True,
    "show_group_colors":         True,
    "show_stereo_pairs":         True,
    "window_width":              1440,
    "window_height":             860,
    "window_maximized":          False,
    "remember_window_size":      True,

    # ── Logging settings ─────────────────────────────────────────────
    "log_level":                 "INFO",
    "log_to_file":               True,
    "log_dir":                   "logs",
    "max_log_lines":             500,

    # ── Advanced ─────────────────────────────────────────────────────
    "reaper_version":            "6.0",
    "cubase_version":            "12",
    "nuendo_version":            "12",
    "include_timestamps":        True,
    "session_json_pretty":       True,

}


class Settings:
    """
    Application settings manager.

    Loads settings from a JSON config file on startup.
    Saves settings to disk whenever they are changed.

    All settings have sensible defaults (see DEFAULTS above).
    Unknown settings are preserved in the config file so future
    versions can still read them.

    Example usage:
        s = Settings()
        print(s.get("default_daw"))     # "REAPER"
        s.set("default_daw", "Cubase")
        print(s.default_daw)            # "Cubase"
    """

    def __init__(self, config_dir: Optional[str] = None):
        """
        Parameters
        ----------
        config_dir : str, optional
            Custom directory for the config file.
            Defaults to the platform config directory.
        """
        self._config_dir  = Path(config_dir) if config_dir else get_config_dir()
        self._config_file = self._config_dir / "settings.json"
        self._data: dict[str, Any] = dict(DEFAULTS)

        self._load()
        logger.info(f"[INFO] Settings: Loaded from '{self._config_file}'")

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value by key.

        Parameters
        ----------
        key : str
            The setting key.
        default : Any, optional
            Fallback value if the key is not found.
            If not provided, uses the built-in default.

        Returns
        -------
        Any
            The setting value.
        """
        if default is None:
            default = DEFAULTS.get(key)
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Set a setting value and immediately save to disk.

        Parameters
        ----------
        key : str
            The setting key.
        value : Any
            The new value. Must be JSON-serializable.
        """
        old_value = self._data.get(key)
        self._data[key] = value

        if old_value != value:
            logger.debug(f"[DEBUG] Settings: '{key}': {old_value!r} → {value!r}")

        self._save()

    def reset_to_defaults(self) -> None:
        """Reset all settings to their built-in defaults."""
        self._data = dict(DEFAULTS)
        self._save()
        logger.info("[INFO] Settings: Reset to defaults")

    def reset_key(self, key: str) -> None:
        """Reset a single setting to its default value."""
        if key in DEFAULTS:
            self._data[key] = DEFAULTS[key]
            self._save()

    def all(self) -> dict[str, Any]:
        """Returns a copy of all current settings."""
        return dict(self._data)

    def export_json(self, path: str) -> None:
        """Export all settings to a JSON file (for backup/sharing)."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        logger.info(f"[INFO] Settings: Exported to '{path}'")

    def import_json(self, path: str) -> None:
        """Import settings from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            imported = json.load(f)
        self._data.update(imported)
        self._save()
        logger.info(f"[INFO] Settings: Imported from '{path}'")

    # ──────────────────────────────────────────────────────────────────
    # Attribute access (convenience)
    # ──────────────────────────────────────────────────────────────────

    def __getattr__(self, key: str) -> Any:
        """Allow settings to be accessed as attributes: s.default_daw"""
        if key.startswith("_"):
            raise AttributeError(key)
        if key in self._data:
            return self._data[key]
        if key in DEFAULTS:
            return DEFAULTS[key]
        raise AttributeError(f"Settings has no attribute '{key}'")

    def __setattr__(self, key: str, value: Any) -> None:
        """Allow settings to be set as attributes: s.default_daw = 'Cubase'"""
        if key.startswith("_"):
            super().__setattr__(key, value)
        elif key in DEFAULTS or key in self.__dict__.get("_data", {}):
            self._data[key] = value
            self._save()
        else:
            super().__setattr__(key, value)

    # ──────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load settings from the config file, merging with defaults."""
        if not self._config_file.exists():
            # First run — write defaults to disk
            self._save()
            return

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                saved = json.load(f)

            # Merge: defaults are the base, saved values override
            merged = dict(DEFAULTS)
            merged.update(saved)
            self._data = merged

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"[WARNING] Settings: Could not load config from "
                f"'{self._config_file}': {e}. Using defaults."
            )
            self._data = dict(DEFAULTS)

    def _save(self) -> None:
        """Write current settings to the config file."""
        try:
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"[ERROR] Settings: Could not save config: {e}")

    def __repr__(self) -> str:
        return f"<Settings config='{self._config_file}' keys={len(self._data)}>"
