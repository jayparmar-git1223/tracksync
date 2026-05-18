#!/usr/bin/env python3
"""
build.py — Build Script for Live Console → DAW Mirror

Cross-platform build script. Run this to produce a distribution-ready
standalone executable for the current platform.

Usage:
    python build.py                    # Build for current platform
    python build.py --clean            # Clean then build
    python build.py --check            # Verify environment only
    python build.py --version 1.2.0   # Set version and build

Output:
    dist/LiveConsoleDawMirror/         # Folder distribution
    dist/LiveConsoleDawMirror.app/     # macOS App Bundle (macOS only)
    dist/LiveConsoleDawMirror.zip      # Zipped distribution archive
"""

import sys
import os
import shutil
import subprocess
import argparse
import zipfile
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────
# Build configuration
# ─────────────────────────────────────────────────────────────────────

APP_NAME    = "LiveConsoleDawMirror"
APP_VERSION = "1.0.0"
APP_DISPLAY = "Live Console DAW Mirror"
ENTRY_POINT = "app.py"
SPEC_FILE   = "LiveConsoleDawMirror.spec"

PROJECT_ROOT = Path(__file__).parent
DIST_DIR     = PROJECT_ROOT / "dist"
BUILD_DIR    = PROJECT_ROOT / "build"
SRC_DIR      = PROJECT_ROOT / "src"


def check_environment() -> bool:
    """Verify all build prerequisites are met."""
    print("\n  Checking build environment...")
    ok = True

    # Python version
    if sys.version_info < (3, 12):
        print(f"  ✗ Python 3.12+ required (found {sys.version})")
        ok = False
    else:
        print(f"  ✓ Python {sys.version.split()[0]}")

    # PyInstaller
    try:
        import PyInstaller
        print(f"  ✓ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  ✗ PyInstaller not found — run: pip install pyinstaller")
        ok = False

    # PySide6
    try:
        import PySide6
        print(f"  ✓ PySide6 {PySide6.__version__}")
    except ImportError:
        print("  ✗ PySide6 not found — run: pip install PySide6")
        ok = False

    # Check src/ structure
    required_modules = [
        "src/models/session.py",
        "src/parser/digico_parser.py",
        "src/exporters/reaper/reaper_exporter.py",
        "src/gui/main_window.py",
        "app.py",
    ]
    for mod in required_modules:
        p = PROJECT_ROOT / mod
        if p.exists():
            print(f"  ✓ {mod}")
        else:
            print(f"  ✗ Missing: {mod}")
            ok = False

    return ok


def clean_build():
    """Remove previous build artifacts."""
    print("\n  Cleaning previous build artifacts...")
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed: {d}")
    # Remove .pyc files
    for pyc in PROJECT_ROOT.rglob("*.pyc"):
        pyc.unlink()
    for pycache in PROJECT_ROOT.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)
    print("  Clean complete")


def run_tests() -> bool:
    """Run the test suite before building."""
    print("\n  Running test suite...")
    result = subprocess.run(
        [sys.executable, "tests/test_suite.py"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode == 0:
        print("  ✓ All tests passed")
        return True
    else:
        print("  ✗ Tests failed:")
        print(result.stdout[-500:])
        return False


def build_executable():
    """Run PyInstaller to build the executable."""
    print(f"\n  Building {APP_DISPLAY}...")
    print(f"  Platform: {sys.platform}")
    print(f"  Version:  {APP_VERSION}")

    # Use spec file if available, otherwise use args
    spec = PROJECT_ROOT / SPEC_FILE
    if spec.exists():
        cmd = [
            sys.executable, "-m", "PyInstaller",
            str(spec),
            "--noconfirm",
            "--clean",
        ]
    else:
        cmd = [
            sys.executable, "-m", "PyInstaller",
            ENTRY_POINT,
            "--name", APP_NAME,
            "--windowed",           # No console
            "--noconfirm",
            "--clean",
            "--paths", str(SRC_DIR),
            "--add-data", f"templates{os.pathsep}templates",
            "--add-data", f"assets{os.pathsep}assets",
        ]

    print(f"  Running: {' '.join(cmd[:4])} ...")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode != 0:
        print("  ✗ PyInstaller build failed")
        return False

    print("  ✓ Build complete")
    return True


def create_archive():
    """Create a zip archive of the distribution."""
    dist_app = DIST_DIR / APP_NAME
    if not dist_app.exists():
        print("  Warning: No dist folder found to archive")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    platform_tag = {
        "darwin":  "macos",
        "win32":   "windows",
        "linux":   "linux",
    }.get(sys.platform, sys.platform)

    archive_name = f"{APP_NAME}_v{APP_VERSION}_{platform_tag}_{timestamp}.zip"
    archive_path = DIST_DIR / archive_name

    print(f"\n  Creating archive: {archive_name}")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in dist_app.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(DIST_DIR)
                zf.write(file_path, arcname)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"  ✓ Archive: {archive_path} ({size_mb:.1f} MB)")


def print_summary():
    """Print a build summary."""
    print()
    print("=" * 56)
    print(f"  BUILD COMPLETE — {APP_DISPLAY}")
    print("=" * 56)
    print()

    dist_app = DIST_DIR / APP_NAME
    if dist_app.exists():
        # Count files
        files = list(dist_app.rglob("*"))
        size_mb = sum(f.stat().st_size for f in files if f.is_file()) / (1024 * 1024)
        print(f"  Output:  {dist_app}")
        print(f"  Files:   {len(files)}")
        print(f"  Size:    {size_mb:.1f} MB")
        print()

    print("  Run the app:")
    if sys.platform == "darwin":
        print(f"    open 'dist/Live Console DAW Mirror.app'")
        print(f"    # or: ./dist/{APP_NAME}/{APP_NAME}")
    elif sys.platform == "win32":
        print(f"    .\\dist\\{APP_NAME}\\{APP_NAME}.exe")
    else:
        print(f"    ./dist/{APP_NAME}/{APP_NAME}")
    print()
    print("  Or use the CLI:")
    print("    python cli.py --help")
    print()


def main():
    parser = argparse.ArgumentParser(
        description=f"Build script for {APP_DISPLAY}"
    )
    parser.add_argument("--clean",   action="store_true", help="Clean before building")
    parser.add_argument("--check",   action="store_true", help="Check environment only")
    parser.add_argument("--no-test", action="store_true", help="Skip test suite")
    parser.add_argument("--no-zip",  action="store_true", help="Skip archive creation")
    parser.add_argument("--version", default=APP_VERSION, help="Set version number")
    args = parser.parse_args()

    global APP_VERSION
    APP_VERSION = args.version

    print()
    print("=" * 56)
    print(f"  {APP_DISPLAY} — Build System")
    print(f"  Version: {APP_VERSION}")
    print("=" * 56)

    # Environment check
    if not check_environment():
        print("\n  ✗ Environment check failed. Fix issues above and retry.")
        if args.check:
            sys.exit(1)
        if not args.check:
            print("  Continuing anyway (some checks failed)...")

    if args.check:
        print("\n  Environment check complete.")
        return

    # Clean
    if args.clean:
        clean_build()

    # Tests
    if not args.no_test:
        if not run_tests():
            print("\n  ✗ Build aborted: tests failed.")
            print("  Use --no-test to skip (not recommended for releases).")
            sys.exit(1)

    # Build
    if not build_executable():
        print("\n  ✗ Build failed.")
        sys.exit(1)

    # Archive
    if not args.no_zip:
        create_archive()

    print_summary()


if __name__ == "__main__":
    main()
