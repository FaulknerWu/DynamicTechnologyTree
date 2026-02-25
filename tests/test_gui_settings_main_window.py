# pyright: reportMissingImports=false

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QSpinBox

import gui as gui_module
from gui.main_window import MainWindow
from gui.settings_panel import SettingsPanel
from gui.settings_renderer import PathFieldWidget
from settings import Settings
from settings_store import load_settings, save_settings


def _write_profile(
    path: Path,
    *,
    base_game_path: str,
    mod_folder_path: str,
    launcher_db_path: str,
    max_tree_depth: int,
    ingestion_diagnostic_example_limit: int,
) -> None:
    settings = Settings()
    settings.paths.base_game_path = base_game_path
    settings.paths.mod_folder_path = mod_folder_path
    settings.paths.launcher_db_path = launcher_db_path
    settings.display.max_tree_depth = max_tree_depth
    settings.ingestion.diagnostic_example_limit = ingestion_diagnostic_example_limit
    save_settings(path, settings)


def _make_window(settings_path: Path, qt_app: Any) -> MainWindow:
    window = MainWindow(settings_path=settings_path)
    window.show()
    qt_app.processEvents()
    return window


def test_gui_settings_main_window_loads_settings_and_hosts_panel(
    tmp_path: Path,
    qt_app: Any,
) -> None:
    profile_path = tmp_path / "profile-a.json"
    _write_profile(
        profile_path,
        base_game_path="/profiles/a/game",
        mod_folder_path="/profiles/a/workshop",
        launcher_db_path="/profiles/a/launcher-v2.sqlite",
        max_tree_depth=9,
        ingestion_diagnostic_example_limit=10,
    )

    window = _make_window(profile_path, qt_app)
    try:
        assert isinstance(window.settings_panel, SettingsPanel)
        assert window.settings is window.settings_panel.settings
        assert window.settings_path == profile_path
        assert window.settings.display.max_tree_depth == 9

        depth_spin = cast(
            QSpinBox,
            window.settings_panel.settings_renderer.widget_for(
                "display.max_tree_depth"
            ),
        )
        assert depth_spin.value() == 9
        assert window.generate_button.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_gui_settings_main_window_switch_profile_refreshes_ssot_and_controls(
    tmp_path: Path,
    qt_app: Any,
) -> None:
    profile_a = tmp_path / "profile-a.json"
    profile_b = tmp_path / "profile-b.json"

    _write_profile(
        profile_a,
        base_game_path="/profiles/a/game",
        mod_folder_path="/profiles/a/workshop",
        launcher_db_path="/profiles/a/launcher-v2.sqlite",
        max_tree_depth=3,
        ingestion_diagnostic_example_limit=7,
    )
    _write_profile(
        profile_b,
        base_game_path="/profiles/b/game",
        mod_folder_path="/profiles/b/workshop",
        launcher_db_path="/profiles/b/launcher-v2.sqlite",
        max_tree_depth=8,
        ingestion_diagnostic_example_limit=42,
    )

    window = _make_window(profile_a, qt_app)
    try:
        assert window.switch_settings_profile(profile_b)
        qt_app.processEvents()

        assert window.settings_path == profile_b
        assert window.settings.paths.base_game_path == "/profiles/b/game"
        assert window.settings.display.max_tree_depth == 8
        assert window.settings.ingestion.diagnostic_example_limit == 42

        depth_spin = cast(
            QSpinBox,
            window.settings_panel.settings_renderer.widget_for(
                "display.max_tree_depth"
            ),
        )
        ingestion_spin = cast(
            QSpinBox,
            window.settings_panel.settings_renderer.widget_for(
                "ingestion.diagnostic_example_limit"
            ),
        )
        base_path_widget = cast(
            PathFieldWidget,
            window.settings_panel.settings_renderer.widget_for("paths.base_game_path"),
        )
        assert depth_spin.value() == 8
        assert ingestion_spin.value() == 42
        assert base_path_widget.text() == "/profiles/b/game"
        assert window.settings_profile_combo.currentText() == str(profile_b)
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_gui_settings_main_window_invalid_raw_json_disables_generate_and_warns(
    tmp_path: Path,
    qt_app: Any,
    message_boxes,
) -> None:
    profile_path = tmp_path / "profile-invalid.json"
    _write_profile(
        profile_path,
        base_game_path="/profiles/invalid/game",
        mod_folder_path="/profiles/invalid/workshop",
        launcher_db_path="/profiles/invalid/launcher-v2.sqlite",
        max_tree_depth=4,
        ingestion_diagnostic_example_limit=10,
    )

    window = _make_window(profile_path, qt_app)
    try:
        window.settings_panel.raw_editor.text_edit.setPlainText("{")
        qt_app.processEvents()
        window.settings_panel.raw_editor.validate_now()
        qt_app.processEvents()

        assert not window.generate_button.isEnabled()
        assert window.settings_error_label.isVisible()
        error_text = window.settings_error_label.text().lower()
        assert "line" in error_text
        assert "fix" in error_text

        window.on_generate_clicked()

        assert message_boxes["warning"]
        warning_args = message_boxes["warning"][-1][0]
        assert "fix" in str(warning_args[2]).lower()
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_gui_settings_main_window_save_persists_current_profile(
    tmp_path: Path,
    qt_app: Any,
) -> None:
    profile_path = tmp_path / "new-profile.json"
    window = _make_window(profile_path, qt_app)
    try:
        base_path_widget = cast(
            PathFieldWidget,
            window.settings_panel.settings_renderer.widget_for("paths.base_game_path"),
        )
        mod_path_widget = cast(
            PathFieldWidget,
            window.settings_panel.settings_renderer.widget_for("paths.mod_folder_path"),
        )
        launcher_db_widget = cast(
            PathFieldWidget,
            window.settings_panel.settings_renderer.widget_for(
                "paths.launcher_db_path"
            ),
        )
        depth_spin = cast(
            QSpinBox,
            window.settings_panel.settings_renderer.widget_for(
                "display.max_tree_depth"
            ),
        )

        base_path_widget.setText("/saved/game")
        mod_path_widget.setText("/saved/workshop")
        launcher_db_widget.setText("/saved/launcher-v2.sqlite")
        depth_spin.setValue(6)
        qt_app.processEvents()

        window.on_save_clicked()

        loaded = load_settings(profile_path)
        assert loaded.paths.base_game_path == "/saved/game"
        assert loaded.paths.mod_folder_path == "/saved/workshop"
        assert loaded.paths.launcher_db_path == "/saved/launcher-v2.sqlite"
        assert loaded.display.max_tree_depth == 6
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_gui_settings_main_window_default_path_uses_app_config_location(
    tmp_path: Path,
    qt_app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_config_root = tmp_path / "app-config-root"

    monkeypatch.setattr(
        gui_module.QStandardPaths,
        "writableLocation",
        staticmethod(lambda _location: str(app_config_root)),
    )

    window = MainWindow(settings_path=None)
    try:
        expected = app_config_root / "dynamic-technology-tree" / "settings.json"
        assert window.settings_path == expected
        assert window.settings_path.parent == expected.parent
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_gui_settings_main_window_ini_not_supported_on_startup(
    tmp_path: Path,
    qt_app: Any,
) -> None:
    legacy_profile = tmp_path / "legacy.ini"
    legacy_profile.write_text("[paths]\n", encoding="utf-8")

    window = _make_window(legacy_profile, qt_app)
    try:
        assert not window.generate_button.isEnabled()
        assert window.settings_error_label.isVisible()
        error_text = window.settings_error_label.text().lower()
        assert "ini settings profiles are no longer supported" in error_text
        assert "json settings profile" in error_text
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_gui_settings_main_window_ini_not_supported_on_profile_switch(
    tmp_path: Path,
    qt_app: Any,
    message_boxes,
) -> None:
    profile_path = tmp_path / "profile.json"
    _write_profile(
        profile_path,
        base_game_path="/profiles/base/game",
        mod_folder_path="/profiles/base/workshop",
        launcher_db_path="/profiles/base/launcher-v2.sqlite",
        max_tree_depth=5,
        ingestion_diagnostic_example_limit=10,
    )

    legacy_profile = tmp_path / "legacy.ini"
    legacy_profile.write_text("[paths]\n", encoding="utf-8")

    window = _make_window(profile_path, qt_app)
    try:
        assert not window.switch_settings_profile(legacy_profile)
        assert window.settings_path == profile_path
        assert message_boxes["warning"]
        warning_args = message_boxes["warning"][-1][0]
        assert "json settings profile" in str(warning_args[2]).lower()
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_gui_settings_main_window_invalid_blocks_missing_required_paths_block_generate(
    tmp_path: Path,
    qt_app: Any,
) -> None:
    profile_path = tmp_path / "missing-required.json"
    save_settings(profile_path, Settings())

    window = _make_window(profile_path, qt_app)
    try:
        assert not window.generate_button.isEnabled()
        assert window.settings_error_label.isVisible()
        assert (
            "fix the highlighted fields" in window.settings_error_label.text().lower()
        )
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()
