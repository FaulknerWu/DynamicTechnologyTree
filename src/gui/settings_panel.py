from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QTabWidget, QVBoxLayout, QWidget

from gui.settings_json_editor import SettingsJsonEditor
from gui.settings_renderer import SettingsRenderer, render_settings_fields
from settings import Settings

Translator = Callable[[str], str]


class SettingsPanel(QWidget):
    raw_apply_finished = pyqtSignal(bool, str)
    validation_changed = pyqtSignal(bool, str)

    def __init__(
        self,
        schema: dict[str, Any],
        settings: Settings | None = None,
        *,
        parent: QWidget | None = None,
        translate: Translator | None = None,
    ) -> None:
        super().__init__(parent)

        self.settings = settings or Settings()
        self.schema = schema
        self._translate = translate or (lambda key: key)
        self._renderer_valid = True
        self._renderer_error = ""
        self._raw_editor_valid = True
        self._raw_editor_error = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.settings_renderer: SettingsRenderer = render_settings_fields(
            self.schema,
            self.settings,
            parent=self,
            translate=self._translate,
            on_validation_changed=self._on_renderer_validation_changed,
        )
        layout.addWidget(self.settings_renderer.widget)

        self.tabs_widget: QTabWidget = self.settings_renderer.tabs_widget
        self.raw_editor = SettingsJsonEditor(
            settings=self.settings, parent=self.tabs_widget
        )
        self.apply_raw_button = QPushButton(
            self._t_or_default("ui_action_apply_json", "Apply JSON")
        )
        self.apply_raw_button.setObjectName("settingsPanelApplyRawButton")

        self.advanced_tab = QWidget(self.tabs_widget)
        advanced_layout = QVBoxLayout(self.advanced_tab)
        advanced_layout.setContentsMargins(10, 10, 10, 10)
        advanced_layout.setSpacing(8)
        advanced_layout.addWidget(self.raw_editor)

        controls_row = QHBoxLayout()
        controls_row.addStretch(1)
        controls_row.addWidget(self.apply_raw_button)
        advanced_layout.addLayout(controls_row)

        self.tabs_widget.addTab(
            self.advanced_tab,
            self._t_or_default("ui_tab_advanced", "Advanced"),
        )

        self.apply_raw_button.clicked.connect(self.apply_raw_editor_changes)
        self.raw_editor.validation_changed.connect(self._on_raw_validation_changed)
        self._on_raw_validation_changed(
            self.raw_editor.is_valid,
            self.raw_editor.validation_error,
        )

    def apply_raw_editor_changes(self) -> bool:
        applied = self.raw_editor.apply_to_bound_settings()
        if not applied:
            self.raw_apply_finished.emit(False, self.raw_editor.validation_error)
            return False

        self.settings_renderer.refresh_from_settings()
        self.raw_apply_finished.emit(True, "")
        return True

    def refresh_from_settings(self) -> None:
        self.settings_renderer.refresh_from_settings()
        self.raw_editor.set_settings(self.settings)
        self._emit_validation_changed()

    def retranslate(self, translate: Translator | None = None) -> None:
        if translate is not None:
            self._translate = translate

        self.settings_renderer.retranslate(self._translate)
        self.apply_raw_button.setText(
            self._t_or_default("ui_action_apply_json", "Apply JSON")
        )

        advanced_index = self.tabs_widget.indexOf(self.advanced_tab)
        if advanced_index != -1:
            self.tabs_widget.setTabText(
                advanced_index,
                self._t_or_default("ui_tab_advanced", "Advanced"),
            )

    @property
    def is_valid(self) -> bool:
        valid, _error = self.validation_state()
        return valid

    @property
    def validation_error(self) -> str:
        _valid, error = self.validation_state()
        return error

    def validation_state(self) -> tuple[bool, str]:
        if not self._renderer_valid:
            return False, self._renderer_error
        if not self._raw_editor_valid:
            return False, self._raw_editor_error
        return True, ""

    def _on_renderer_validation_changed(
        self, is_valid: bool, error_message: str
    ) -> None:
        self._renderer_valid = is_valid
        self._renderer_error = error_message.strip()
        self._emit_validation_changed()

    def _on_raw_validation_changed(self, is_valid: bool, _error_message: str) -> None:
        self.apply_raw_button.setEnabled(is_valid)
        self._raw_editor_valid = is_valid
        self._raw_editor_error = self.raw_editor.validation_error.strip()
        self._emit_validation_changed()

    def _emit_validation_changed(self) -> None:
        is_valid, error_message = self.validation_state()
        self.validation_changed.emit(is_valid, error_message)

    def _t_or_default(self, key: str, fallback: str) -> str:
        translated = self._translate(key)
        if translated and translated != key:
            return translated
        return fallback


__all__ = ["SettingsPanel"]
