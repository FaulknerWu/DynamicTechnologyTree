from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SPEC_PATH = ROOT_DIR / "packaging" / "pyinstaller" / "techtree_gui.spec"


REQUIRED_HIDDENIMPORTS = {
    "config",
    "generator",
    "gui",
    "gui.config_editor",
    "gui.fonts",
    "gui.generation_worker",
    "gui.i18n",
    "gui.main_window",
    "gui.path_detector",
    "gui.title_bar",
    "localization",
    "models",
    "dtt_core.config_loader",
    "dtt_core.cycle",
    "dtt_core.eligibility",
    "dtt_core.events",
    "dtt_core.file_decode",
    "dtt_core.generate_localization",
    "dtt_core.ingestion_pipeline",
    "dtt_core.output",
    "dtt_core.relations",
    "dtt_core.render",
    "dtt_core.sav_reader",
    "dtt_core.save_context",
    "dtt_core.stats",
    "dtt_core.stdout_event_sink",
    "dtt_core.swap_resolver",
    "dtt_core.tech_merge",
    "dtt_core.trigger_evaluator",
}


IMPORT_SMOKE_MODULES = (
    "gui.__main__",
    "generator",
    "dtt_core.config_loader",
    "dtt_core.events",
    "dtt_core.generate_localization",
    "dtt_core.ingestion_pipeline",
    "dtt_core.output",
    "dtt_core.render",
    "dtt_core.sav_reader",
    "dtt_core.save_context",
)


def _analysis_hiddenimports(spec_source: str) -> set[str]:
    parsed = ast.parse(spec_source)
    for node in ast.walk(parsed):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id != "Analysis":
                continue
            for keyword in node.keywords:
                if keyword.arg != "hiddenimports":
                    continue
                if not isinstance(keyword.value, ast.List):
                    raise AssertionError("hiddenimports must be a literal list")

                imports: set[str] = set()
                for item in keyword.value.elts:
                    if not isinstance(item, ast.Constant) or not isinstance(
                        item.value, str
                    ):
                        raise AssertionError(
                            "hiddenimports entries must be literal strings"
                        )
                    imports.add(item.value)
                return imports
    raise AssertionError("Analysis(..., hiddenimports=[...]) not found in spec")


@pytest.fixture(scope="session")
def qt_app() -> Any:
    app: Any = QApplication.instance()
    if app is None:
        app = QApplication([])
    try:
        app.setQuitOnLastWindowClosed(False)
    except Exception:
        pass
    return app


def test_pyinstaller_spec_keeps_gui_entry_and_font_bundle() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")

    assert 'entry_script = src_dir / "gui" / "__main__.py"' in spec_text
    assert (
        'font_file = src_dir / "gui" / "fonts" / "NotoSansSC-Regular.otf"' in spec_text
    )
    assert '(str(font_file), "gui/fonts")' in spec_text


def test_pyinstaller_spec_hiddenimports_cover_runtime_modules() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    hiddenimports = _analysis_hiddenimports(spec_text)

    missing = REQUIRED_HIDDENIMPORTS.difference(hiddenimports)
    assert not missing, f"missing hiddenimports: {sorted(missing)}"


def test_packaging_entry_and_core_modules_are_importable() -> None:
    gui_main_path = SRC_DIR / "gui" / "__main__.py"
    assert gui_main_path.exists(), "src/gui/__main__.py is required for packaging"

    for module_name in IMPORT_SMOKE_MODULES:
        module = importlib.import_module(module_name)
        assert module is not None


def test_bundled_font_asset_loads_offscreen(qt_app: Any) -> None:
    font_path = SRC_DIR / "gui" / "fonts" / "NotoSansSC-Regular.otf"
    assert font_path.exists(), "bundled GUI font file must exist"

    assert qt_app is not None
    gui_fonts = importlib.import_module("gui.fonts")
    setattr(gui_fonts, "_loaded_font_family", None)

    assert gui_fonts.load_fonts(), "gui.fonts.load_fonts() should load bundled font"

    loaded_family = getattr(gui_fonts, "_loaded_font_family", None)
    assert isinstance(loaded_family, str) and loaded_family
    assert loaded_family in QFontDatabase.families()
