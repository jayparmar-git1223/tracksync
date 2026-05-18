"""
registry.py — Parser & Exporter Registry

Central registry for all console parsers and DAW exporters.

Instead of hard-coding which parsers/exporters exist in every
part of the app, everything registers here. The GUI, CLI, and
any other consumer can query the registry to discover what's
available.

Usage:
    from registry import get_parser, get_exporter, list_parsers, list_exporters

    # Get a parser by file extension
    parser = get_parser(".rtf")                 # → DiGiCoParser
    parser = get_parser(".cel")                 # → YamahaParser
    parser = get_parser(".scene")               # → AllenHeathParser

    # Get a parser by console name
    parser = get_parser_by_console("DiGiCo")   # → DiGiCoParser
    parser = get_parser_by_console("Yamaha")    # → YamahaParser

    # Get an exporter
    exporter = get_exporter("REAPER")           # → REAPERExporter
    exporter = get_exporter("ableton")          # → AbletonExporter

    # List everything
    for p in list_parsers():
        print(p.console_name, p.supported_extensions)

    for e in list_exporters():
        print(e.daw_name, e.file_extension)
"""

import logging
from typing import Optional, Type
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Registration data classes
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ParserEntry:
    """Metadata about a registered parser."""
    console_name:         str               # e.g. "DiGiCo"
    console_brand:        str               # e.g. "DiGiCo" (for matching)
    supported_extensions: list[str]         # e.g. [".rtf"]
    parser_class:         type              # The parser class itself
    description:          str = ""
    version:              str = "1.0"
    status:               str = "stable"    # "stable", "beta", "experimental"
    keywords:             list[str] = None  # Content keywords for auto-detection

    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


@dataclass
class ExporterEntry:
    """Metadata about a registered exporter."""
    daw_name:       str       # e.g. "REAPER"
    file_extension: str       # e.g. ".rpp"
    exporter_class: type      # The exporter class itself
    description:    str = ""
    version:        str = "1.0"
    status:         str = "stable"
    aliases:        list[str] = None  # Alternative names e.g. ["pt", "protools"]

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []


# ─────────────────────────────────────────────────────────────────────
# Registry tables
# ─────────────────────────────────────────────────────────────────────

# Populated by _register_all() below
_PARSERS:   list[ParserEntry]   = []
_EXPORTERS: list[ExporterEntry] = []
_initialized = False


