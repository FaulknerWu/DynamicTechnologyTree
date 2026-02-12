"""PyQt6 GUI entry point.

This project uses a flat import model (src/ on sys.path). We keep runtime path
resolution here to avoid divergent behaviors between dev and frozen builds.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from gui.config_editor import ConfigEditor
from gui.generation_worker import GenerationWorker
from gui.main_window import MainWindow


@dataclass(frozen=True)
class RuntimePaths:
    application_path: Path
    config_path: Path


def _find_project_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def _resolve_runtime_paths() -> RuntimePaths:
    """Resolve application root and default config.ini path.

    - Frozen builds: next to the executable.
    - Source/dev: prefer CWD if it already contains config.ini; otherwise prefer
      a detected project root; final fallback is CWD.

    Note: the generator writes outputs to relative paths (e.g. ./localisation),
    so the resolved application_path is also used as CWD.
    """
    frozen = getattr(sys, "frozen", False)
    if frozen:
        app_path = Path(sys.executable).resolve().parent
        return RuntimePaths(
            application_path=app_path, config_path=app_path / "config.ini"
        )

    cwd = Path.cwd()
    if (cwd / "config.ini").exists():
        return RuntimePaths(application_path=cwd, config_path=cwd / "config.ini")

    project_root = _find_project_root(Path(__file__).resolve())
    if project_root is not None:
        return RuntimePaths(
            application_path=project_root, config_path=project_root / "config.ini"
        )

    return RuntimePaths(application_path=cwd, config_path=cwd / "config.ini")


def _safe_chdir(target: Path) -> None:
    try:
        os.chdir(target)
    except OSError as exc:
        print(f"Warning: failed to set working directory to '{target}': {exc}")


def main() -> int:
    paths = _resolve_runtime_paths()
    _safe_chdir(paths.application_path)

    app = QApplication(sys.argv)

    # Load bundled CJK fonts for proper Chinese text display
    from gui.fonts import load_fonts, set_default_font

    if load_fonts():
        set_default_font(app)

    window = MainWindow(config_path=str(paths.config_path))
    window.show()
    return app.exec()


__all__ = ["ConfigEditor", "GenerationWorker", "MainWindow", "main"]
