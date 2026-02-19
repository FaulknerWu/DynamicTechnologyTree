from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dtt_core.events import EventKind, EventSink, GenerationEvent, StageId
from dtt_core.sav_reader import load_save_context
from dtt_core.save_context import SaveContext
from dtt_core.trigger_evaluator import EmpireProfile


@dataclass(frozen=True)
class GenerationSteps:
    require_save_path: Callable[[Path | str | None], Path]
    resolve_country_id: Callable[[SaveContext, int | None], int]
    set_empire_profile: Callable[[EmpireProfile], None]
    scan_all_technology_files: Callable[[], None]
    build_technology_tree_relationships: Callable[[], None]
    scan_all_tech_descriptions: Callable[[], None]
    precompute_overlong_trees: Callable[[], None]
    report_circular_dependencies: Callable[[], None]
    display_generation_statistics: Callable[[], None]
    generate_all_yml_files: Callable[[], object]


class GenerateLocalizationUseCase:
    def __init__(
        self,
        *,
        localize: Callable[..., str],
        event_sink: EventSink,
        steps: GenerationSteps,
    ) -> None:
        self._l = localize
        self._event_sink = event_sink
        self._steps = steps

    def run(
        self,
        save_path: Path | str | None = None,
        *,
        country_id: int | None = None,
    ) -> None:
        resolved_save_path = self._steps.require_save_path(save_path)

        self._emit(
            StageId.SAVE_PARSE,
            EventKind.PROGRESS,
            self._l("msg_start_generation"),
            progress=5,
        )
        self._emit(
            StageId.SAVE_PARSE,
            EventKind.PROGRESS,
            self._l("msg_parsing_save"),
            progress=10,
            details=(("save_path", str(resolved_save_path)),),
        )
        save_context = load_save_context(resolved_save_path)
        selected_country_id = self._steps.resolve_country_id(save_context, country_id)

        self._steps.set_empire_profile(
            EmpireProfile.from_save_context(
                save_context,
                country_id=selected_country_id,
            )
        )

        self._emit(StageId.LOAD_ORDER, EventKind.PROGRESS, "", progress=20)
        self._steps.scan_all_technology_files()
        self._emit(StageId.RELATIONS, EventKind.PROGRESS, "", progress=35)
        self._steps.build_technology_tree_relationships()

        self._emit(StageId.INGEST_L10N, EventKind.PROGRESS, "", progress=45)
        self._steps.scan_all_tech_descriptions()

        self._emit(
            StageId.RENDER,
            EventKind.PROGRESS,
            self._l("msg_counting_tree"),
            progress=50,
        )
        self._steps.precompute_overlong_trees()
        self._emit(StageId.CYCLES, EventKind.PROGRESS, "", progress=60)
        self._steps.report_circular_dependencies()
        self._steps.display_generation_statistics()

        self._emit(
            StageId.WRITE_OUTPUT,
            EventKind.PROGRESS,
            self._l("msg_evaluating_eligibility"),
            progress=80,
        )
        self._steps.generate_all_yml_files()
        self._emit(
            StageId.DONE,
            EventKind.PROGRESS,
            self._l("msg_generation_done"),
            progress=100,
        )

    def _emit(
        self,
        stage_id: StageId,
        kind: EventKind,
        message: str,
        *,
        progress: int | None = None,
        details: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._event_sink.emit(
            GenerationEvent(
                stage_id=stage_id,
                kind=kind,
                message=message,
                progress=progress,
                details=details,
            )
        )


__all__ = ["GenerationSteps", "GenerateLocalizationUseCase"]