def _register_all():
    """Register all built-in parsers and exporters."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    # ── Parsers ──────────────────────────────────────────────────────
    try:
        from parser.digico_parser import DiGiCoParser
        _PARSERS.append(ParserEntry(
            console_name=         "DiGiCo SD Range",
            console_brand=        "DiGiCo",
            supported_extensions= [".rtf"],
            parser_class=         DiGiCoParser,
            description=          "DiGiCo SD5/SD7/SD10/SD11/SD12 session report parser. "
                                  "Reads .rtf export files from DiGiCo consoles.",
            status=               "stable",
            keywords=             ["digico", "sd5", "sd7", "sd10", "sd11", "sd12", "sd-rack"],
        ))
        logger.debug("[DEBUG] Registry: Registered DiGiCoParser")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register DiGiCoParser: {e}")

    try:
        from parser.yamaha_parser import YamahaParser
        _PARSERS.append(ParserEntry(
            console_name=         "Yamaha CL/QL Series",
            console_brand=        "Yamaha",
            supported_extensions= [".cel", ".csv", ".xml", ".txt"],
            parser_class=         YamahaParser,
            description=          "Yamaha CL1/CL3/CL5/QL1/QL5 session export parser. "
                                  "Supports CEL, CSV, and text exports.",
            status=               "stable",
            keywords=             ["yamaha", "cl1", "cl3", "cl5", "ql1", "ql5", "m7cl", "ls9"],
        ))
        logger.debug("[DEBUG] Registry: Registered YamahaParser")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register YamahaParser: {e}")

    try:
        from parser.allen_heath_parser import AllenHeathParser
        _PARSERS.append(ParserEntry(
            console_name=         "Allen & Heath dLive/SQ/Avantis",
            console_brand=        "Allen & Heath",
            supported_extensions= [".scene", ".csv", ".xml", ".txt"],
            parser_class=         AllenHeathParser,
            description=          "Allen & Heath dLive, SQ series, Avantis, and Qu series parser. "
                                  "Supports .scene XML and CSV exports.",
            status=               "stable",
            keywords=             ["allen", "heath", "dlive", "sq-5", "sq-6", "sq-7",
                                   "avantis", "qu-16", "qu-24", "qu-32"],
        ))
        logger.debug("[DEBUG] Registry: Registered AllenHeathParser")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register AllenHeathParser: {e}")

    try:
        from parser.rivage_parser import RIVAGEParser
        _PARSERS.append(ParserEntry(
            console_name=         "Yamaha RIVAGE PM",
            console_brand=        "Yamaha",
            supported_extensions= [".RIVAGEPM", ".rivagepm"],
            parser_class=         RIVAGEParser,
            description=          "Yamaha RIVAGE PM10/PM7/PM5/PM3 project file parser. "
                                  "Reads binary MBDF project files (.RIVAGEPM) by "
                                  "decompressing and extracting channel name arrays.",
            status=               "stable",
            keywords=             ["rivage", "pm10", "pm7", "pm5", "pm3", "yamaha rivage"],
        ))
        logger.debug("[DEBUG] Registry: Registered RIVAGEParser")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register RIVAGEParser: {e}")

    try:
        from parser.avid_parser import AvidS6LParser
        _PARSERS.append(ParserEntry(
            console_name=         "Avid S6L",
            console_brand=        "Avid",
            supported_extensions= [".csv", ".txt", ".xml"],
            parser_class=         AvidS6LParser,
            description=          "Avid S6L/VENUE console session export parser. "
                                  "Supports CSV and text exports from VENUE software.",
            status=               "beta",
            keywords=             ["avid", "s6l", "venue", "s3l"],
        ))
        logger.debug("[DEBUG] Registry: Registered AvidS6LParser")
    except ImportError:
        pass  # Optional parser, not yet fully implemented

    # ── Exporters ────────────────────────────────────────────────────
    try:
        from exporters.reaper.reaper_exporter import REAPERExporter
        _EXPORTERS.append(ExporterEntry(
            daw_name=       "REAPER",
            file_extension= ".rpp",
            exporter_class= REAPERExporter,
            description=    "Generates REAPER .rpp project files. Full folder/group "
                            "structure, colors, and routing preserved.",
            status=         "stable",
            aliases=        ["reaper"],
        ))
        logger.debug("[DEBUG] Registry: Registered REAPERExporter")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register REAPERExporter: {e}")

    try:
        from exporters.cubase.cubase_exporter import CubaseExporter
        _EXPORTERS.append(ExporterEntry(
            daw_name=       "Cubase",
            file_extension= ".xml",
            exporter_class= CubaseExporter,
            description=    "Generates Cubase Track Archive XML for import via "
                            "File → Import → Track Archive.",
            status=         "stable",
            aliases=        ["cubase", "cubase12", "cubase13", "cubase14"],
        ))
        logger.debug("[DEBUG] Registry: Registered CubaseExporter")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register CubaseExporter: {e}")

    try:
        from exporters.nuendo.nuendo_exporter import NuendoExporter
        _EXPORTERS.append(ExporterEntry(
            daw_name=       "Nuendo",
            file_extension= ".xml",
            exporter_class= NuendoExporter,
            description=    "Generates Nuendo Track Archive XML. Same format as Cubase, "
                            "labeled for Nuendo engineers.",
            status=         "stable",
            aliases=        ["nuendo", "nuendo12", "nuendo13"],
        ))
        logger.debug("[DEBUG] Registry: Registered NuendoExporter")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register NuendoExporter: {e}")

    try:
        from exporters.protools.protools_exporter import ProToolsExporter
        _EXPORTERS.append(ExporterEntry(
            daw_name=       "Pro Tools",
            file_extension= ".txt",
            exporter_class= ProToolsExporter,
            description=    "Generates Pro Tools Session Info Text and AAF metadata "
                            "for import via File → Import → Session Data.",
            status=         "stable",
            aliases=        ["protools", "pro_tools", "pt", "protools2023"],
        ))
        logger.debug("[DEBUG] Registry: Registered ProToolsExporter")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register ProToolsExporter: {e}")

    try:
        from exporters.ableton.ableton_exporter import AbletonExporter
        _EXPORTERS.append(ExporterEntry(
            daw_name=       "Ableton Live",
            file_extension= ".als",
            exporter_class= AbletonExporter,
            description=    "Generates Ableton Live Set (.als) files with audio tracks, "
                            "return tracks, and master track.",
            status=         "stable",
            aliases=        ["ableton", "live", "abletonlive", "ableton11", "ableton12"],
        ))
        logger.debug("[DEBUG] Registry: Registered AbletonExporter")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register AbletonExporter: {e}")

    try:
        from exporters.logic.logic_exporter import LogicExporter
        _EXPORTERS.append(ExporterEntry(
            daw_name=       "Logic Pro",
            file_extension= ".txt",
            exporter_class= LogicExporter,
            description=    "Generates Logic Pro channel strip XML and Scripter JS "
                            "for track auto-creation on macOS.",
            status=         "stable",
            aliases=        ["logic", "logicpro", "logicprox", "logic10", "logic11"],
        ))
        logger.debug("[DEBUG] Registry: Registered LogicExporter")
    except ImportError as e:
        logger.warning(f"[WARNING] Registry: Could not register LogicExporter: {e}")

    logger.info(
        f"[INFO] Registry: Loaded {len(_PARSERS)} parsers, "
        f"{len(_EXPORTERS)} exporters"
    )


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def list_parsers() -> list[ParserEntry]:
    """Return all registered parser entries."""
    _register_all()
    return list(_PARSERS)


def list_exporters() -> list[ExporterEntry]:
    """Return all registered exporter entries."""
    _register_all()
    return list(_EXPORTERS)


def get_parser(file_extension: str) -> Optional[object]:
    """
    Get an instantiated parser for the given file extension.

    Parameters
    ----------
    file_extension : str
        File extension including the dot. e.g. ".rtf", ".cel"

    Returns
    -------
    BaseParser instance or None
    """
    _register_all()
    ext = file_extension.lower()
    if not ext.startswith("."):
        ext = "." + ext

    for entry in _PARSERS:
        if ext in entry.supported_extensions:
            return entry.parser_class()

    return None


def get_parser_by_console(console_name: str) -> Optional[object]:
    """
    Get an instantiated parser by console brand name.

    Parameters
    ----------
    console_name : str
        Console brand e.g. "DiGiCo", "Yamaha", "Allen & Heath"

    Returns
    -------
    BaseParser instance or None
    """
    _register_all()
    name_lower = console_name.lower()

    for entry in _PARSERS:
        if (entry.console_brand.lower() in name_lower or
                name_lower in entry.console_brand.lower()):
            return entry.parser_class()

        for keyword in entry.keywords:
            if keyword in name_lower:
                return entry.parser_class()

    return None


def detect_parser_for_file(file_path: str) -> Optional[object]:
    """
    Auto-detect and return the best parser for a given file.

    Checks file extension first, then sniffs file content for
    console brand keywords.

    Parameters
    ----------
    file_path : str
        Full path to the console session file.

    Returns
    -------
    BaseParser instance or None
    """
    import re
    from pathlib import Path

    _register_all()
    path = Path(file_path)
    ext  = path.suffix.lower()

    # Try extension match first
    ext_matches = [e for e in _PARSERS if ext in e.supported_extensions]

    if len(ext_matches) == 1:
        return ext_matches[0].parser_class()

    # Multiple parsers support this extension — sniff content
    if ext_matches or ext in (".csv", ".txt", ".xml"):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")[:600].lower()

            for entry in _PARSERS:
                for keyword in entry.keywords:
                    if re.search(r'\b' + re.escape(keyword) + r'\b', content):
                        logger.info(
                            f"[INFO] Registry: Auto-detected {entry.console_name} "
                            f"from content keyword '{keyword}'"
                        )
                        return entry.parser_class()
        except Exception:
            pass

        # Fall back to first extension match
        if ext_matches:
            return ext_matches[0].parser_class()

    return None


def get_exporter(daw_name: str) -> Optional[object]:
    """
    Get an instantiated exporter by DAW name or alias.

    Parameters
    ----------
    daw_name : str
        DAW name or alias. Case-insensitive.
        e.g. "REAPER", "reaper", "pro tools", "pt", "ableton"

    Returns
    -------
    BaseExporter instance or None
    """
    _register_all()
    name_lower = daw_name.lower().replace(" ", "").replace("-", "").replace("_", "")

    for entry in _EXPORTERS:
        # Check canonical name
        if entry.daw_name.lower().replace(" ", "") == name_lower:
            return entry.exporter_class()
        # Check aliases
        for alias in entry.aliases:
            if alias.lower().replace(" ", "").replace("-", "") == name_lower:
                return entry.exporter_class()

    return None


def get_all_exporters() -> list:
    """Return instantiated instances of all registered exporters."""
    _register_all()
    return [entry.exporter_class() for entry in _EXPORTERS]


def print_registry():
    """Print a formatted registry summary to stdout."""
    _register_all()
    print()
    print("=" * 64)
    print("  LIVE CONSOLE → DAW MIRROR — Component Registry")
    print("=" * 64)
    print()
    print("  PARSERS (Console Input)")
    print("  " + "─" * 50)
    for p in _PARSERS:
        exts = ", ".join(p.supported_extensions)
        status = f"[{p.status}]"
        print(f"  {p.console_name:<30}  {exts:<20}  {status}")

    print()
    print("  EXPORTERS (DAW Output)")
    print("  " + "─" * 50)
    for e in _EXPORTERS:
        status = f"[{e.status}]"
        print(f"  {e.daw_name:<30}  {e.file_extension:<10}  {status}")

    print()
    print(f"  Total: {len(_PARSERS)} parsers, {len(_EXPORTERS)} exporters")
    print("=" * 64)
    print()
