# pyright: reportMissingImports=false

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from dtt_core.settings_snapshot import generator_config_from_settings
from dtt_core.run_outcome import RunOutcome, RunOutcomeCode
from gui.generation_worker import (
    GenerationOutcome,
    GenerationOutcomeCode,
    GenerationWorker,
)
from gui.i18n import t
from settings import Settings
from settings_store import CURRENT_SCHEMA_VERSION, SettingsStoreError, load_settings


def _capture_finished_outcome(worker: GenerationWorker) -> GenerationOutcome:
    outcomes: list[object] = []
    worker.finished.connect(outcomes.append)
    worker.run()

    assert len(outcomes) == 1, "expected exactly one finished signal"
    return cast(GenerationOutcome, outcomes[0])


def test_language_single_source_settings_drive_ui_and_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import gui.generation_worker as generation_worker_module

    def _unexpected_system_fallback() -> str:
        raise AssertionError("system locale fallback should not be consulted")

    monkeypatch.setattr(
        generation_worker_module,
        "default_language_from_system",
        _unexpected_system_fallback,
        raising=False,
    )
    monkeypatch.setattr(
        GenerationWorker,
        "_run_generator",
        lambda _self, *, save_path, country_id: RunOutcome(code=RunOutcomeCode.INCOMPLETE),
    )

    settings = Settings()
    settings.localization.language = "english"

    worker = GenerationWorker(settings)
    worker.save_path = "language-single-source.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.INCOMPLETE
    assert outcome.message == t("ui_worker_generation_incomplete", "english")

    config = generator_config_from_settings(settings)
    assert config.localization.target_language_code == settings.localization.language


def test_language_invalid_rejected_for_runtime_settings_and_json_load(
    tmp_path: Path,
) -> None:
    settings = Settings()
    settings.localization.language = "not_a_supported_language"

    worker = GenerationWorker(settings)
    worker.save_path = "language-invalid.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "settings.localization.language must be one of" in outcome.message
    assert "not_a_supported_language" in outcome.message

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "paths": {},
                "localization": {"language": "not_a_supported_language"},
                "display": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsStoreError) as exc_info:
        load_settings(settings_path)

    error = exc_info.value
    assert error.path == ("localization", "language")
    assert error.pydantic_errors is not None
    assert ("localization", "language") in {
        tuple(item["loc"]) for item in error.pydantic_errors
    }
