from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError  # pyright: ignore[reportMissingImports]
from PyQt6.QtCore import QSignalBlocker, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from settings import Settings


class SettingsJsonEditor(QWidget):
    validation_changed = pyqtSignal(bool, str)

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        validation_delay_ms: int = 300,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._bound_settings: Settings = settings or Settings()
        self._validated_settings: Settings | None = None
        self._is_valid = True
        self._validation_error = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setObjectName("settingsJsonTextEdit")
        layout.addWidget(self.text_edit)

        self.validation_label = QLabel(self)
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)

        self._validation_timer = QTimer(self)
        self._validation_timer.setSingleShot(True)
        self._validation_timer.setInterval(max(validation_delay_ms, 0))
        self._validation_timer.timeout.connect(self.validate_now)

        self.text_edit.textChanged.connect(self._schedule_validation)

        self.set_settings(self._bound_settings)

    @property
    def is_valid(self) -> bool:
        return self._is_valid

    @property
    def validation_error(self) -> str:
        return self._validation_error

    def set_settings(self, settings: Settings) -> None:
        self._bound_settings = settings
        with QSignalBlocker(self.text_edit):
            self.text_edit.setPlainText(self._format_settings_json(settings))
        self.validate_now()

    def apply_to_bound_settings(self) -> bool:
        return self.apply_to(self._bound_settings)

    def apply_to(self, target: Settings) -> bool:
        if not self.validate_now() or self._validated_settings is None:
            return False

        validated_snapshot = self._validated_settings.model_copy(deep=True)
        for field_name in Settings.model_fields:
            setattr(target, field_name, getattr(validated_snapshot, field_name))
        return True

    def validate_now(self) -> bool:
        self._validation_timer.stop()

        raw_text = self.text_edit.toPlainText()
        parsed_payload: Any
        try:
            parsed_payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            self._set_validation_state(
                is_valid=False,
                error_message=(
                    f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
                ),
                settings=None,
            )
            return False

        try:
            parsed_settings = Settings.model_validate(parsed_payload, strict=True)
        except ValidationError as exc:
            self._set_validation_state(
                is_valid=False,
                error_message=self._format_schema_error(exc),
                settings=None,
            )
            return False

        self._set_validation_state(
            is_valid=True,
            error_message="",
            settings=parsed_settings,
        )
        return True

    def _schedule_validation(self) -> None:
        self._validation_timer.start()

    def _set_validation_state(
        self,
        *,
        is_valid: bool,
        error_message: str,
        settings: Settings | None,
    ) -> None:
        self._is_valid = is_valid
        self._validation_error = error_message
        self._validated_settings = settings

        if is_valid:
            self.validation_label.setText("JSON is valid.")
            self.validation_label.setStyleSheet("color: #2e7d32;")
        else:
            self.validation_label.setText(error_message)
            self.validation_label.setStyleSheet("color: #c62828;")

        self.validation_changed.emit(self._is_valid, self._validation_error)

    @staticmethod
    def _format_settings_json(settings: Settings) -> str:
        json_text = settings.model_dump_json(indent=2)
        if not json_text.endswith("\n"):
            json_text += "\n"
        return json_text

    @staticmethod
    def _format_schema_error(exc: ValidationError) -> str:
        errors = exc.errors(include_url=False)
        if not errors:
            return "Settings JSON does not match schema."

        first_error = errors[0]
        path = SettingsJsonEditor._format_error_path(first_error.get("loc", ()))
        msg = str(first_error.get("msg", "Invalid value"))
        return f"Schema validation failed at {path}: {msg}"

    @staticmethod
    def _format_error_path(loc: Any) -> str:
        if not isinstance(loc, tuple) or not loc:
            return "<root>"

        parts: list[str] = []
        for item in loc:
            if isinstance(item, int):
                parts.append(f"[{item}]")
                continue

            text = str(item)
            if not parts:
                parts.append(text)
            elif text:
                parts.append(f".{text}")

        return "".join(parts) or "<root>"


__all__ = ["SettingsJsonEditor"]
