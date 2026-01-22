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
    except OSError as exc:
        print(f"Warning: failed to set working directory to '{application_path}': {exc}")

    app = QApplication(sys.argv)

    # Load bundled CJK fonts for proper Chinese text display
    from gui.fonts import load_fonts, set_default_font
    if load_fonts():
        set_default_font(app)

    window = MainWindow(config_path=config_path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
