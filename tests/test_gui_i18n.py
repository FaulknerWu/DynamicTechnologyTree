from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any, Callable

import pytest

# Must be set before creating the QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gui.i18n import default_language_from_system, map_locale_to_language_key, t
from gui.main_window import MainWindow


@pytest.fixture(scope="session")
def qt_app() -> Any:
    """Create a single QApplication for offscreen GUI tests."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    # Prevent the app from quitting when the last test window closes.
    try:
        app.setQuitOnLastWindowClosed(False)
    except Exception:
        # Some stubs/type checkers model this as QCoreApplication; runtime is fine.
        pass
    return app


@pytest.fixture()
def message_boxes(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[tuple[tuple[Any, ...], dict[str, Any]]]]:
    """Patch QMessageBox to avoid modal dialogs during tests."""

    calls: dict[str, list[tuple[tuple[Any, ...], dict[str, Any]]]] = {
        "warning": [],
        "critical": [],
        "information": [],
    }

    def _stub(kind: str) -> Callable[..., Any]:
        def _impl(*args: Any, **kwargs: Any) -> Any:
            calls[kind].append((args, kwargs))
            return QMessageBox.StandardButton.Ok

        return _impl

    monkeypatch.setattr(QMessageBox, "warning", _stub("warning"))
    monkeypatch.setattr(QMessageBox, "critical", _stub("critical"))
    monkeypatch.setattr(QMessageBox, "information", _stub("information"))
    return calls


def _make_window(tmp_path: Path, qt_app: Any) -> MainWindow:
    cfg_path = tmp_path / "config.ini"
    window = MainWindow(config_path=cfg_path)
    window.show()
    qt_app.processEvents()
    return window


def test_t_falls_back_to_english_for_missing_keys() -> None:
    # french exists but intentionally has no ui_* strings.
    assert t("ui_btn_generate", "french") == t("ui_btn_generate", "english")


def test_locale_mapping_and_default_language_selection() -> None:
    assert map_locale_to_language_key("en_US") == "english"
    assert map_locale_to_language_key("zh_CN") == "simp_chinese"
    # Windows may provide display-name locale strings.
    assert map_locale_to_language_key("Chinese (Simplified)_China") == "simp_chinese"
    assert map_locale_to_language_key("pt_BR.UTF-8") == "braz_por"
    # braz_por has no ui_* keys, so GUI defaults to english for clarity.
    assert default_language_from_system(locale_name="pt_BR") == "english"
    assert (
        default_language_from_system(locale_name="Chinese (Simplified)_China")
        == "simp_chinese"
    )


def test_runtime_retranslation_updates_window_tabs_and_placeholders(
    tmp_path: Path, qt_app: Any, message_boxes
) -> None:
    window = _make_window(tmp_path, qt_app)
    try:
        combo = window.config_editor.language_combo
        tabs = window.config_editor.tabs
        paths_index = tabs.indexOf(window.config_editor.paths_tab)
        assert paths_index != -1

        # Force a known starting point.
        combo.setCurrentText("english")
        qt_app.processEvents()

        title_en = window.windowTitle()
        generate_en = window.generate_button.text()
        tab_en = tabs.tabText(paths_index)
        placeholder_en = window.config_editor.priority_mods_input.placeholderText()

        # Switch english -> simp_chinese and verify visible text changes.
        combo.setCurrentText("simp_chinese")
        qt_app.processEvents()

        assert window.windowTitle() != title_en
        assert window.windowTitle() == t("ui_app_title", "simp_chinese")
        assert title_en == t("ui_app_title", "english")

        assert window.generate_button.text() != generate_en
        assert window.generate_button.text() == t("ui_btn_generate", "simp_chinese")
        assert generate_en == t("ui_btn_generate", "english")

        assert tabs.tabText(paths_index) != tab_en
        assert tabs.tabText(paths_index) == t("ui_tab_paths", "simp_chinese")
        assert tab_en == t("ui_tab_paths", "english")

        assert (
            window.config_editor.priority_mods_input.placeholderText() != placeholder_en
        )
        assert window.config_editor.priority_mods_input.placeholderText() == t(
            "ui_placeholder_priority_mods", "simp_chinese"
        )
        assert placeholder_en == t("ui_placeholder_priority_mods", "english")
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_save_config_validation_and_persistence(
    tmp_path: Path, qt_app: Any, message_boxes
) -> None:
    cfg_path = tmp_path / "config.ini"
    window = _make_window(tmp_path, qt_app)
    try:
        # Missing required paths -> warning.
        window.config_editor.base_game_path_input.setText("")
        window.config_editor.mod_folder_path_input.setText("")
        message_boxes["warning"].clear()

        window.on_save_clicked()
        assert message_boxes["warning"], (
            "expected QMessageBox.warning for invalid config"
        )
        assert not cfg_path.exists(), "invalid config should not be written"

        # Required paths filled -> config.ini written with selected language.
        base_game_dir = tmp_path / "game"
        workshop_dir = tmp_path / "workshop"
        base_game_dir.mkdir()
        workshop_dir.mkdir()

        window.config_editor.base_game_path_input.setText(str(base_game_dir))
        window.config_editor.mod_folder_path_input.setText(str(workshop_dir))
        window.config_editor.language_combo.setCurrentText("simp_chinese")
        qt_app.processEvents()

        window.on_save_clicked()
        assert cfg_path.exists(), "expected config.ini to be written"

        parser = configparser.ConfigParser()
        parser.read(cfg_path, encoding="utf-8")
        assert parser.get("localization", "language") == "simp_chinese"

        text = cfg_path.read_text(encoding="utf-8")
        assert "[localization]" in text
        assert "language = simp_chinese" in text
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_language_locked_during_generation(
    tmp_path: Path, qt_app: Any, message_boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dummy signal object to satisfy `.connect()` usage without real threads.
    class _Signal:
        def __init__(self) -> None:
            self._slots: list[Callable[..., Any]] = []

        def connect(self, slot: Callable[..., Any]) -> None:
            self._slots.append(slot)

        def emit(self, *args: Any, **kwargs: Any) -> None:
            for slot in list(self._slots):
                slot(*args, **kwargs)

    class DummyWorker:
        def __init__(self, _config_path: str) -> None:
            self.log_message = _Signal()
            self.progress = _Signal()
            self.finished = _Signal()
            self._running = False

        def start(self) -> None:
            self._running = True

        def isRunning(self) -> bool:
            return self._running

        def cancel(self) -> None:
            self._running = False

        def wait(self, *_args: Any, **_kwargs: Any) -> bool:
            self._running = False
            return True

        def deleteLater(self) -> None:  # pragma: no cover
            return

    import gui.main_window as main_window_module

    monkeypatch.setattr(main_window_module, "GenerationWorker", DummyWorker)

    window = _make_window(tmp_path, qt_app)
    try:
        base_game_dir = tmp_path / "game"
        workshop_dir = tmp_path / "workshop"
        base_game_dir.mkdir()
        workshop_dir.mkdir()
        window.config_editor.base_game_path_input.setText(str(base_game_dir))
        window.config_editor.mod_folder_path_input.setText(str(workshop_dir))
        qt_app.processEvents()

        window.on_generate_clicked()

        assert not window.config_editor.language_combo.isEnabled()
        assert not window.save_button.isEnabled()

        window.on_generation_finished(True, "")

        assert window.config_editor.language_combo.isEnabled()
        assert window.save_button.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()
