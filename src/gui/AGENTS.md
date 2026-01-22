# GUI (PyQt6)

## OVERVIEW
PyQt6 GUI for editing `config.ini`, auto-detecting Stellaris paths, and running generation on a background thread while streaming logs/progress.

## STRUCTURE
```
src/gui/
|-- __init__.py          # console-script entrypoint: gui:main
|-- main_window.py       # MainWindow: UI shell + generation wiring
|-- config_editor.py     # ConfigEditor: edits config.ini sections
|-- generation_worker.py # GenerationWorker(QThread): runs generator + emits signals
|-- path_detector.py     # PathDetector: Steam/game/workshop/user-data discovery
|-- title_bar.py         # custom window chrome
`-- fonts/               # bundled CJK font + loader
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| GUI entrypoint | `src/gui/__init__.py:13` | `dtt-gui` calls `main()` |
| Main window | `src/gui/main_window.py:28` | Loads/saves config, hosts editor/logs/progress |
| Start generation | `src/gui/main_window.py:180` | Validates, saves config, starts worker |
| Background generation | `src/gui/generation_worker.py:40` | QThread.run redirects stdout/stderr to UI |
| Progress markers | `src/gui/generation_worker.py:52` | Derived from localized `msg_*` strings |
| Path auto-detect | `src/gui/path_detector.py:24` | Heuristics for Steam + Stellaris install |

## CONVENTIONS
- Do not block the UI thread: generation runs in `GenerationWorker(QThread)` (`src/gui/generation_worker.py:25`).
- Logs are transported by redirecting `stdout`/`stderr` into `log_message` (`src/gui/generation_worker.py:50`).
- Config persistence uses `configparser` and writes `config.ini` in-place (`src/gui/main_window.py:170`).

## ANTI-PATTERNS
- Losing debugging context: GUI error handling currently emits only `str(exc)` (`src/gui/generation_worker.py:65`).
- Divergent runtime roots: `gui.main()` uses `os.getcwd()` for non-frozen (`src/gui/__init__.py:15`), while `MainWindow._default_config_path()` uses `sys.argv[0]` (`src/gui/main_window.py:49`). Keep config path semantics consistent when changing startup code.
- Silent `chdir` failures: `os.chdir(...)` exceptions are ignored (`src/gui/__init__.py:18`).
