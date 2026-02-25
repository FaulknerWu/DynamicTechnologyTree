# pyright: reportMissingImports=false

from __future__ import annotations

import codecs
from pathlib import Path

from config import (
    DisplayConfig,
    GeneratorConfig,
    LocalizationConfig,
    PathConfig,
)
from dtt_core.events import EventKind, GenerationEvent, StageId
from dtt_core.output import OutputWriter, plan_output_file_paths
from dtt_core.settings_snapshot import require_settings_snapshot
from models import Technology
from settings import Settings


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[GenerationEvent] = []

    def emit(self, event: GenerationEvent) -> None:
        self.events.append(event)


def _build_config(lang_code: str = "english") -> GeneratorConfig:
    return GeneratorConfig(
        paths=PathConfig(base_game_path=".", mod_folder_path="."),
        localization=LocalizationConfig(target_language_code=lang_code),
        display=DisplayConfig(
            max_children_per_node=12,
            max_tree_depth=4,
            max_display_nodes=128,
        ),
    )


def _expected_output_paths(lang_code: str, filename: str) -> list[Path]:
    base = Path("localisation")
    return [
        base / filename,
        base / lang_code / filename,
        base / "replace" / filename,
        base / lang_code / "replace" / filename,
        base / "zzz_tech_trees" / "replace" / filename,
    ]


def _read_identical_output_bytes(paths: list[Path]) -> bytes:
    assert len(paths) == 5
    for path in paths:
        assert path.exists(), f"missing output file: {path}"
    first = paths[0].read_bytes()
    for path in paths[1:]:
        assert path.read_bytes() == first
    return first


def _build_output_writer(
    *,
    config: GeneratorConfig | None = None,
    event_sink: RecordingEventSink | None = None,
    application_root: Path | None = None,
) -> OutputWriter:
    tech_id = "tech_alpha"
    all_technologies = {
        tech_id: Technology(tech_id, research_area="physics", tier_level=1)
    }
    tech_descriptions = {tech_id: {"english": "Alpha description."}}

    def _localize(key: str, **kwargs) -> str:
        file_path = kwargs.get("file", "")
        return f"{key}|file={file_path}"

    def _render_tree(tech: str, lang_code: str, **_kwargs) -> str:
        return f"{lang_code}:{tech}"

    return OutputWriter(
        all_technologies=all_technologies,
        tech_descriptions=tech_descriptions,
        config=_build_config() if config is None else config,
        localize=_localize,
        generate_tech_tree_content=_render_tree,
        application_root=application_root,
        event_sink=event_sink,
    )


def test_output_multi_target_writes_expected_candidate_paths_and_identical_bytes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    writer = _build_output_writer()
    writer.generate_all_yml_files()

    lang_code = "english"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"

    expected_main_paths = _expected_output_paths(lang_code, main_name)
    expected_replaced_paths = _expected_output_paths(lang_code, replaced_name)

    main_paths, main_failures = plan_output_file_paths(
        localisation_root=Path("localisation"),
        yml_targets=writer.config.output.yml_targets,
        lang_code=lang_code,
        filename=main_name,
    )
    assert not main_failures
    assert main_paths == expected_main_paths

    replaced_paths, replaced_failures = plan_output_file_paths(
        localisation_root=Path("localisation"),
        yml_targets=writer.config.output.yml_targets,
        lang_code=lang_code,
        filename=replaced_name,
    )
    assert not replaced_failures
    assert replaced_paths == expected_replaced_paths

    _read_identical_output_bytes(expected_main_paths)
    _read_identical_output_bytes(expected_replaced_paths)


def test_output_multi_target_default_root_is_relative_to_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    lang_code = "english"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    run_bytes: dict[str, bytes] = {}

    for run_name in ("run_a", "run_b"):
        run_root = tmp_path / run_name
        run_root.mkdir(parents=True)
        monkeypatch.chdir(run_root)

        writer = _build_output_writer()
        writer.generate_all_yml_files()

        relative_paths = _expected_output_paths(lang_code, main_name)
        absolute_paths = [run_root / path for path in relative_paths]
        run_bytes[run_name] = _read_identical_output_bytes(absolute_paths)

    assert run_bytes["run_a"] == run_bytes["run_b"]
    assert not (tmp_path / "localisation").exists()


