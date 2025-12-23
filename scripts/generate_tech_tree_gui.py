from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from gui import MainWindow


def main() -> int:
    frozen = getattr(sys, "frozen", False)
    application_path = os.path.dirname(sys.executable) if frozen else os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(application_path, "config.ini")

    try:
        os.chdir(application_path)
    except OSError:
        pass

    app = QApplication(sys.argv)
    window = MainWindow(config_path=config_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
