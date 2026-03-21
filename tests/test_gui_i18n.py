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
from gui.i18n import t
from gui.main_window import MainWindow
from gui.settings_renderer import PathFieldWidget
from settings_store import load_settings


def _make_window(tmp_path: Path, qt_app: Any) -> MainWindow:
    settings_path = tmp_path / "settings.json"
    window = MainWindow(settings_path=settings_path)
    window.show()
    qt_app.processEvents()
    return window


def _language_combo(window: MainWindow) -> QComboBox:
    return cast(
        QComboBox,
        window.settings_panel.settings_renderer.widget_for(
            "localization.target_language_code"
        ),
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
        settings_profile_label = window.settings_profile_label

        combo.setCurrentText("english")
        qt_app.processEvents()

        title_en = window.windowTitle()
        generate_en = window.generate_button.text()
        tab_en = tabs.tabText(paths_index)
        max_children_label_en = max_children_label.text()
        profile_label_en = settings_profile_label.text()
        raw_validation_en = window.settings_panel.raw_editor.validation_label.text()

        advanced_tab = window.settings_panel.advanced_tab
        advanced_index = tabs.indexOf(advanced_tab)
        assert advanced_index != -1
        advanced_tab_en = tabs.tabText(advanced_index)

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

        assert settings_profile_label.text() != profile_label_en
        assert settings_profile_label.text() == t(
            "ui_label_settings_profile", "simp_chinese"
        )
        assert profile_label_en == t("ui_label_settings_profile", "english")

        assert tabs.tabText(advanced_index) != advanced_tab_en
        assert tabs.tabText(advanced_index) == t("ui_tab_advanced", "simp_chinese")
        assert advanced_tab_en == t("ui_tab_advanced", "english")

        assert (
            window.settings_panel.raw_editor.validation_label.text()
            != raw_validation_en
        )
        assert window.settings_panel.raw_editor.validation_label.text() == t(
            "ui_settings_json_valid", "simp_chinese"
        )
        assert raw_validation_en == t("ui_settings_json_valid", "english")
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
        assert loaded.localization.target_language_code == "simp_chinese"

        text = settings_path.read_text(encoding="utf-8")
        assert '"localization"' in text
        assert '"target_language_code": "simp_chinese"' in text
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