def test_output_multi_target_application_root_overrides_process_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_cwd = tmp_path / "runtime-cwd"
    runtime_cwd.mkdir(parents=True)
    monkeypatch.chdir(runtime_cwd)

    application_root = tmp_path / "app-root"
    application_root.mkdir(parents=True)

    writer = _build_output_writer(application_root=application_root)
    writer.generate_all_yml_files()

    lang_code = "english"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    expected_absolute_paths = [
        application_root / path for path in _expected_output_paths(lang_code, main_name)
    ]
    planned_paths, failures = plan_output_file_paths(
        localisation_root=application_root / "localisation",
        yml_targets=writer.config.output.yml_targets,
        lang_code=lang_code,
        filename=main_name,
    )
    assert not failures
    assert planned_paths == expected_absolute_paths
    _read_identical_output_bytes(expected_absolute_paths)

    report_path = application_root / "localisation" / "dtt-save-report.txt"
    assert report_path.exists()
    assert not (runtime_cwd / "localisation").exists()


def test_output_encoding_uses_utf8_sig_for_yml_and_utf8_for_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    writer = _build_output_writer()
    writer.generate_all_yml_files()

    lang_code = "english"
    yml_names = [
        f"zztechtreemain_l_{lang_code}.yml",
        f"zztechtreereplaced_l_{lang_code}.yml",
    ]

    for yml_name in yml_names:
        for path in _expected_output_paths(lang_code, yml_name):
            yml_bytes = path.read_bytes()
            assert yml_bytes.startswith(codecs.BOM_UTF8)
            assert yml_bytes.decode("utf-8-sig").startswith("l_english:")

    report_path = Path("localisation") / "dtt-save-report.txt"
    report_bytes = report_path.read_bytes()
    assert not report_bytes.startswith(codecs.BOM_UTF8)
    assert report_bytes.decode("utf-8").startswith("dtt-save-report")


def test_output_failure_policy_single_unwritable_target_emits_warning_and_continues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    sink = RecordingEventSink()
    writer = _build_output_writer(event_sink=sink)

    lang_code = "english"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"
    failing_path = Path("localisation") / lang_code / main_name
    original_open = Path.open

    def _patched_open(self: Path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if self == failing_path and "w" in mode:
            raise PermissionError("simulated unwritable target")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _patched_open)

    writer.generate_all_yml_files()

    warning_events = [
        event
        for event in sink.events
        if event.kind == EventKind.WARNING and event.stage_id == StageId.WRITE_OUTPUT
    ]
    assert warning_events
    assert any("warn_write_file_failed" in event.message for event in warning_events)
    assert any(str(failing_path) in event.message for event in warning_events)
    assert not failing_path.exists()

    for path in _expected_output_paths(lang_code, main_name):
        if path == failing_path:
            continue
        assert path.exists()

    for path in _expected_output_paths(lang_code, replaced_name):
        assert path.exists()

    report_path = Path("localisation") / "dtt-save-report.txt"
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert "eligibility_counts:" in report_text
    assert "unknown_predicate_frequency_top:" in report_text
    assert "swap_ambiguities:" in report_text


def test_output_targets_customization_removing_target_stops_writing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = Settings()
    settings.localization.target_language_code = "english"
    settings.output.yml_targets = [
        "",
        "replace",
        "{lang_code}/replace",
        "zzz_tech_trees/replace",
    ]
    config = require_settings_snapshot(settings).generator_config

    writer = _build_output_writer(config=config)
    writer.generate_all_yml_files()

    lang_code = "english"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"

    removed_main = Path("localisation") / lang_code / main_name
    removed_replaced = Path("localisation") / lang_code / replaced_name
    assert not removed_main.exists()
    assert not removed_replaced.exists()

    expected_remaining = [
        Path("localisation") / main_name,
        Path("localisation") / "replace" / main_name,
        Path("localisation") / lang_code / "replace" / main_name,
        Path("localisation") / "zzz_tech_trees" / "replace" / main_name,
        Path("localisation") / replaced_name,
        Path("localisation") / "replace" / replaced_name,
        Path("localisation") / lang_code / "replace" / replaced_name,
        Path("localisation") / "zzz_tech_trees" / "replace" / replaced_name,
    ]
    for path in expected_remaining:
        assert path.exists(), f"missing configured output file: {path}"
