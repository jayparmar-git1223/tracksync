# Live Console → DAW Mirror

**Professional live console session translation engine.**

Automatically mirrors live console sessions into DAW project files.
Preserves track order, names, groups, routing, and stereo pairings.

---

## Supported Consoles (Input)

| Console | Format | Status |
|---------|--------|--------|
| DiGiCo SD Range | `.rtf` Session Reports | ✅ v1.0 |
| Yamaha CL/QL | — | 🔄 Planned |
| Allen & Heath | — | 🔄 Planned |
| Avid S6L | — | 🔄 Planned |

## Supported DAWs (Output)

| DAW | Format | Status |
|-----|--------|--------|
| REAPER | `.rpp` | ✅ v1.0 |
| Cubase | Track Archive `.xml` | ✅ v1.0 |
| Nuendo | Track Archive `.xml` | ✅ v1.0 |
| Pro Tools | `.ptx` | 🔄 Planned |
| Logic Pro | `.logicx` | 🔄 Planned |
| Ableton Live | `.als` | 🔄 Planned |

---

## Installation

### Requirements

- Python 3.12+
- PySide6
- striprtf

### Setup

```bash
# Clone the repo
git clone https://github.com/yourname/live-console-daw-mirror.git
cd live-console-daw-mirror

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

---

## Usage

### GUI Workflow

1. **Load Session** — click "Load Session" or drag-and-drop a `.rtf` file
2. **Review Tracks** — inspect and edit the track table
3. **Select DAW** — choose REAPER, Cubase, or Nuendo from the dropdown
4. **Generate Session** — click "⚡ GENERATE SESSION" and choose output path

### Command Line (headless)

```python
import sys
sys.path.insert(0, "src")

from parser.digico_parser import DiGiCoParser
from exporters.reaper.reaper_exporter import REAPERExporter

# Parse
parser = DiGiCoParser()
session = parser.parse("show_report.rtf")

# Export
exporter = REAPERExporter()
output = exporter.export(session, "output/arena_show.rpp")
print(f"Exported: {output}")
```

---

## Architecture

```
Console Input (.rtf)
       ↓
 Parser Adapter
  DiGiCoParser
       ↓
Universal Session JSON
  {tracks, groups, buses, routing}
       ↓
  DAW Exporters
  ├── REAPERExporter    → .rpp
  ├── CubaseExporter    → .xml (Track Archive)
  └── NuendoExporter    → .xml (Track Archive)
```

### Key Principle

**The console is the source of truth.**

Track count, order, names, and routing from the console are preserved
exactly in the DAW output. No assumptions, no reordering.

---

## Project Structure

```
live-console-daw-mirror/
├── app.py                          ← Entry point
├── requirements.txt
├── src/
│   ├── parser/
│   │   ├── base_parser.py          ← Abstract parser base class
│   │   └── digico_parser.py        ← DiGiCo RTF parser
│   ├── models/
│   │   ├── session.py              ← Universal Session model
│   │   ├── track.py                ← Track data model
│   │   ├── bus.py                  ← Bus/subgroup model
│   │   └── routing.py              ← Routing assignment model
│   ├── exporters/
│   │   ├── base_exporter.py        ← Abstract exporter base class
│   │   ├── reaper/
│   │   │   └── reaper_exporter.py  ← REAPER .rpp generator
│   │   ├── cubase/
│   │   │   └── cubase_exporter.py  ← Cubase Track Archive XML
│   │   └── nuendo/
│   │       └── nuendo_exporter.py  ← Nuendo (inherits Cubase)
│   ├── gui/
│   │   ├── main_window.py          ← Main PySide6 window
│   │   └── track_table.py          ← Editable track table widget
│   └── logger.py                   ← Logging setup
├── tests/
│   └── test_suite.py               ← Full test suite
├── output/                         ← Default export directory
└── logs/                           ← Application logs
```

---

## Building a Standalone Executable

```bash
# Install PyInstaller
pip install pyinstaller

# Build
pyinstaller --onefile --windowed app.py

# Output will be in dist/app (or dist/app.exe on Windows)
```

For a named executable:
```bash
pyinstaller --onefile --windowed --name "LiveConsoleDawMirror" app.py
```

---

## Running Tests

```bash
cd live-console-daw-mirror
python -m pytest tests/test_suite.py -v
```

---

## Adding a New Console Parser

1. Create `src/parser/yourconsole_parser.py`
2. Inherit from `BaseParser`
3. Implement `parse(file_path: str) -> Session`
4. Add to the file type detection in `gui/main_window.py`

```python
from parser.base_parser import BaseParser
from models.session import Session

class YamahaParser(BaseParser):
    def __init__(self):
        super().__init__(console_name="Yamaha CL/QL")

    def parse(self, file_path: str) -> Session:
        path = self._validate_file(file_path)
        # ... parse the file ...
        return Session(console="Yamaha", tracks=[...])
```

## Adding a New DAW Exporter

1. Create `src/exporters/yourdaw/yourdaw_exporter.py`
2. Inherit from `BaseExporter`
3. Implement `export(session: Session, output_path: str) -> str`
4. Add to the DAW combo in `gui/main_window.py`

```python
from exporters.base_exporter import BaseExporter
from models.session import Session

class LogicExporter(BaseExporter):
    def __init__(self):
        super().__init__(daw_name="Logic Pro", file_extension=".logicx")

    def export(self, session: Session, output_path: str) -> str:
        path = self._ensure_output_dir(output_path)
        # ... generate the project file ...
        return str(path)
```

---

## License

MIT License. Built for the live sound, recording, and broadcast community.

---

*Live Console → DAW Mirror — reducing manual DAW setup time from hours to seconds.*
