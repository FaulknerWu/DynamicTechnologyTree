# PROJECT KNOWLEDGE BASE

**Generated:** 2026-02-02T18:38:48Z
**Commit:** 109b1b4
**Branch:** main

complexity: 3/5
scope: repo-root
applies_to: everything unless overridden by a nearer AGENTS.md

## OVERVIEW
Python 3.10+ app that generates Stellaris tech-tree localization output for the "Dynamic Technology Tree" mod. Primary UX is a PyQt6 GUI (required) and a Windows PyInstaller-built EXE.

## STRUCTURE
```
./
|-- pyproject.toml                 # packaging + entrypoint + pytest config
|-- README.md                      # usage (GUI-only), config.ini schema, build notes
|-- packaging/
|   `-- pyinstaller/
|       `-- techtree_gui.spec      # canonical PyInstaller spec (Windows EXE build)
|-- src/
|   |-- generator.py               # TechTreeGenerator pipeline orchestrator (composition-based)
|   |-- config.py                  # config dataclasses + defaults
|   |-- models.py                  # Technology model
|   |-- localization.py            # LOCALIZATION_STRINGS + RESEARCH_AREA_ICONS
|   |-- dtt_core/                  # core pipeline stages (scan/parse/render/output/etc.)
|   `-- gui/                       # PyQt6 GUI (entrypoint, window, worker, path detection)
`-- tests/                         # pytest (minimal smoke coverage)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Run GUI (installed) | `pyproject.toml:19` | `dtt-gui = "gui:main"` (calls `src/gui/__init__.py:71`) |
| Run GUI (module) | `src/gui/__main__.py:12` | `python -m gui` executes `gui.main()` (also used by PyInstaller) |
| Core generation pipeline | `src/generator.py:144` | `run_generation_process()` stages: scan/parse -> relate -> describe -> cycle/stats -> output |
| Load config + enabled mods | `src/dtt_core/config_loader.py:18` | Reads `config.ini` and optionally parses `dlc_load.json` |
| Scan tech + localization | `src/dtt_core/scan_parse.py:18` | Tech `.txt` + localisation `.yml` scanning |
| Render tree text | `src/dtt_core/render.py:39` | Limit-aware tree formatting (depth/children/node caps) |
| Write output YML | `src/dtt_core/output.py:19` | Main tech tree + description replacement files |
| GUI generation thread | `src/gui/generation_worker.py:26` | Redirects stdout/stderr and derives progress from log markers |
| Path auto-detect | `src/gui/path_detector.py:24` | Steam/game/workshop/user-data detection |
| Test entrypoint | `tests/test_smoke.py:25` | Minimal smoke test around generator scan/relationship/description |
| Golden output regression | `tests/test_golden_output.py:35` | End-to-end fixture run; compares generated YML bytes to committed snapshots |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `TechTreeGenerator` | class | `src/generator.py:16` | Orchestrates generation stages via composed core components |
| `ConfigLoader` | class | `src/dtt_core/config_loader.py:18` | Loads `GeneratorConfig` + enabled MOD IDs; provides localized strings via `l()` |
| `ScanParseCore` | class | `src/dtt_core/scan_parse.py:18` | Scans tech definitions and localisation descriptions into in-memory maps |
| `RelationsBuilder` | class | `src/dtt_core/relations.py:7` | Builds prerequisite/unlock relationships and precomputes overlong roots |
| `TreeRenderer` | class | `src/dtt_core/render.py:39` | Produces formatted tree content with overflow handling |
| `OutputWriter` | class | `src/dtt_core/output.py:19` | Emits localisation output files; expands variant trees/descriptions |
| `CycleDetector` | class | `src/dtt_core/cycle.py:6` | Detects and reports circular dependencies |
| `StatsReporter` | class | `src/dtt_core/stats.py:8` | Computes and prints generation statistics |
| `MainWindow` | class | `src/gui/main_window.py:30` | GUI shell for config + generation + log output |
| `GenerationWorker` | class | `src/gui/generation_worker.py:26` | QThread that runs generator and signals logs/progress |
| `PathDetector` | class | `src/gui/path_detector.py:24` | Detects Stellaris/Steam paths (cross-platform heuristics) |
| `LOCALIZATION_STRINGS` | const | `src/localization.py:9` | User-facing text (UI + progress markers + warnings) |

## CONVENTIONS
- Python: `>=3.10` (`pyproject.toml:10`).
- Packaging: `package-dir = {"": "src"}`; flat modules are listed in `py-modules`, while packages under `src/` (e.g. `gui`, `dtt_core`) are discovered via `find_packages` (`pyproject.toml:21`).
- Entry point: `dtt-gui` runs `gui:main` (`pyproject.toml:19`).
- Module entry point: `python -m gui` runs `src/gui/__main__.py` (`src/gui/__main__.py:12`).
- Config file: `config.ini` is expected at runtime and is ignored by git (`.gitignore:26`).
- Outputs: generated mod content folders are ignored (`.gitignore:30`).

## ANTI-PATTERNS (THIS PROJECT)
- Silent exception swallowing: `except Exception: pass` exists when tagging overlong roots (`src/dtt_core/render.py:489`).
- Silent data loss during reads: `read_text(..., errors="ignore")` is used when scanning/parsing; prefer surfacing failures (not silently dropping bytes).
- Hidden path-detection failures: `PathDetector` may `except OSError: return []` (no warning) when reading Steam metadata (`src/gui/path_detector.py`).
- Adding extra launchers: prefer `dtt-gui` as the primary entrypoint; keep `python -m gui` for module execution/PyInstaller analysis only.
- Version drift on release: keep `pyproject.toml:7` aligned with release tagging/docs.
- Committing build artifacts: `dist/`/`build/`/`*.exe` are ignored (`.gitignore:13`); prefer keeping them out of git history.

## COMMANDS
```bash
# Dev install (GUI + tests)
python -m pip install -e ".[dev]"

# Run GUI via entry point
dtt-gui

# Run tests (pytest is configured in pyproject.toml)
python -m pytest

# Build Windows EXE (PyInstaller; run on Windows)
pyinstaller packaging/pyinstaller/techtree_gui.spec
```

## NOTES
- No CI config in this checkout (`.github/workflows` absent).
- Tests exist but coverage is small (smoke + golden snapshots).

## LOCAL AGENTS
- `src/AGENTS.md`
- `src/dtt_core/AGENTS.md`
- `src/gui/AGENTS.md`
- `tests/AGENTS.md`
- `build/AGENTS.md`
- `packaging/pyinstaller/AGENTS.md`
