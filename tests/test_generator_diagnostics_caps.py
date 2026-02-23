# pyright: reportMissingImports=false

from __future__ import annotations

from dtt_core.events import GenerationEvent
from generator import TechTreeGenerator
from models import Technology
from settings import Settings


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[GenerationEvent] = []

    def emit(self, event: GenerationEvent) -> None:
        self.events.append(event)


def _build_generator(
    *, overlong_tree_roots_log_limit: int | None = None
) -> TechTreeGenerator:
    settings_payload = Settings().model_dump(mode="python", round_trip=True)
    settings_payload["localization"]["language"] = "english"
    if overlong_tree_roots_log_limit is not None:
        settings_payload["diagnostics"][
            "overlong_tree_roots_log_limit"
        ] = overlong_tree_roots_log_limit

    settings = Settings.model_validate(settings_payload, strict=True)
    generator = TechTreeGenerator(settings=settings)
    generator._l = (  # type: ignore[method-assign]
        lambda key, **kwargs: f"{key}|{kwargs}" if kwargs else key
    )
    return generator


def _seed_overlong_roots(generator: TechTreeGenerator, root_ids: list[str]) -> None:
    generator.overlong_tech_ids = set(root_ids)
    for index, tech_id in enumerate(root_ids):
        generator.all_technologies[tech_id] = Technology(
            tech_id=tech_id,
            unlocked_tech_ids=[f"child_{index}_a", f"child_{index}_b"],
        )


def test_generator_diagnostics_caps_default_limit_keeps_non_truncating_behavior() -> (
    None
):
    generator = _build_generator()
    _seed_overlong_roots(generator, ["tech_gamma", "tech_beta", "tech_alpha"])

    sink = RecordingEventSink()
    generator._set_event_sink(sink)
    generator._emit_overlong_tree_roots()

    messages = [event.message for event in sink.events]
    assert generator.config.diagnostics.overlong_tree_roots_log_limit == 50
    assert sum(message.startswith("overbreadth_entry") for message in messages) == 3
    assert "overbreadth_list_header" in messages
    assert not any(message.startswith("overbreadth_truncated") for message in messages)


def test_generator_diagnostics_caps_custom_limit_truncates_overbreadth_entries() -> (
    None
):
    generator = _build_generator(overlong_tree_roots_log_limit=1)
    _seed_overlong_roots(generator, ["tech_c", "tech_a", "tech_b"])

    sink = RecordingEventSink()
    generator._set_event_sink(sink)
    generator._emit_overlong_tree_roots()

    messages = [event.message for event in sink.events]
    assert generator.config.diagnostics.overlong_tree_roots_log_limit == 1
    assert sum(message.startswith("overbreadth_entry") for message in messages) == 1

    truncated_messages = [
        message for message in messages if message.startswith("overbreadth_truncated")
    ]
    assert len(truncated_messages) == 1
    assert "'remaining': 2" in truncated_messages[0]
