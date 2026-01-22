# PROJECT KNOWLEDGE BASE

**Generated:** 2026-01-22T12:46:28Z
**Commit:** 2aa9255
**Branch:** main

## OVERVIEW
Python 3.10+ app that generates Stellaris tech-tree localization output for the "Dynamic Technology Tree" mod. Primary UX is a PyQt6 GUI (optional extra) and a Windows PyInstaller-built EXE.

## STRUCTURE
```
./
|-- pyproject.toml                 # packaging + entrypoint + pytest config
|-- descriptor.mod                 # Stellaris mod metadata (version, workshop id)
|-- scripts/
|   `-- generate_tech_tree_gui.py  # repo-run / PyInstaller GUI launcher
|-- src/
|   |-- generator.py               # TechTreeGenerator pipeline orchestrator
|   |-- config.py                  # config dataclasses + defaults
|   |-- models.py                  # Technology model
|   |-- localization.py            # LOCALIZATION_STRINGS + RESEARCH_AREA_ICONS
|   |-- gui/                       # PyQt6 GUI (entrypoint, window, worker, path detection)
|   `-- mixins/                    # parsing/render/output pipeline stages
|-- build_win.ps1                  # Windows EXE build automation (PyInstaller)
|-- StellarisTechTreeGenerator.spec
`-- build/techtree_gui.spec
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Run GUI (installed) | `pyproject.toml:19` | `dtt-gui = "gui:main"` (calls `src/gui/__init__.py:13`) |
| Run GUI (repo script) | `scripts/generate_tech_tree_gui.py:15` | Injects `src/` into `sys.path` for flat imports |
| Core generation pipeline | `src/generator.py:33` | `run_generation_process()` stages: parse -> relate -> describe -> cycle/stats -> output |
| Parse tech + localization | `src/mixins/parser_mixin.py:70` | Tech `.txt` + localization `.yml` scanning |
| Render tree text | `src/mixins/render_mixin.py:330` | Limit-aware tree formatting (depth/children/node caps) |
| Write output YML | `src/mixins/output_mixin.py:212` | Main tech tree + description replacement files |
| GUI generation thread | `src/gui/generation_worker.py:25` | Redirects stdout/stderr and derives progress from log markers |
| Path auto-detect | `src/gui/path_detector.py:24` | Steam/game/workshop/user-data detection |

## CODE MAP
| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `TechTreeGenerator` | class | `src/generator.py:18` | Orchestrates generation stages via mixins |
| `ConfigAndLocalizationMixin` | class | `src/mixins/config_mixin.py:19` | Loads config + dlc_load.json + localized strings `_l()` |
| `ParserMixin` | class | `src/mixins/parser_mixin.py:9` | Parses technologies and localization descriptions |
| `RenderMixin` | class | `src/mixins/render_mixin.py:32` | Produces formatted tree content with overflow handling |
| `OutputMixin` | class | `src/mixins/output_mixin.py:18` | Emits localisation output files; expands variants |
| `MainWindow` | class | `src/gui/main_window.py:28` | GUI shell for config + generation + log output |
| `GenerationWorker` | class | `src/gui/generation_worker.py:25` | QThread that runs generator and signals logs/progress |
| `PathDetector` | class | `src/gui/path_detector.py:24` | Detects Stellaris/Steam paths (cross-platform heuristics) |
| `LOCALIZATION_STRINGS` | const | `src/localization.py:9` | User-facing text (UI + progress markers + warnings) |

## CONVENTIONS
- Python: `>=3.10` (`pyproject.toml:10`).
- Packaging: `package-dir = {"": "src"}` and flat modules via `py-modules = ["config", "generator", "localization", "models"]` (`pyproject.toml:22`).
- Entry point: `dtt-gui` runs `gui:main` (`pyproject.toml:19`).
- Config file: `config.ini` is expected at runtime and is ignored by git (`.gitignore:26`).
- Outputs: generated mod content folders are ignored (`.gitignore:30`).

## ANTI-PATTERNS (THIS PROJECT)
- Swallowed parse errors: `except Exception: pass` causes silent missing output (e.g. `src/mixins/parser_mixin.py:104`).
- Forked GUI entrypoints: `dtt-gui` (`src/gui/__init__.py:13`) vs `scripts/generate_tech_tree_gui.py:15` (different `application_path`/cwd logic).
- Silent cwd failures: `os.chdir(...)` errors are ignored (`src/gui/__init__.py:18`, `scripts/generate_tech_tree_gui.py:20`).
- Version drift on release: keep `descriptor.mod:1` and `pyproject.toml:7` aligned.
- Committing build artifacts: `dist/`/`build/`/`*.exe` are ignored (`.gitignore:13`); prefer keeping them out of git history.

## COMMANDS
```bash
# Dev install (GUI + tests)
python -m pip install -e ".[gui,dev]"

# Run GUI via entry point
dtt-gui

# Run tests (pytest is configured in pyproject.toml)
python -m pytest

# Build Windows EXE (PowerShell)
powershell -ExecutionPolicy Bypass -File build_win.ps1

# Build with PyInstaller spec
pyinstaller build/techtree_gui.spec
```

## NOTES
- `pyproject.toml` references `README.md` (`pyproject.toml:9`), but the file is missing in this checkout.
- There is no CI config (`.github/workflows` absent) and `tests/` is effectively empty (`tests/__init__.py:1`).
