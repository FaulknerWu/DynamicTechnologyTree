"""Module entrypoint for the PyQt6 GUI.

This allows `python -m gui` style execution and provides a stable PyInstaller
analysis target.
"""

from __future__ import annotations

from gui import main


if __name__ == "__main__":
    raise SystemExit(main())
