# pyright: reportMissingImports=false

from __future__ import annotations

import os
import subprocess
import sys
import types
from dataclasses import FrozenInstanceError
from itertools import pairwise
from pathlib import Path

import pytest

import dtt_core.generate_localization as generate_localization_module
from conftest import _build_settings, _create_minimal_launcher_db, _write_sav
from dtt_core.events import (
    EventKind,
    EventSink,
    GenerationEvent,
    NullEventSink,
    StageId,
)
from dtt_core.generate_localization import GenerateLocalizationUseCase, GenerationSteps
from dtt_core.stdout_event_sink import StdoutEventSink
from generator import TechTreeGenerator
from settings import Settings


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[GenerationEvent] = []

    def emit(self, event: GenerationEvent) -> None:
        self.events.append(event)


def _build_generate_localization_use_case(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[GenerateLocalizationUseCase, RecordingEventSink, list[str]]:
    monkeypatch.setattr(
        generate_localization_module,
        "prepare_run",
        lambda _save_path, *, country_id=None, save_reader_limits=None: types.SimpleNamespace(
            save_context=object(),
            country_candidates=(7,),
            selected_country_id=country_id or 7,
        ),
    )
    monkeypatch.setattr(
        generate_localization_module.EmpireProfile,
        "from_save_context",
        staticmethod(lambda _context, country_id=None: object()),
    )

    step_calls: list[str] = []

    def _record(name: str) -> None:
        step_calls.append(name)

    sink = RecordingEventSink()
    use_case = GenerateLocalizationUseCase(
        localize=lambda key, **kwargs: f"@@{key}",
        event_sink=sink,
        steps=GenerationSteps(
            require_save_path=lambda save_path: Path(save_path or "dummy.sav"),
            set_empire_profile=lambda _profile: _record("set_empire_profile"),
            scan_all_technology_files=lambda: _record("scan_all_technology_files"),
            build_technology_tree_relationships=lambda: _record(
                "build_technology_tree_relationships"
            ),
            scan_all_tech_descriptions=lambda: _record("scan_all_tech_descriptions"),
            precompute_overlong_trees=lambda: _record("precompute_overlong_trees"),
            report_circular_dependencies=lambda: _record(
                "report_circular_dependencies"
            ),
            display_generation_statistics=lambda: _record(
                "display_generation_statistics"
            ),
            generate_all_yml_files=lambda: _record("generate_all_yml_files"),
        ),
    )
    return use_case, sink, step_calls


def _progress_events(events: list[GenerationEvent]) -> list[GenerationEvent]:
    return [
        event
        for event in events
        if event.kind is EventKind.PROGRESS and event.progress is not None
    ]


def _progress_values(events: list[GenerationEvent]) -> list[int]:
    return [int(event.progress) for event in events if event.progress is not None]


def test_generate_localization_progress_stage_order_and_milestones_are_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, sink, step_calls = _build_generate_localization_use_case(monkeypatch)

    use_case.run(save_path="ignored.sav")

    progress_events = _progress_events(sink.events)
    assert [event.stage_id for event in progress_events] == [
        StageId.SAVE_PARSE,
        StageId.SAVE_PARSE,
        StageId.LOAD_ORDER,
        StageId.RELATIONS,
        StageId.INGEST_L10N,
        StageId.RENDER,
        StageId.CYCLES,
        StageId.WRITE_OUTPUT,
        StageId.DONE,
    ]
    assert _progress_values(progress_events) == [
        5,
        10,
        20,
        35,
        45,
        50,
        60,
        80,
        100,
    ]
    assert step_calls == [
        "set_empire_profile",
        "scan_all_technology_files",
        "build_technology_tree_relationships",
        "scan_all_tech_descriptions",
        "precompute_overlong_trees",
        "report_circular_dependencies",
        "display_generation_statistics",
        "generate_all_yml_files",
    ]


def test_generate_localization_progress_monotonic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, sink, _step_calls = _build_generate_localization_use_case(monkeypatch)

    use_case.run(save_path="ignored.sav")

    progress_values = _progress_values(_progress_events(sink.events))
    assert progress_values
    assert all(
        current > previous for previous, current in pairwise(progress_values)
    ), progress_values


def test_generate_localization_progress_run_with_settings_uses_settings_milestones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_case, sink, step_calls = _build_generate_localization_use_case(monkeypatch)

    settings = Settings.model_validate(
        {
            "schema_version": 1,
            "paths": {},
            "localization": {"language": "english"},
            "display": {},
            "progress_milestones": {
                "save_parse_start": 1,
                "save_parse_parse": 2,
                "load_order": 3,
                "relations": 4,
                "ingest_l10n": 5,
                "render": 6,
                "cycles": 7,
                "write_output": 8,
                "done": 100,
            },
        },
        strict=True,
    )

    use_case.run_with_settings(settings=settings, save_path="ignored.sav")

    progress_events = _progress_events(sink.events)
    assert [event.stage_id for event in progress_events] == [
        StageId.SAVE_PARSE,
        StageId.SAVE_PARSE,
        StageId.LOAD_ORDER,
        StageId.RELATIONS,
        StageId.INGEST_L10N,
        StageId.RENDER,
        StageId.CYCLES,
        StageId.WRITE_OUTPUT,
        StageId.DONE,
    ]
    assert _progress_values(progress_events) == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        100,
    ]
    assert step_calls == [
        "set_empire_profile",
        "scan_all_technology_files",
        "build_technology_tree_relationships",
        "scan_all_tech_descriptions",
        "precompute_overlong_trees",
        "report_circular_dependencies",
        "display_generation_statistics",
        "generate_all_yml_files",
    ]


