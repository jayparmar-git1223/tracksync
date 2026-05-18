"""
cli.py — Command-Line Interface (Headless Mode)

Run Live Console → DAW Mirror without the GUI.
Useful for batch processing, automation scripts, and CI/CD pipelines.

Usage examples:
    # Parse and export to REAPER
    python cli.py input.rtf --daw reaper --out output/show.rpp

    # Parse and save as Universal JSON (for re-export later)
    python cli.py input.rtf --save-json output/show.json

    # Load JSON and export to Cubase
    python cli.py output/show.json --daw cubase --out output/show

    # Batch process a folder
    python cli.py /shows/ --batch --daw reaper --out /exports/

    # Show session info only (no export)
    python cli.py input.rtf --info

    # Export to all DAWs at once
    python cli.py input.rtf --daw all --out output/show
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add src/ to path
SRC_DIR = os.path.join(os.path.dirname(__file__), "src")
sys.path.insert(0, SRC_DIR)

from logger import setup_logging
setup_logging(log_dir="logs")

logger = logging.getLogger("cli")


# ─────────────────────────────────────────────────────────────────────
# Console detection
# ─────────────────────────────────────────────────────────────────────

def detect_parser(file_path: str, console_hint: str = ""):
    """
    Detect the correct parser based on file type, content, and optional console hint.

    Parameters
    ----------
    file_path : str
        Path to the session file.
    console_hint : str, optional
        Console brand hint e.g. "digico", "yamaha", "allen_heath"

    Returns a parser instance ready to call .parse() on.
    """
    suffix = Path(file_path).suffix.lower()
    hint = console_hint.lower().replace(" ", "_").replace("&", "").replace("-", "_")

    # ── Explicit console hint overrides auto-detection ──
    if "yamaha" in hint or "cl" in hint or "ql" in hint:
        from parser.yamaha_parser import YamahaParser
        return YamahaParser()

    if "allen" in hint or "heath" in hint or "dlive" in hint or "sq" in hint or "avantis" in hint:
        from parser.allen_heath_parser import AllenHeathParser
        return AllenHeathParser()

    # ── Auto-detect from file extension ──────────────────────────────
    if suffix in (".rivagepm", ".RIVAGEPM".lower()) or suffix == ".rivagepm":
        from parser.rivage_parser import RIVAGEParser
        return RIVAGEParser()

    if suffix == ".rtf":
        # DiGiCo uses RTF; sniff content to be sure
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")[:500].lower()
            if "yamaha" in content:
                from parser.yamaha_parser import YamahaParser
                return YamahaParser()
            if "allen" in content or "dlive" in content:
                from parser.allen_heath_parser import AllenHeathParser
                return AllenHeathParser()
        except Exception:
            pass
        from parser.digico_parser import DiGiCoParser
        return DiGiCoParser()

    elif suffix in (".cel", ".scene"):
        # CEL = Yamaha; .scene = Allen & Heath dLive
        if suffix == ".cel":
            from parser.yamaha_parser import YamahaParser
            return YamahaParser()
        else:
            from parser.allen_heath_parser import AllenHeathParser
            return AllenHeathParser()

    elif suffix in (".csv", ".txt", ".xml"):
        # Sniff the content to determine console
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")[:400].lower()
            if any(m in content for m in ["cl1", "cl3", "cl5", "ql1", "ql5", "yamaha"]):
                from parser.yamaha_parser import YamahaParser
                return YamahaParser()
            if any(m in content for m in ["dlive", "sq-5", "sq-6", "sq-7", "avantis", "allen"]):
                from parser.allen_heath_parser import AllenHeathParser
                return AllenHeathParser()
        except Exception:
            pass
        # Default to DiGiCo for unknown text formats
        from parser.digico_parser import DiGiCoParser
        return DiGiCoParser()

    elif suffix == ".json":
        return None  # JSON sessions are loaded directly via Session.load_json

    else:
        raise ValueError(
            f"Unsupported file type: '{suffix}'\n"
            f"Supported formats:\n"
            f"  .rtf   — DiGiCo session reports\n"
            f"  .cel   — Yamaha CL/QL exports\n"
            f"  .scene — Allen & Heath dLive scenes\n"
            f"  .csv   — Any console CSV export\n"
            f"  .json  — Universal Session JSON"
        )


def detect_exporter(daw: str):
    """
    Return the exporter instance for the given DAW name.

    Parameters
    ----------
    daw : str
        One of: reaper, cubase, nuendo, protools, ableton, logic
    """
    daw_lower = daw.lower().replace(" ", "").replace("-", "")

    if daw_lower == "reaper":
        from exporters.reaper.reaper_exporter import REAPERExporter
        return REAPERExporter()
    elif daw_lower in ("cubase", "cubase12", "cubase13"):
        from exporters.cubase.cubase_exporter import CubaseExporter
        return CubaseExporter()
    elif daw_lower in ("nuendo", "nuendo12", "nuendo13"):
        from exporters.nuendo.nuendo_exporter import NuendoExporter
        return NuendoExporter()
    elif daw_lower in ("protools", "pt", "pro_tools"):
        from exporters.protools.protools_exporter import ProToolsExporter
        return ProToolsExporter()
    elif daw_lower in ("ableton", "live", "abletonlive"):
        from exporters.ableton.ableton_exporter import AbletonExporter
        return AbletonExporter()
    elif daw_lower in ("logic", "logicpro", "logicprox"):
        from exporters.logic.logic_exporter import LogicExporter
        return LogicExporter()
    else:
        raise ValueError(
            f"Unknown DAW: '{daw}'\n"
            f"Supported: reaper, cubase, nuendo, protools, ableton, logic"
        )


# ─────────────────────────────────────────────────────────────────────
# Main commands
# ─────────────────────────────────────────────────────────────────────

def cmd_info(session, args):
    """Print session information to stdout."""
    from models.track import GROUP_COLORS

    print()
    print("=" * 60)
    print(f"  LIVE CONSOLE → DAW MIRROR")
    print("=" * 60)
    print(f"  Session:     {session.session_name}")
    print(f"  Console:     {session.console}")
    print(f"  Sample Rate: {session.sample_rate} Hz")
    print(f"  Bit Depth:   {session.bit_depth}-bit")
    print(f"  Tracks:      {session.get_track_count()}")
    print(f"  Groups:      {', '.join(session.get_unique_groups())}")
    print(f"  Source:      {session.source_file}")
    print()
    print("─" * 60)
    print(f"  {'CH':>3}  {'NAME':<24}  {'TYPE':<7}  {'GROUP':<10}  STEREO")
    print("─" * 60)

    for t in session.tracks:
        stereo = f"↔ ch{t.stereo_pair}" if t.stereo_pair else ""
        print(f"  {t.channel:>3}  {t.name:<24}  {t.track_type:<7}  {t.group:<10}  {stereo}")

    if session.buses:
        print()
        print("─" * 60)
        print("  BUSES")
        print("─" * 60)
        for b in session.buses:
            ch_list = ", ".join(str(c) for c in b.channels[:8])
            if len(b.channels) > 8:
                ch_list += f" +{len(b.channels)-8} more"
            print(f"  {b.name:<25}  ({b.bus_type})  CH: {ch_list}")

    print()


def cmd_export(session, daw_name: str, output_path: str):
    """Export a session to a DAW format."""
    exporter = detect_exporter(daw_name)
    out = exporter.export(session, output_path)
    print(f"[SUCCESS] {daw_name} → {out}")
    return out


def cmd_export_all(session, base_output: str):
    """Export to all supported DAWs."""
    base = Path(base_output)
    results = []

    for daw in ["reaper", "cubase", "nuendo"]:
        out_path = base.with_name(f"{base.name}_{daw}")
        out = cmd_export(session, daw, str(out_path))
        results.append(out)

    return results


def cmd_batch(input_dir: str, daw: str, output_dir: str):
    """
    Batch-process all session files in a directory.

    Finds all .rtf and .json files in input_dir and exports each one.
    """
    input_path  = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    session_files = list(input_path.glob("*.rtf")) + list(input_path.glob("*.json"))

    if not session_files:
        print(f"[WARNING] No session files found in: {input_dir}")
        return

    print(f"[INFO] Found {len(session_files)} session files in {input_dir}")
    print()

    success = 0
    errors  = 0

    for file_path in sorted(session_files):
        try:
            print(f"  Processing: {file_path.name}")
            session = load_session(str(file_path))

            out_name = file_path.stem
            out_path = output_path / out_name

            if daw.lower() == "all":
                cmd_export_all(session, str(out_path))
            else:
                cmd_export(session, daw, str(out_path))

            success += 1

        except Exception as e:
            print(f"  [ERROR] {file_path.name}: {e}")
            errors += 1

    print()
    print(f"[DONE] {success} exported, {errors} failed")


# ─────────────────────────────────────────────────────────────────────
# Session loading
# ─────────────────────────────────────────────────────────────────────

def load_session(file_path: str):
    """Load a session file (RTF or JSON) and return a Session object."""
    from pathlib import Path
    suffix = Path(file_path).suffix.lower()

    if suffix == ".json":
        from models.session import Session
        return Session.load_json(file_path)
    else:
        parser = detect_parser(file_path)
        return parser.parse(file_path)


# ─────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="liveconsole",
        description="Live Console → DAW Mirror — headless CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    p.add_argument(
        "input",
        nargs="?",
        help="Console session file (.rtf/.cel/.scene/.csv/.json) or directory for --batch",
    )

    p.add_argument(
        "--daw",
        choices=["reaper", "cubase", "nuendo", "protools", "ableton", "logic", "all"],
        default=None,
        help="Target DAW for export",
    )

    p.add_argument(
        "--console",
        default="",
        help="Console brand hint: digico, yamaha, allen_heath (auto-detected if not set)",
    )

    p.add_argument(
        "--preset",
        default=None,
        help="Apply a routing preset: live_show, recording, broadcast, festival, theatre, playback",
    )

    p.add_argument(
        "--list-presets",
        action="store_true",
        help="List all available routing presets",
    )

    p.add_argument(
        "--diff",
        default=None,
        metavar="SESSION_B",
        help="Compare input session against SESSION_B and print diff report",
    )

    p.add_argument(
        "--out",
        default=None,
        help="Output path for the exported session file (without extension)",
    )

    p.add_argument(
        "--save-json",
        default=None,
        metavar="PATH",
        help="Save the parsed session as a Universal Session JSON file",
    )

    p.add_argument(
        "--info",
        action="store_true",
        help="Print session info to stdout without exporting",
    )

    p.add_argument(
        "--batch",
        action="store_true",
        help="Batch-process all session files in the input directory",
    )

    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )

    return p


def main():
    p = build_arg_parser()
    args = p.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── List presets ─────────────────────────────────────────────────
    if args.list_presets:
        from routing_presets import PresetManager
        pm = PresetManager()
        print("\nAvailable routing presets:")
        print("─" * 56)
        for preset in pm.list_presets():
            slug = pm._slugify(preset.name)
            tags = f"  [{', '.join(preset.tags)}]" if preset.tags else ""
            print(f"  {slug:<20}  {preset.description[:45]}{tags}")
        print()
        return

    if not args.input:
        p.print_help()
        return

    # ── Session diff ─────────────────────────────────────────────────
    if args.diff:
        from session_diff import SessionDiff
        print(f"[INFO] Loading session A: {args.input}")
        session_a = load_session(args.input)
        print(f"[INFO] Loading session B: {args.diff}")
        session_b = load_session(args.diff)
        diff = SessionDiff(
            session_a, session_b,
            label_a=Path(args.input).stem,
            label_b=Path(args.diff).stem,
        )
        print(diff.report())
        return

    # ── Batch mode ───────────────────────────────────────────────────
    if args.batch:
        if not args.daw:
            p.error("--daw is required in batch mode")
        out_dir = args.out or "output"
        cmd_batch(args.input, args.daw, out_dir)
        return

    # ── Single file mode ─────────────────────────────────────────────
    if not Path(args.input).exists():
        print(f"[ERROR] File not found: {args.input}")
        sys.exit(1)

    try:
        print(f"[INFO] Loading: {args.input}")
        session = load_session(args.input, console_hint=getattr(args, "console", ""))

    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # Apply routing preset if specified
    if args.preset:
        from routing_presets import PresetManager
        pm = PresetManager()
        session = pm.apply_preset(session, args.preset)
        print(f"[INFO] Applied preset: {args.preset}")

    # Show info
    if args.info or not args.daw:
        cmd_info(session, args)

    # Save JSON
    if args.save_json:
        session.save_json(args.save_json)
        print(f"[SUCCESS] JSON saved: {args.save_json}")

    # Export to DAW
    if args.daw:
        out_base = args.out or f"output/{Path(args.input).stem}"

        try:
            if args.daw == "all":
                cmd_export_all(session, out_base)
            else:
                cmd_export(session, args.daw, out_base)
        except Exception as e:
            print(f"[ERROR] Export failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
