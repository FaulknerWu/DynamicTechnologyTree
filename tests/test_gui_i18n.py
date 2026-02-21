# pyright: reportMissingImports=false

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, cast

import pytest

# Must be set before creating the QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
)  # noqa: E402

from gui.generation_worker import GenerationOutcome, GenerationOutcomeCode
from gui.i18n import default_language_from_system, map_locale_to_language_key, t
from gui.main_window import MainWindow
from gui.settings_renderer import PathFieldWidget
from settings_store import load_settings

def _make_window(tmp_path: Path, qt_app: Any) -> MainWindow:
    settings_path = tmp_path / "settings.json"
    window = MainWindow(config_path=settings_path)
    window.show()
    qt_app.processEvents()
    return window


def _language_combo(window: MainWindow) -> QComboBox:
    return cast(
        QComboBox,
        window.settings_panel.settings_renderer.widget_for("localization.language"),
    )


def _path_widget(window: MainWindow, field: str) -> PathFieldWidget:
    return cast(
        PathFieldWidget,
        window.settings_panel.settings_renderer.widget_for(f"paths.{field}"),
    )


def _configure_required_paths(window: MainWindow, tmp_path: Path) -> None:
    base_game_dir = tmp_path / "game"
    workshop_dir = tmp_path / "workshop"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    base_game_dir.mkdir(exist_ok=True)
    workshop_dir.mkdir(exist_ok=True)
    launcher_db.write_text("", encoding="utf-8")

    _path_widget(window, "base_game_path").setText(str(base_game_dir))
    _path_widget(window, "mod_folder_path").setText(str(workshop_dir))
    _path_widget(window, "launcher_db_path").setText(str(launcher_db))


def test_t_falls_back_to_english_for_missing_keys() -> None:
    assert t("ui_btn_generate", "french") == t("ui_btn_generate", "english")


def test_locale_mapping_and_default_language_selection() -> None:
    assert map_locale_to_language_key("en_US") == "english"
    assert map_locale_to_language_key("zh_CN") == "simp_chinese"
    assert map_locale_to_language_key("Chinese (Simplified)_China") == "simp_chinese"
    assert map_locale_to_language_key("pt_BR.UTF-8") == "braz_por"
    assert default_language_from_system(locale_name="pt_BR") == "english"
    assert (
        default_language_from_system(locale_name="Chinese (Simplified)_China")
        == "simp_chinese"
    )


def test_runtime_retranslation_updates_window_tabs_and_labels(
    tmp_path: Path, qt_app: Any, message_boxes
) -> None:
    window = _make_window(tmp_path, qt_app)
    try:
        combo = _language_combo(window)
        tabs = window.settings_panel.tabs_widget
        paths_tab = window.settings_panel.settings_renderer.tab_widget_for(
            "ui_tab_paths"
        )
        assert paths_tab is not None
        paths_index = tabs.indexOf(paths_tab)
        assert paths_index != -1

        max_children_label = window.settings_panel.settings_renderer.label_for(
            "display.max_children_per_node"
        )

        combo.setCurrentText("english")
        qt_app.processEvents()

        title_en = window.windowTitle()
        generate_en = window.generate_button.text()
        tab_en = tabs.tabText(paths_index)
        max_children_label_en = max_children_label.text()

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

        assert max_children_label.text() != max_children_label_en
        assert max_children_label.text() == t("ui_label_max_children", "simp_chinese")
        assert max_children_label_en == t("ui_label_max_children", "english")
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_save_config_validation_and_persistence(
    tmp_path: Path, qt_app: Any, message_boxes
) -> None:
    settings_path = tmp_path / "settings.json"
    window = _make_window(tmp_path, qt_app)
    try:
        language_combo = _language_combo(window)
        language_combo.setEditText("not_a_supported_language")
        qt_app.processEvents()

        message_boxes["warning"].clear()

        window.on_save_clicked()
        assert message_boxes[
            "warning"
        ], "expected QMessageBox.warning for invalid settings"
        assert not settings_path.exists(), "invalid settings should not be written"

        language_combo.setCurrentText("simp_chinese")
        _configure_required_paths(window, tmp_path)
        qt_app.processEvents()

        window.on_save_clicked()
        assert settings_path.exists(), "expected settings.json to be written"

        loaded = load_settings(settings_path)
        assert loaded.localization.language == "simp_chinese"

        text = settings_path.read_text(encoding="utf-8")
        assert '"localization"' in text
        assert '"language": "simp_chinese"' in text
        assert "priority_mods" not in text
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_language_locked_during_generation(
    tmp_path: Path, qt_app: Any, message_boxes, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _Signal:
        def __init__(self) -> None:
            self._slots: list[Callable[..., Any]] = []

        def connect(self, slot: Callable[..., Any]) -> None:
            self._slots.append(slot)

        def emit(self, *args: Any, **kwargs: Any) -> None:
            for slot in list(self._slots):
                slot(*args, **kwargs)

    class DummyWorker:
        def __init__(self, _settings: Any) -> None:
            self.log_message = _Signal()
            self.progress = _Signal()
            self.finished = _Signal()
            self._running = False

        def start(self) -> None:
            self._running = True
            self._running = False

        def isRunning(self) -> bool:
            return self._running

        def cancel(self) -> None:
            self._running = False

        def wait(self, *_args: Any, **_kwargs: Any) -> bool:
            self._running = False
            return True

        def deleteLater(self) -> None:
            return

    import gui.main_window as main_window_module

    monkeypatch.setattr(main_window_module, "GenerationWorker", DummyWorker)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(tmp_path / "current.sav"), ""),
    )

    window = _make_window(tmp_path, qt_app)
    try:
        _configure_required_paths(window, tmp_path)
        qt_app.processEvents()

        window.on_generate_clicked()
        language_combo = _language_combo(window)

        assert not language_combo.isEnabled()
        assert not window.save_button.isEnabled()

        window.on_generation_finished(
            GenerationOutcome(code=GenerationOutcomeCode.SUCCESS)
        )

        assert language_combo.isEnabled()
        assert window.save_button.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()
