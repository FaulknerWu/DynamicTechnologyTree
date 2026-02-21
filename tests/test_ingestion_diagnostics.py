# pyright: reportMissingImports=false

from __future__ import annotations

from dtt_core.ingestion_pipeline import IntegratedIngestionPipeline
from dtt_core.events import EventKind, GenerationEvent, StageId
from dtt_core.settings_snapshot import generator_config_from_settings
from settings import Settings


def _build_pipeline(
    *, diagnostic_example_limit: int | None = None
) -> IntegratedIngestionPipeline:
    settings_payload = Settings().model_dump(mode="python", round_trip=True)
    settings_payload["localization"]["language"] = "english"
    if diagnostic_example_limit is not None:
        settings_payload["ingestion"][
            "diagnostic_example_limit"
        ] = diagnostic_example_limit

    settings = Settings.model_validate(settings_payload, strict=True)
    config = generator_config_from_settings(settings)
    return IntegratedIngestionPipeline(
        config=config,
        localize=lambda key, **kwargs: key,
        all_technologies={},
        base_game_tech_ids=set(),
        tech_descriptions={},
        merged_tech_definitions={},
    )


def _record_many_examples(pipeline: IntegratedIngestionPipeline, *, count: int) -> None:
    for index in range(count):
        pipeline._record_tech_example(f"path-{index}", f"error-{index}")


def test_ingestion_pipeline_default_diagnostics_cap_records_ten_examples_per_stage() -> (
    None
):
    pipeline = _build_pipeline()

    _record_many_examples(pipeline, count=25)
    for index in range(25):
        pipeline._record_localisation_example(f"loc-{index}", f"loc-error-{index}")

    assert pipeline.config.ingestion.diagnostic_example_limit == 10
    assert len(pipeline.report.tech_examples) == 10
    assert pipeline.report.tech_examples[0] == ("path-0", "error-0")
    assert pipeline.report.tech_examples[-1] == ("path-9", "error-9")

    assert len(pipeline.report.localisation_examples) == 10
    assert pipeline.report.localisation_examples[0] == ("loc-0", "loc-error-0")
    assert pipeline.report.localisation_examples[-1] == ("loc-9", "loc-error-9")


def test_ingestion_diagnostics_custom_cap_reduces_examples_deterministically() -> None:
    pipeline = _build_pipeline(diagnostic_example_limit=3)

    _record_many_examples(pipeline, count=25)
    for index in range(25):
        pipeline._record_localisation_example(f"loc-{index}", f"loc-error-{index}")

    assert pipeline.config.ingestion.diagnostic_example_limit == 3
    assert len(pipeline.report.tech_examples) == 3
    assert pipeline.report.tech_examples == [
        ("path-0", "error-0"),
        ("path-1", "error-1"),
        ("path-2", "error-2"),
    ]

    assert len(pipeline.report.localisation_examples) == 3
    assert pipeline.report.localisation_examples == [
        ("loc-0", "loc-error-0"),
        ("loc-1", "loc-error-1"),
        ("loc-2", "loc-error-2"),
    ]


def test_ingestion_report_examples_are_stage_scoped_in_emission() -> None:
    pipeline = _build_pipeline(diagnostic_example_limit=10)
    pipeline._l = (  # type: ignore[method-assign]
        lambda key, **kwargs: f"{key}|{kwargs}"
    )

    class RecordingSink:
        def __init__(self) -> None:
            self.events: list[GenerationEvent] = []

        def emit(self, event: GenerationEvent) -> None:
            self.events.append(event)

    sink = RecordingSink()
    pipeline.set_event_sink(sink)

    pipeline.report.tech_files_total = 1
    pipeline.report.tech_files_failed = 1
    pipeline.report.tech_examples = [("tech.txt", "tech-error")]

    pipeline.report.localization_files_total = 1
    pipeline.report.localization_files_with_diagnostics = 1
    pipeline.report.localisation_examples = [("loc.yml", "loc-error")]

    pipeline._print_localization_report()

    warning_messages = [
        event.message
        for event in sink.events
        if event.stage_id == StageId.INGEST_L10N and event.kind is EventKind.WARNING
    ]
    assert any("loc.yml" in message for message in warning_messages)
    assert not any("tech.txt" in message for message in warning_messages)
