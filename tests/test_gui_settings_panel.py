# pyright: reportMissingImports=false

from __future__ import annotations

import json
import os
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QSpinBox, QTabWidget, QWidget

from gui.settings_json_editor import SettingsJsonEditor
from gui.settings_panel import SettingsPanel
from gui.settings_renderer import PathFieldWidget
from settings import Settings, settings_json_schema

_TRANSLATIONS = {
    "ui_tab_paths": "Paths",
    "ui_tab_localization": "Localization",
    "ui_tab_display": "Display",
    "ui_tab_advanced": "Advanced",
}

def _translate(key: str) -> str:
    return _TRANSLATIONS.get(key, key)


def _build_panel(qt_app: Any) -> tuple[SettingsPanel, Settings]:
    settings = Settings()
    panel = SettingsPanel(settings_json_schema(), settings, translate=_translate)
    panel.show()
    qt_app.processEvents()
    return panel, settings


def _tab_index_by_title(tab_widget: QTabWidget, title: str) -> int:
    for index in range(tab_widget.count()):
        if tab_widget.tabText(index) == title:
            return index
    return -1


def _is_descendant(widget: QWidget, ancestor: QWidget) -> bool:
    current: QWidget | None = widget
    while current is not None:
        if current is ancestor:
            return True
        current = current.parentWidget()
    return False


def test_gui_settings_panel_renders_schema_tabs_and_advanced_tab(qt_app: Any) -> None:
    panel, _settings = _build_panel(qt_app)
    try:
        tab_widget = panel.tabs_widget
        tab_titles = {tab_widget.tabText(index) for index in range(tab_widget.count())}
        assert {"Paths", "Localization", "Display", "Advanced"}.issubset(tab_titles)

        paths_tab_index = _tab_index_by_title(tab_widget, "Paths")
        assert paths_tab_index >= 0
        paths_tab = cast(QWidget, tab_widget.widget(paths_tab_index))

        base_game_path_widget = cast(
            PathFieldWidget, panel.settings_renderer.widget_for("paths.base_game_path")
        )
        assert _is_descendant(base_game_path_widget, paths_tab)

        advanced_tab_index = _tab_index_by_title(tab_widget, "Advanced")
        assert advanced_tab_index >= 0
        advanced_tab = cast(QWidget, tab_widget.widget(advanced_tab_index))

        assert isinstance(panel.raw_editor, SettingsJsonEditor)
        assert _is_descendant(panel.raw_editor, advanced_tab)
    finally:
        panel.close()
        panel.deleteLater()
        qt_app.processEvents()


def test_gui_settings_panel_raw_sync_apply_updates_settings_and_controls(
    qt_app: Any,
) -> None:
    panel, settings = _build_panel(qt_app)
    try:
        depth_spin = cast(
            QSpinBox,
            panel.settings_renderer.widget_for("display.max_tree_depth"),
        )
        base_game_path_widget = cast(
            PathFieldWidget,
            panel.settings_renderer.widget_for("paths.base_game_path"),
        )

        payload = settings.model_dump(mode="json")
        payload["display"]["max_tree_depth"] = 9
        payload["paths"]["base_game_path"] = "/tmp/panel-sync"

        panel.raw_editor.text_edit.setPlainText(json.dumps(payload, indent=2))
        qt_app.processEvents()

        assert panel.apply_raw_editor_changes() is True
        qt_app.processEvents()

        assert settings.display.max_tree_depth == 9
        assert depth_spin.value() == 9
        assert settings.paths.base_game_path == "/tmp/panel-sync"
        assert base_game_path_widget.text() == "/tmp/panel-sync"
    finally:
        panel.close()
        panel.deleteLater()
        qt_app.processEvents()
