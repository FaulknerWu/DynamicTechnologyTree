from __future__ import annotations

import importlib
import os
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = importlib.import_module("PyQt6.QtWidgets")
QComboBox = QtWidgets.QComboBox
QSpinBox = QtWidgets.QSpinBox

renderer_module = importlib.import_module("gui.settings_renderer")
PathFieldWidget = renderer_module.PathFieldWidget
render_settings_fields = renderer_module.render_settings_fields

settings_module = importlib.import_module("settings")
Settings = settings_module.Settings
settings_json_schema = settings_module.settings_json_schema

def _build_renderer(qt_app: Any) -> tuple[Any, Settings]:
    settings = Settings()
    renderer = render_settings_fields(settings_json_schema(), settings)
    renderer.widget.show()
    qt_app.processEvents()
    return renderer, settings


def test_gui_settings_renderer_renders_controls_for_all_current_settings_fields(
    qt_app: Any,
) -> None:
    renderer, _settings = _build_renderer(qt_app)
    try:
        expected_fields = {
            "schema_version",
            "paths.base_game_path",
            "paths.mod_folder_path",
            "paths.launcher_db_path",
            "paths.local_mod_folder_path",
            "localization.language",
            "display.max_children_per_node",
            "display.max_tree_depth",
            "display.max_display_nodes",
            "display.max_prereq_display",
        }

        assert expected_fields.issubset(renderer.field_widgets.keys())
        assert isinstance(renderer.widget_for("paths.base_game_path"), PathFieldWidget)
        assert isinstance(renderer.widget_for("paths.mod_folder_path"), PathFieldWidget)
        assert isinstance(
            renderer.widget_for("paths.launcher_db_path"), PathFieldWidget
        )
        assert isinstance(
            renderer.widget_for("paths.local_mod_folder_path"), PathFieldWidget
        )
        assert isinstance(renderer.widget_for("schema_version"), QSpinBox)
        assert isinstance(renderer.widget_for("localization.language"), QComboBox)
    finally:
        renderer.widget.close()
        renderer.widget.deleteLater()
        qt_app.processEvents()


def test_gui_settings_renderer_updates_settings_and_runs_validation_on_change(
    qt_app: Any,
) -> None:
    renderer, settings = _build_renderer(qt_app)
    try:
        path_widget = cast(PathFieldWidget, renderer.widget_for("paths.base_game_path"))
        depth_spin = cast(QSpinBox, renderer.widget_for("display.max_tree_depth"))
        language_combo = cast(QComboBox, renderer.widget_for("localization.language"))

        before_runs = renderer.validation_runs
        path_widget.setText("/tmp/stellaris")
        qt_app.processEvents()

        assert settings.paths.base_game_path == "/tmp/stellaris"
        assert renderer.validation_runs > before_runs

        before_runs = renderer.validation_runs
        depth_spin.setValue(9)
        qt_app.processEvents()

        assert settings.display.max_tree_depth == 9
        assert renderer.validation_runs > before_runs

        language_combo.setCurrentText("english")
        qt_app.processEvents()

        assert settings.localization.language == "english"
        assert renderer.error_for("localization.language") is None
    finally:
        renderer.widget.close()
        renderer.widget.deleteLater()
        qt_app.processEvents()


def test_gui_settings_renderer_validation_marks_invalid_enum_value(
    qt_app: Any,
) -> None:
    renderer, settings = _build_renderer(qt_app)
    try:
        language_combo = cast(QComboBox, renderer.widget_for("localization.language"))

        language_combo.setEditText("not_a_supported_language")
        qt_app.processEvents()

        assert settings.localization.language == "not_a_supported_language"
        assert renderer.validate() is False

        error_message = renderer.error_for("localization.language")
        assert error_message is not None
        assert "language must be one of" in error_message
        assert "c62828" in language_combo.styleSheet()
    finally:
        renderer.widget.close()
        renderer.widget.deleteLater()
        qt_app.processEvents()
