# pyright: reportMissingImports=false

from __future__ import annotations

import json
import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.settings_json_editor import SettingsJsonEditor
from settings import Settings


def test_gui_settings_json_editor_invalid_json_marks_invalid_and_blocks_apply(
    qt_app: Any,
) -> None:
    settings = Settings()
    settings.paths.base_game_path = "/before"
    editor = SettingsJsonEditor(settings=settings, validation_delay_ms=1)
    editor.show()
    qt_app.processEvents()

    editor.text_edit.setPlainText("{")
    qt_app.processEvents()
    editor.validate_now()

    assert not editor.is_valid
    assert "line 1" in editor.validation_error.lower()
    assert "column 2" in editor.validation_error.lower()
    assert not editor.apply_to_bound_settings()
    assert settings.paths.base_game_path == "/before"

    editor.close()
    editor.deleteLater()
    qt_app.processEvents()


def test_gui_settings_json_editor_schema_invalid_reports_precise_path(
    qt_app: Any,
) -> None:
    settings = Settings()
    payload = settings.model_dump(mode="json")
    payload["display"]["unknown_display"] = 1

    editor = SettingsJsonEditor(settings=settings, validation_delay_ms=1)
    editor.show()
    qt_app.processEvents()

    editor.text_edit.setPlainText(json.dumps(payload, indent=2))
    qt_app.processEvents()
    editor.validate_now()

    assert not editor.is_valid
    assert "display.unknown_display" in editor.validation_error

    editor.close()
    editor.deleteLater()
    qt_app.processEvents()


def test_gui_settings_json_editor_apply_valid_json_updates_bound_settings(
    qt_app: Any,
) -> None:
    settings = Settings()
    payload = settings.model_dump(mode="json")
    payload["display"]["max_tree_depth"] = 7
    payload["ingestion"]["diagnostic_example_limit"] = 22
    payload["output"]["on_existing_file"] = "skip"

    editor = SettingsJsonEditor(settings=settings, validation_delay_ms=1)
    editor.show()
    qt_app.processEvents()

    editor.text_edit.setPlainText(json.dumps(payload, indent=2))
    qt_app.processEvents()

    assert editor.apply_to_bound_settings()
    assert editor.is_valid
    assert settings.display.max_tree_depth == 7
    assert settings.ingestion.diagnostic_example_limit == 22
    assert settings.output.on_existing_file == "skip"

    assert editor._validated_settings is not None
    editor._validated_settings.ingestion.diagnostic_example_limit = 99
    editor._validated_settings.output.on_existing_file = "fail"
    assert settings.ingestion.diagnostic_example_limit == 22
    assert settings.output.on_existing_file == "skip"

    editor.close()
    editor.deleteLater()
    qt_app.processEvents()
