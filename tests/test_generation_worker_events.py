# pyright: reportMissingImports=false

from __future__ import annotations

import os
import sys
import types
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dtt_core.events import EventKind, GenerationEvent, StageId
from dtt_core.prepared_run import AmbiguousPlayerEmpireError
from dtt_core.sav_reader import SaveReaderError
from dtt_core.save_context import SaveContext, SaveEmpireFacts
from gui.generation_worker import (
    GenerationOutcome,
    GenerationOutcomeCode,
    GenerationWorker,
)
from settings import Settings


def _capture_finished_outcome(worker: GenerationWorker) -> GenerationOutcome:
    outcomes: list[object] = []
    worker.finished.connect(outcomes.append)
    worker.run()

    assert len(outcomes) == 1, "expected exactly one finished signal emission"
    outcome = outcomes[0]
    assert isinstance(outcome, GenerationOutcome)
    return outcome


def _worker_settings() -> Settings:
    return Settings()


def test_generation_worker_events_forwarding_event_order_progress_filter_and_success_latch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scripted_events = [
        GenerationEvent(
            stage_id=StageId.SAVE_PARSE,
            kind=EventKind.LOG,
            message="begin",
        ),
        GenerationEvent(
            stage_id=StageId.SAVE_PARSE,
            kind=EventKind.PROGRESS,
            message="5%",
            progress=5,
        ),
        GenerationEvent(
            stage_id=StageId.LOAD_ORDER,
            kind=EventKind.PROGRESS,
            message="still 5%",
            progress=5,
        ),
        GenerationEvent(
            stage_id=StageId.LOAD_ORDER,
            kind=EventKind.PROGRESS,
            message="10%",
            progress=10,
        ),
        GenerationEvent(
            stage_id=StageId.RELATIONS,
            kind=EventKind.PROGRESS,
            message="progress missing value",
        ),
        GenerationEvent(
            stage_id=StageId.RENDER,
            kind=EventKind.WARNING,
            message="warning",
        ),
        GenerationEvent(
            stage_id=StageId.RENDER,
            kind=EventKind.PROGRESS,
            message="regression",
            progress=9,
        ),
        GenerationEvent(
            stage_id=StageId.RENDER,
            kind=EventKind.ERROR,
            message="error",
        ),
        GenerationEvent(
            stage_id=StageId.WRITE_OUTPUT,
            kind=EventKind.ARTIFACT,
            message="artifact",
            artifact_path="localisation/output.yml",
        ),
        GenerationEvent(
            stage_id=StageId.DONE,
            kind=EventKind.PROGRESS,
            message="done",
            progress=100,
        ),
    ]

    run_calls: list[tuple[str, int | None]] = []

    class FakeGenerator:
        def __init__(self, *, settings: Settings) -> None:
            assert isinstance(settings, Settings)
            return

        def run_generation_process(
            self,
            *,
            save_path: str,
            country_id: int | None,
            event_sink: Any,
            cancel_event: Any | None = None,
        ) -> None:
            del cancel_event
            run_calls.append((save_path, country_id))
            for event in scripted_events:
                event_sink.emit(event)

    monkeypatch.setitem(
        sys.modules,
        "generator",
        types.SimpleNamespace(TechTreeGenerator=FakeGenerator),
    )
    worker = GenerationWorker(_worker_settings())
    worker.save_path = "forwarding.sav"
    worker.country_id = 7

    forwarded_events: list[GenerationEvent] = []
    progress_updates: list[int] = []
    outcomes: list[object] = []

    worker.generation_event.connect(forwarded_events.append)
    worker.progress.connect(progress_updates.append)
    worker.finished.connect(outcomes.append)
    worker.run()

    assert forwarded_events == scripted_events
    assert {event.kind for event in forwarded_events} == set(EventKind)
    assert progress_updates == [5, 10, 100]
    assert all(
        current > previous for previous, current in pairwise(progress_updates)
    ), progress_updates

    assert run_calls == [("forwarding.sav", 7)]
    assert len(outcomes) == 1
    outcome = cast(GenerationOutcome, outcomes[0])
    assert outcome.code == GenerationOutcomeCode.SUCCESS


def test_generation_worker_events_failure_missing_save_path_emits_error() -> None:
    worker = GenerationWorker(_worker_settings())

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.ERROR
    assert outcome.message == "save_path is required and cannot be empty"


