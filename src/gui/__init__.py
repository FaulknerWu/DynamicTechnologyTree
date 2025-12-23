"""GUI package for the Stellaris tech tree generator."""

import os
import sys

from PyQt6.QtWidgets import QApplication

from gui.config_editor import ConfigEditor
from gui.generation_worker import GenerationWorker
from gui.main_window import MainWindow


def main() -> int:
    frozen = getattr(sys, "frozen", False)
    application_path = os.path.dirname(sys.executable) if frozen else os.getcwd()
    config_path = os.path.join(application_path, "config.ini")

    try:
        os.chdir(application_path)
    except OSError:
        pass

    app = QApplication(sys.argv)

    # Load bundled CJK fonts for proper Chinese text display
    from gui.fonts import load_fonts, set_default_font
    if load_fonts():
        set_default_font(app)

    window = MainWindow(config_path=config_path)
    window.show()
    return app.exec()


__all__ = ["ConfigEditor", "GenerationWorker", "MainWindow", "main"]
