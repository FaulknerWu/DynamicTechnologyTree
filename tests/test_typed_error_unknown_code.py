# pyright: reportMissingImports=false

from __future__ import annotations

import os
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dtt_core.load_order_resolver import LoadOrderResolutionError
from gui.generation_worker import (
    GenerationOutcome,
    GenerationOutcomeCode,
    GenerationWorker,
)
from settings import Settings


def test_typed_error_unknown_code_surfaces_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    settings.localization.language = "english"

    worker = GenerationWorker(settings)
    worker.save_path = "dummy.sav"

    def _boom(
        self: GenerationWorker, *, save_path: str, country_id: int | None
    ) -> bool:
        raise LoadOrderResolutionError(
            code="unmapped_test_code",
            details=(("path", "dummy"),),
        )

    monkeypatch.setattr(GenerationWorker, "_run_generator", _boom)

    outcomes: list[object] = []
    worker.finished.connect(outcomes.append)
    worker.run()

    assert outcomes, "expected GenerationWorker to emit finished"
    outcome_obj = outcomes[-1]
    assert isinstance(outcome_obj, GenerationOutcome)
    outcome = cast(GenerationOutcome, outcome_obj)
    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "Unknown error code" in outcome.message
    assert "unmapped_test_code" in outcome.message