def test_generation_worker_events_failure_unsupported_save_format_maps_to_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_save_reader_error(
        _self: GenerationWorker,
        *,
        save_path: str,
        country_id: int | None,
    ) -> bool:
        del save_path, country_id
        raise SaveReaderError("unsupported save fixture")

    monkeypatch.setattr(GenerationWorker, "_run_generator", _raise_save_reader_error)

    worker = GenerationWorker(_worker_settings())
    worker.save_path = "unsupported.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.UNSUPPORTED_SAVE_FORMAT
    assert "unsupported save fixture" in outcome.message


def test_generation_worker_events_failure_generic_exception_maps_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_runtime_error(
        _self: GenerationWorker,
        *,
        save_path: str,
        country_id: int | None,
    ) -> bool:
        del save_path, country_id
        raise RuntimeError("boom")

    monkeypatch.setattr(GenerationWorker, "_run_generator", _raise_runtime_error)

    worker = GenerationWorker(_worker_settings())
    worker.save_path = "broken.sav"

    logs: list[str] = []
    worker.log_message.connect(logs.append)

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.ERROR
    assert outcome.message == "boom"
    assert logs
    assert "RuntimeError: boom" in logs[-1]


def test_generation_worker_events_failure_cancel_before_run_emits_cancelled() -> None:
    worker = GenerationWorker(_worker_settings())
    worker.cancel()

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.CANCELLED


def test_generation_worker_events_failure_ambiguous_country_selection_includes_empire_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_ambiguous_player_empire(
        _self: GenerationWorker,
        *,
        save_path: str,
        country_id: int | None,
    ) -> bool:
        del country_id
        save_context = SaveContext(
            save_path=save_path,
            player_country_candidates=(42, 7),
            empires_by_country_id={
                7: SaveEmpireFacts(country_id=7, country_name="Alpha Union"),
                42: SaveEmpireFacts(country_id=42, country_name="Beta Directorate"),
            },
        )
        raise AmbiguousPlayerEmpireError(
            save_context=save_context,
            country_candidates=(7, 42),
        )

    monkeypatch.setattr(
        GenerationWorker,
        "_run_generator",
        _raise_ambiguous_player_empire,
    )

    worker = GenerationWorker(_worker_settings())
    worker.save_path = "ambiguous.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.AMBIGUOUS_COUNTRY_SELECTION
    assert outcome.empire_options == (
        {"country_id": 7, "label": "7 - Alpha Union"},
        {"country_id": 42, "label": "42 - Beta Directorate"},
    )


def test_generation_worker_events_failure_incomplete_when_done_sentinel_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        GenerationWorker,
        "_run_generator",
        lambda _self, *, save_path, country_id: False,
    )

    worker = GenerationWorker(_worker_settings())
    worker.save_path = "incomplete.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.INCOMPLETE


def test_generation_worker_outcome_incomplete_maps_from_done_outcome_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGenerator:
        def __init__(self, *, settings: Settings) -> None:
            assert isinstance(settings, Settings)

        def run_generation_process(
            self,
            *,
            save_path: str,
            country_id: int | None,
            event_sink: Any,
            cancel_event: Any | None = None,
        ) -> None:
            del cancel_event
            del save_path, country_id
            event_sink.emit(
                GenerationEvent(
                    stage_id=StageId.DONE,
                    kind=EventKind.PROGRESS,
                    message="done",
                    progress=100,
                    details=(
                        ("outcome_code", "incomplete"),
                        ("artifact_failed_paths", "localisation/failing.yml"),
                    ),
                )
            )

    monkeypatch.setitem(
        sys.modules,
        "generator",
        types.SimpleNamespace(TechTreeGenerator=FakeGenerator),
    )

    settings = _worker_settings()
    settings.localization.language = "english"

    worker = GenerationWorker(settings)
    worker.save_path = "incomplete-details.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.INCOMPLETE
    assert "localisation/failing.yml" in outcome.message


