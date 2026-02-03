# PYINSTALLER

complexity: 2/5
scope: packaging/pyinstaller/*
inherits: ../../AGENTS.md

## OVERVIEW
Windows EXE build wiring for the PyQt6 GUI via a canonical PyInstaller spec.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Canonical spec | `packaging/pyinstaller/techtree_gui.spec` | Entry script: `src/gui/__main__.py`; GUI app (`console=False`) |

## CONVENTIONS
- Build must run on Windows (PyInstaller cross-build is not reliable); see `README.md`.
- Spec sets `pathex=["src"]` and relies on the hybrid import model (flat modules + packages under `src/`).
- When adding/removing modules used at runtime, update `hiddenimports` in `packaging/pyinstaller/techtree_gui.spec`.
- Keep data files (fonts) in `datas=`; missing data often fails only at runtime.

## ANTI-PATTERNS
- Duplicating spec files or adding extra launchers; `dtt-gui` + this spec are the supported entrypoints.
- Removing `hiddenimports` without testing a frozen build; import discovery differs from running from source.
- Forgetting to bundle required assets (currently `src/gui/fonts/NotoSansSC-Regular.otf`).
