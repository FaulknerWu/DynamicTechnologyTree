# GUI (PyQt6)

## OVERVIEW
PyQt6 GUI for editing `config.ini`, auto-detecting Stellaris paths, and running generation on a background thread while streaming logs/progress.

complexity: 4/5
scope: src/gui/*
inherits: ../../AGENTS.md

## STRUCTURE
```
src/gui/
|-- __init__.py          # gui-script entrypoint: gui:main
|-- main_window.py       # MainWindow: UI shell + generation wiring
|-- config_editor.py     # ConfigEditor: edits config.ini sections
|-- generation_worker.py # GenerationWorker(QThread): runs generator + emits signals
|-- i18n.py              # translation + locale mapping + language defaults
|-- path_detector.py     # PathDetector: Steam/game/workshop/user-data discovery
|-- title_bar.py         # custom window chrome
`-- fonts/               # bundled CJK font + loader
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| GUI entrypoint | `src/gui/__init__.py:69` | `dtt-gui` calls `main()` |
| Main window | `src/gui/main_window.py:31` | Loads/saves config, hosts editor/logs/progress |
| Start generation | `src/gui/main_window.py:243` | Validates, saves config, starts worker |
| Background generation | `src/gui/generation_worker.py:44` | QThread.run redirects stdout/stderr to UI |
| Progress markers | `src/gui/generation_worker.py:57` | Derived from localized `msg_*` strings |
| Path auto-detect | `src/gui/path_detector.py:26` | Heuristics for Steam + Stellaris install |

## CONVENTIONS
- Do not block the UI thread: generation runs in `GenerationWorker(QThread)` (`src/gui/generation_worker.py:29`).
- Logs are transported by redirecting `stdout`/`stderr` into `log_message` (`src/gui/generation_worker.py:53`).
- Config persistence uses `configparser` and writes `config.ini` in-place (`src/gui/main_window.py:215`).

## ANTI-PATTERNS
- Losing debugging context: GUI error handling currently emits only `str(exc)` (`src/gui/generation_worker.py:73`).
- Divergent runtime roots: `gui.main()` resolves CWD/config via `_resolve_runtime_paths()` (`src/gui/__init__.py:32`), while `MainWindow._default_config_path()` falls back to `sys.argv[0]` (`src/gui/main_window.py:64`). Keep these semantics aligned if you change startup wiring.
- Hidden output location changes: generation output is relative to process CWD (`src/gui/__init__.py:71`); don't change cwd logic without updating docs/UI.