def test_generation_worker_outcome_success_maps_from_done_outcome_details_with_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGenerator:
        def __init__(self, *, settings: Settings) -> None:
            assert isinstance(settings, Settings)

        def run_generation_process(
            self,
            *,
            save_path: str,
            country_id: int | None,
            event_sink: Any,
            cancel_event: Any | None = None,
        ) -> None:
            del cancel_event
            del save_path, country_id
            event_sink.emit(
                GenerationEvent(
                    stage_id=StageId.DONE,
                    kind=EventKind.PROGRESS,
                    message="done",
                    progress=100,
                    details=(
                        ("outcome_code", "success"),
                        ("artifact_skipped_count", "3"),
                    ),
                )
            )

    monkeypatch.setitem(
        sys.modules,
        "generator",
        types.SimpleNamespace(TechTreeGenerator=FakeGenerator),
    )

    settings = _worker_settings()
    settings.localization.language = "english"

    worker = GenerationWorker(settings)
    worker.save_path = "success-details.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.SUCCESS


def test_generation_worker_outcome_cancelled_maps_from_done_outcome_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGenerator:
        def __init__(self, *, settings: Settings) -> None:
            assert isinstance(settings, Settings)

        def run_generation_process(
            self,
            *,
            save_path: str,
            country_id: int | None,
            event_sink: Any,
            cancel_event: Any | None = None,
        ) -> None:
            del save_path, country_id, cancel_event
            event_sink.emit(
                GenerationEvent(
                    stage_id=StageId.DONE,
                    kind=EventKind.PROGRESS,
                    message="done",
                    progress=10,
                    details=(("outcome_code", "cancelled"),),
                )
            )

    monkeypatch.setitem(
        sys.modules,
        "generator",
        types.SimpleNamespace(TechTreeGenerator=FakeGenerator),
    )

    settings = _worker_settings()
    settings.localization.language = "english"

    worker = GenerationWorker(settings)
    worker.save_path = "cancelled-details.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.CANCELLED


def test_generation_worker_settings_snapshot_frozen_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_settings: list[tuple[str, int]] = []

    class FakeGenerator:
        def __init__(self, *, settings: Settings) -> None:
            captured_settings.append(
                (settings.localization.language, settings.display.max_tree_depth)
            )

        def run_generation_process(
            self,
            *,
            save_path: str,
            country_id: int | None,
            event_sink: Any,
            cancel_event: Any | None = None,
        ) -> None:
            del cancel_event
            event_sink.emit(
                GenerationEvent(
                    stage_id=StageId.DONE,
                    kind=EventKind.PROGRESS,
                    message="done",
                    progress=100,
                )
            )

    monkeypatch.setitem(
        sys.modules,
        "generator",
        types.SimpleNamespace(TechTreeGenerator=FakeGenerator),
    )
    settings = _worker_settings()
    settings.localization.language = "english"
    settings.display.max_tree_depth = 4

    worker = GenerationWorker(settings)
    worker.save_path = "snapshot.sav"

    settings.localization.language = "simp_chinese"
    settings.display.max_tree_depth = 9

    outcome = _capture_finished_outcome(worker)

    assert captured_settings == [("english", 4)]
    assert outcome.code == GenerationOutcomeCode.SUCCESS


def test_generation_worker_no_settings_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_source = (
        Path(__file__).resolve().parents[1] / "src" / "gui" / "generation_worker.py"
    ).read_text(encoding="utf-8")
    assert "configparser" not in worker_source
    assert "parser.read(" not in worker_source
    assert "load_save_context(" not in worker_source

    class FakeGenerator:
        def __init__(self, *, settings: Settings) -> None:
            assert isinstance(settings, Settings)

        def run_generation_process(
            self,
            *,
            save_path: str,
            country_id: int | None,
            event_sink: Any,
            cancel_event: Any | None = None,
        ) -> None:
            del cancel_event
            event_sink.emit(
                GenerationEvent(
                    stage_id=StageId.DONE,
                    kind=EventKind.PROGRESS,
                    message="done",
                    progress=100,
                )
            )

    opened_files: list[str] = []
    original_open = open

    def _tracking_open(file: Any, *args: Any, **kwargs: Any):
        opened_files.append(str(file))
        return original_open(file, *args, **kwargs)

    monkeypatch.setitem(
        sys.modules,
        "generator",
        types.SimpleNamespace(TechTreeGenerator=FakeGenerator),
    )
    monkeypatch.setattr("builtins.open", _tracking_open)

    worker = GenerationWorker(_worker_settings())
    worker.save_path = "no-io.sav"

    outcome = _capture_finished_outcome(worker)

    assert outcome.code == GenerationOutcomeCode.SUCCESS
    assert not [
        path for path in opened_files if path.endswith(".ini") or path.endswith(".json")
    ]
