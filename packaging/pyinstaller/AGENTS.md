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

## NOTES
- The repo ignores `*.spec` but un-ignores this canonical spec (`.gitignore`).
- Entry script is `src/gui/__main__.py`; keep `python -m gui` working for PyInstaller analysis.
- If a frozen build fails at runtime, `hiddenimports`/`datas` is the first place to look.
- Font asset is bundled via `datas=` (`src/gui/fonts/NotoSansSC-Regular.otf`).

## CONVENTIONS
- Build must run on Windows (PyInstaller cross-build is not reliable); see `README.md`.
- Spec sets `pathex=["src"]` and relies on the hybrid import model (flat modules + packages under `src/`).
- When adding/removing modules used at runtime, update `hiddenimports` in `packaging/pyinstaller/techtree_gui.spec`.
- Keep data files (fonts) in `datas=`; missing data often fails only at runtime.

## ANTI-PATTERNS
- Duplicating spec files or adding extra launchers; `dtt-gui` + this spec are the supported entrypoints.
- Removing `hiddenimports` without testing a frozen build; import discovery differs from running from source.
- Forgetting to bundle required assets (currently `src/gui/fonts/NotoSansSC-Regular.otf`).
