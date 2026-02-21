"""Font loading utilities for the GUI application."""

from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

_loaded_font_family: str | None = None


def load_fonts() -> bool:
    """Load bundled font files into the application.

    Returns:
        True if at least one font was loaded successfully, False otherwise.
    """
    global _loaded_font_family

    font_dir = Path(__file__).parent
    font_path = font_dir / "NotoSansSC-Regular.otf"

    if not font_path.exists():
        return False

    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id == -1:
        return False

    families = QFontDatabase.applicationFontFamilies(font_id)
    if families:
        _loaded_font_family = families[0]
        return True

    return False


def set_default_font(app: QApplication, size: int = 10) -> None:
    """Set the application's default font to the bundled CJK font.

    Args:
        app: The QApplication instance.
        size: Font size in points.
    """
    if _loaded_font_family:
        font = QFont(_loaded_font_family, size)
        app.setFont(font)