def test_stage_id_values_are_stable_machine_ids() -> None:
    assert tuple(stage.value for stage in StageId) == (
        "SAVE_PARSE",
        "LOAD_ORDER",
        "INGEST_TECH",
        "INGEST_L10N",
        "RELATIONS",
        "CYCLES",
        "RENDER",
        "WRITE_OUTPUT",
        "DONE",
    )


def test_event_kind_values_are_stable_machine_ids() -> None:
    assert tuple(kind.value for kind in EventKind) == (
        "progress",
        "log",
        "warning",
        "error",
        "artifact",
    )


def test_generation_event_is_immutable() -> None:
    event = GenerationEvent(
        stage_id=StageId.SAVE_PARSE,
        kind=EventKind.PROGRESS,
        message="Parsing save",
        progress=10,
        details=(("file", "example.sav"),),
    )

    with pytest.raises(FrozenInstanceError):
        event.message = "mutated"  # type: ignore[misc]


def test_null_event_sink_matches_protocol_and_accepts_events() -> None:
    sink = NullEventSink()
    assert isinstance(sink, EventSink)

    sink.emit(
        GenerationEvent(
            stage_id=StageId.DONE,
            kind=EventKind.LOG,
            message="Generation complete",
        )
    )


def test_event_module_import_does_not_import_pyqt6() -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_dir)
        if not existing_pythonpath
        else f"{src_dir}{os.pathsep}{existing_pythonpath}"
    )

    script = "\n".join(
        [
            "import importlib",
            "import json",
            "import sys",
            "importlib.import_module('dtt_core.events')",
            "pyqt_modules = sorted(name for name in sys.modules if name == 'PyQt6' or name.startswith('PyQt6.'))",
            "print(json.dumps(pyqt_modules))",
            "raise SystemExit(1 if pyqt_modules else 0)",
        ]
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, (
        "Expected dtt_core.events import to be Qt-free. "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )


def test_stdout_event_sink_prints_non_empty_messages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sink = StdoutEventSink()

    sink.emit(
        GenerationEvent(
            stage_id=StageId.RENDER,
            kind=EventKind.LOG,
            message="rendered",
        )
    )
    sink.emit(
        GenerationEvent(
            stage_id=StageId.RENDER,
            kind=EventKind.LOG,
            message="",
        )
    )

    assert capsys.readouterr().out == "rendered\n"


def test_run_generation_process_emits_typed_done_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    settings = _build_settings(
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=launcher_db,
    )
    save_path = _write_sav(
        tmp_path / "event-sink.sav",
        meta='name = "Event Sink Save"\n',
        gamestate="\n".join(
            [
                "player = {",
                "  0 = { country = 7 }",
                "}",
                "country = {",
                "  7 = {",
                '    name = "Event Sink Empire"',
                "    authority = auth_democratic",
                "  }",
                "}",
            ]
        ),
    )

    monkeypatch.chdir(tmp_path)
    generator = TechTreeGenerator(settings=settings)
    monkeypatch.setattr(generator, "_l", lambda key, **kwargs: f"@@{key}")

    sink = RecordingEventSink()
    generator.run_generation_process(save_path=save_path, event_sink=sink)

    done_events = [
        event
        for event in sink.events
        if event.stage_id == StageId.DONE and event.kind == EventKind.PROGRESS
    ]
    assert done_events
    assert done_events[-1].progress == 100
    assert done_events[-1].message == "@@msg_generation_done"
    assert sink.events[-1].stage_id == StageId.DONE
