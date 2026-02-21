# pyright: reportMissingImports=false

from __future__ import annotations

import os
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dtt_core.swap_resolver import SwapCollision, SwapResolutionReport, SwapResolutionCollisionError
from gui.generation_worker import GenerationOutcome, GenerationOutcomeCode, GenerationWorker
from settings import Settings


def test_generation_worker_surfaces_swap_collision_as_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    settings.localization.language = "english"

    worker = GenerationWorker(settings)
    worker.save_path = "dummy.sav"

    def _boom(
        _self: GenerationWorker, *, save_path: str, country_id: int | None
    ) -> bool:
        del save_path, country_id
        report = SwapResolutionReport(
            collisions={
                "tech_shared_variant": SwapCollision(
                    base_tech_ids=("tech_base_a", "tech_base_b"),
                )
            }
        )
        raise SwapResolutionCollisionError(report)

    monkeypatch.setattr(GenerationWorker, "_run_generator", _boom)

    outcomes: list[object] = []
    worker.finished.connect(outcomes.append)
    worker.run()

    assert outcomes, "expected GenerationWorker to emit finished"
    outcome_obj = outcomes[-1]
    assert isinstance(outcome_obj, GenerationOutcome)
    outcome = cast(GenerationOutcome, outcome_obj)
    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "tech_shared_variant" in outcome.message
    assert "tech_base_a" in outcome.message
    assert "tech_base_b" in outcome.message

