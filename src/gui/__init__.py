"""PyQt6 GUI entry point.

This project uses a flat import model (src/ on sys.path). We keep runtime path
resolution here to avoid divergent behaviors between dev and frozen builds.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication

if TYPE_CHECKING:
    from gui.generation_worker import GenerationWorker as GenerationWorker
    from gui.main_window import MainWindow as MainWindow


@dataclass(frozen=True)
class RuntimePaths:
    application_path: Path
    settings_path: Path


def _default_settings_path() -> Path:
    app_config_root = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppConfigLocation
    ).strip()
    if app_config_root:
        base_dir = Path(app_config_root)
    else:
        base_dir = Path.home() / ".config"

    if base_dir.name.lower() != "dynamic-technology-tree":
        base_dir = base_dir / "dynamic-technology-tree"

    return base_dir / "settings.json"


def __getattr__(name: str) -> Any:
    if name == "GenerationWorker":
        from gui.generation_worker import GenerationWorker as imported

        globals()[name] = imported
        return imported
    if name == "MainWindow":
        from gui.main_window import MainWindow as imported

        globals()[name] = imported
        return imported
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _find_project_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return None


def _resolve_runtime_paths() -> RuntimePaths:
    settings_path = _default_settings_path()

    frozen = getattr(sys, "frozen", False)
    if frozen:
        app_path = Path(sys.executable).resolve().parent
        return RuntimePaths(application_path=app_path, settings_path=settings_path)

    project_root = _find_project_root(Path(__file__).resolve())
    if project_root is not None:
        return RuntimePaths(application_path=project_root, settings_path=settings_path)

    return RuntimePaths(application_path=Path.cwd(), settings_path=settings_path)


def main() -> int:
    paths = _resolve_runtime_paths()

    app = QApplication(sys.argv)

    # Load bundled CJK fonts for proper Chinese text display
    from gui.fonts import load_fonts, set_default_font

    if load_fonts():
        set_default_font(app)

    window_cls = getattr(sys.modules[__name__], "MainWindow")
    window = window_cls(
        settings_path=str(paths.settings_path),
        application_path=paths.application_path,
    )
    window.show()
    return app.exec()


__all__ = ["GenerationWorker", "MainWindow", "main"]
