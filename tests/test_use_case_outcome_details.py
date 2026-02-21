# pyright: reportMissingImports=false

from __future__ import annotations

import types
from pathlib import Path
from threading import Event

import pytest

import dtt_core.generate_localization as generate_localization_module
from dtt_core.events import EventKind, GenerationEvent, StageId
from dtt_core.generate_localization import GenerateLocalizationUseCase, GenerationSteps
from dtt_core.output import ArtifactWriteFailure, ArtifactWriteSummary


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[GenerationEvent] = []

    def emit(self, event: GenerationEvent) -> None:
        self.events.append(event)


def test_use_case_emits_done_outcome_details_from_artifact_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generate_localization_module,
        "prepare_run",
        lambda _save_path, *, country_id=None, save_reader_limits=None: types.SimpleNamespace(
            save_context=object(),
            selected_country_id=country_id or 7,
        ),
    )
    monkeypatch.setattr(
        generate_localization_module.EmpireProfile,
        "from_save_context",
        staticmethod(lambda _context, country_id=None: object()),
    )

    failing_summary = ArtifactWriteSummary(
        failed=[
            ArtifactWriteFailure(
                path=Path("localisation/failing.yml"),
                error_type="PermissionError",
                error="simulated",
            )
        ]
    )
    write_result = types.SimpleNamespace(artifact_summary=failing_summary)

    sink = RecordingEventSink()
    use_case = GenerateLocalizationUseCase(
        localize=lambda key, **kwargs: f"@@{key}",
        event_sink=sink,
        steps=GenerationSteps(
            require_save_path=lambda save_path: Path(save_path or "dummy.sav"),
            set_empire_profile=lambda _profile: None,
            scan_all_technology_files=lambda: None,
            build_technology_tree_relationships=lambda: None,
            scan_all_tech_descriptions=lambda: None,
            precompute_overlong_trees=lambda: None,
            report_circular_dependencies=lambda: None,
            display_generation_statistics=lambda: None,
            generate_all_yml_files=lambda: write_result,
        ),
    )

    use_case.run(save_path="ignored.sav")

    done_events = [event for event in sink.events if event.stage_id == StageId.DONE]
    assert len(done_events) == 1
    done = done_events[0]
    assert done.kind is EventKind.PROGRESS
    assert done.progress == 100

    details = dict(done.details)
    assert details["outcome_code"] == "incomplete"
    assert details["artifact_failed_count"] == "1"
    assert details["artifact_failed_paths"] == "localisation/failing.yml"


def test_use_case_cancellation_stops_before_output_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generate_localization_module,
        "prepare_run",
        lambda _save_path, *, country_id=None, save_reader_limits=None: types.SimpleNamespace(
            save_context=object(),
            selected_country_id=country_id or 7,
        ),
    )
    monkeypatch.setattr(
        generate_localization_module.EmpireProfile,
        "from_save_context",
        staticmethod(lambda _context, country_id=None: object()),
    )

    cancel_event = Event()
    calls: list[str] = []

    def _scan_all_technology_files() -> None:
        calls.append("scan_all_technology_files")
        cancel_event.set()

    def _unexpected(name: str):
        def _impl() -> None:
            raise AssertionError(f"did not expect {name} to run after cancellation")

        return _impl

    sink = RecordingEventSink()
    use_case = GenerateLocalizationUseCase(
        localize=lambda key, **kwargs: f"@@{key}",
        event_sink=sink,
        steps=GenerationSteps(
            require_save_path=lambda save_path: Path(save_path or "dummy.sav"),
            set_empire_profile=lambda _profile: None,
            scan_all_technology_files=_scan_all_technology_files,
            build_technology_tree_relationships=_unexpected(
                "build_technology_tree_relationships"
            ),
            scan_all_tech_descriptions=_unexpected("scan_all_tech_descriptions"),
            precompute_overlong_trees=_unexpected("precompute_overlong_trees"),
            report_circular_dependencies=_unexpected("report_circular_dependencies"),
            display_generation_statistics=_unexpected("display_generation_statistics"),
            generate_all_yml_files=_unexpected("generate_all_yml_files"),
        ),
    )

    use_case.run(save_path="ignored.sav", cancel_event=cancel_event)

    assert calls == ["scan_all_technology_files"]
    done_events = [event for event in sink.events if event.stage_id == StageId.DONE]
    assert len(done_events) == 1
    assert dict(done_events[0].details)["outcome_code"] == "cancelled"
