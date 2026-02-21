# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

import pytest

from dtt_core.events import EventKind, GenerationEvent
from dtt_core.output import OutputWriter
from dtt_core.settings_snapshot import generator_config_from_settings
from models import Technology
from settings import Settings


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[GenerationEvent] = []

    def emit(self, event: GenerationEvent) -> None:
        self.events.append(event)


def _build_writer(
    *,
    config_root: Path,
    settings: Settings,
    event_sink: RecordingEventSink,
) -> OutputWriter:
    config = generator_config_from_settings(settings)

    tech_id = "tech_alpha"
    all_technologies = {
        tech_id: Technology(tech_id, research_area="physics", tier_level=1)
    }
    tech_descriptions = {tech_id: {"english": "Alpha description."}}

    def _render_tree(_tech: str, _lang_code: str, **_kwargs) -> str:
        return "tree"

    return OutputWriter(
        all_technologies=all_technologies,
        tech_descriptions=tech_descriptions,
        config=config,
        localize=lambda key, **kwargs: key,
        generate_tech_tree_content=_render_tree,
        application_root=config_root,
        event_sink=event_sink,
    )


def test_output_writer_exposes_artifact_summary_and_emits_artifact_events(
    tmp_path: Path,
) -> None:
    settings = Settings()
    settings.localization.language = "english"
    settings.output.yml_targets = [""]

    sink = RecordingEventSink()
    writer = _build_writer(config_root=tmp_path, settings=settings, event_sink=sink)

    result = writer.generate_all_yml_files()
    summary = result.artifact_summary

    assert summary.failed == []
    assert summary.skipped == []
    assert [path.name for path in summary.written] == [
        "zztechtreemain_l_english.yml",
        "zztechtreereplaced_l_english.yml",
        "dtt-save-report.txt",
    ]

    artifact_paths = [
        event.artifact_path
        for event in sink.events
        if event.kind is EventKind.ARTIFACT
    ]
    assert artifact_paths == [str(path) for path in summary.written]


def test_output_writer_failure_emits_structured_warning_and_records_failed_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings()
    settings.localization.language = "english"
    settings.output.yml_targets = [""]
    settings.output.on_write_error = "warn_and_continue"

    sink = RecordingEventSink()
    writer = _build_writer(config_root=tmp_path, settings=settings, event_sink=sink)

    failing_path = tmp_path / "localisation" / "zztechtreemain_l_english.yml"
    original_open = Path.open

    def _patched_open(self: Path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self == failing_path and "w" in mode:
            raise PermissionError("simulated unwritable target")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _patched_open)

    result = writer.generate_all_yml_files()
    summary = result.artifact_summary

    assert [failure.path for failure in summary.failed] == [failing_path]
    assert summary.failed[0].error_type == "PermissionError"
    assert "simulated unwritable target" in summary.failed[0].error

    warning_events = [event for event in sink.events if event.kind is EventKind.WARNING]
    assert len(warning_events) == 1
    warning = warning_events[0]
    assert ("file", str(failing_path)) in warning.details
    assert ("error_type", "PermissionError") in warning.details
    assert any(key == "error" and "simulated unwritable target" in value for key, value in warning.details)


def test_output_writer_skip_policy_records_skipped_paths_without_emitting_artifacts(
    tmp_path: Path,
) -> None:
    settings = Settings()
    settings.localization.language = "english"
    settings.output.yml_targets = [""]
    settings.output.on_existing_file = "skip"

    sink_first = RecordingEventSink()
    writer = _build_writer(
        config_root=tmp_path,
        settings=settings,
        event_sink=sink_first,
    )

    writer.generate_all_yml_files()

    sink_second = RecordingEventSink()
    writer.set_event_sink(sink_second)
    result = writer.generate_all_yml_files()
    summary = result.artifact_summary

    assert [path.name for path in summary.skipped] == [
        "zztechtreemain_l_english.yml",
        "zztechtreereplaced_l_english.yml",
        "dtt-save-report.txt",
    ]
    assert summary.written == []
    assert summary.failed == []
    assert sink_second.events == []
