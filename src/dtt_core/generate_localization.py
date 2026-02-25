from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from config import (
    DEFAULT_PROGRESS_CYCLES,
    DEFAULT_PROGRESS_DONE,
    DEFAULT_PROGRESS_INGEST_L10N,
    DEFAULT_PROGRESS_LOAD_ORDER,
    DEFAULT_PROGRESS_RELATIONS,
    DEFAULT_PROGRESS_RENDER,
    DEFAULT_PROGRESS_SAVE_PARSE_PARSE,
    DEFAULT_PROGRESS_SAVE_PARSE_START,
    DEFAULT_PROGRESS_WRITE_OUTPUT,
)
from dtt_core.events import EventEmitterMixin, EventKind, EventSink, StageId
from dtt_core.output import OutputWriteResult
from dtt_core.prepared_run import AmbiguousPlayerEmpireError, prepare_run
from dtt_core.run_outcome import RunOutcome, RunOutcomeCode
from dtt_core.sav_reader import SaveReaderError, SaveReaderLimits
from dtt_core.settings_snapshot import (
    ProgressMilestones,
    RunSettingsSnapshot,
    require_settings_snapshot,
)
from dtt_core.trigger_evaluator import EmpireProfile
from dtt_core.typed_error import TypedCoreError


def _noop_apply_settings_snapshot(_settings: RunSettingsSnapshot) -> None:
    return


@dataclass(frozen=True)
class GenerationSteps:
    require_save_path: Callable[[Path | str | None], Path]
    set_empire_profile: Callable[[EmpireProfile], None]
    scan_all_technology_files: Callable[[], None]
    build_technology_tree_relationships: Callable[[], None]
    scan_all_tech_descriptions: Callable[[], None]
    precompute_overlong_trees: Callable[[], None]
    report_circular_dependencies: Callable[[], None]
    display_generation_statistics: Callable[[], None]
    generate_all_yml_files: Callable[[], OutputWriteResult]
    require_settings: Callable[[object | None], RunSettingsSnapshot] = (
        require_settings_snapshot
    )
    apply_settings_snapshot: Callable[[RunSettingsSnapshot], None] = (
        _noop_apply_settings_snapshot
    )


@dataclass(frozen=True)
class _Stage:
    stage_id: StageId
    progress: int
    message: str
    details: tuple[tuple[str, str], ...] = ()
    action: Callable[[], None] | None = None
    cancel_progress_after_action: int | None = None


class GenerateLocalizationUseCase(EventEmitterMixin):
    _STAGE_ID = StageId.SAVE_PARSE

    def __init__(
        self,
        *,
        localize: Callable[..., str],
        event_sink: EventSink,
        steps: GenerationSteps,
    ) -> None:
        self._l = localize
        self._init_event_sink(event_sink)
        self._steps = steps

    def run(
        self,
        save_path: Path | str | None = None,
        *,
        country_id: int | None = None,
        cancel_event: Event | None = None,
    ) -> RunOutcome:
        default_progress = ProgressMilestones(
            save_parse_start=DEFAULT_PROGRESS_SAVE_PARSE_START,
            save_parse_parse=DEFAULT_PROGRESS_SAVE_PARSE_PARSE,
            load_order=DEFAULT_PROGRESS_LOAD_ORDER,
            relations=DEFAULT_PROGRESS_RELATIONS,
            ingest_l10n=DEFAULT_PROGRESS_INGEST_L10N,
            render=DEFAULT_PROGRESS_RENDER,
            cycles=DEFAULT_PROGRESS_CYCLES,
            write_output=DEFAULT_PROGRESS_WRITE_OUTPUT,
            done=DEFAULT_PROGRESS_DONE,
        )
        return self._run(
            save_path,
            country_id=country_id,
            progress_milestones=default_progress,
            save_reader_limits=None,
            cancel_event=cancel_event,
        )

    def run_with_settings(
        self,
        *,
        settings: object | None,
        save_path: Path | str | None = None,
        country_id: int | None = None,
        cancel_event: Event | None = None,
    ) -> RunOutcome:
        settings_snapshot = self._steps.require_settings(settings)
        self._steps.apply_settings_snapshot(settings_snapshot)

        return self._run(
            save_path,
            country_id=country_id,
            progress_milestones=settings_snapshot.progress_milestones,
            save_reader_limits=settings_snapshot.save_reader_limits,
            cancel_event=cancel_event,
        )

    def _run(
        self,
        save_path: Path | str | None,
        *,
        country_id: int | None,
        progress_milestones: ProgressMilestones,
        save_reader_limits: SaveReaderLimits | None,
        cancel_event: Event | None,
    ) -> RunOutcome:
        resolved_save_path = self._steps.require_save_path(save_path)
        write_result: OutputWriteResult | None = None
        last_progress = 0

        def _is_cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        def _finish_outcome(
            code: RunOutcomeCode,
            *,
            progress: int,
            message: str = "",
            error_code: str = "",
            error_details: tuple[tuple[str, str], ...] = (),
        ) -> RunOutcome:
            nonlocal last_progress
            last_progress = progress
            self._emit(
                EventKind.PROGRESS,
                self._l("msg_generation_done"),
                stage_id=StageId.DONE,
                progress=progress,
            )
            artifact_summary = (
                write_result.artifact_summary if write_result is not None else None
            )
            if artifact_summary is None:
                return RunOutcome(
                    code=code,
                    message=message,
                    error_code=error_code,
                    error_details=error_details,
                )
            return RunOutcome(
                code=code,
                artifact_summary=artifact_summary,
                message=message,
                error_code=error_code,
                error_details=error_details,
            )

        def _emit_progress(stage: _Stage) -> None:
            nonlocal last_progress
            last_progress = stage.progress
            self._emit(
                EventKind.PROGRESS,
                stage.message,
                stage_id=stage.stage_id,
                progress=stage.progress,
                details=stage.details,
            )

        prepared = None

        def _run_save_parse() -> None:
            nonlocal prepared
            if save_reader_limits is None:
                prepared = prepare_run(resolved_save_path, country_id=country_id)
            else:
                prepared = prepare_run(
                    resolved_save_path,
                    country_id=country_id,
                    save_reader_limits=save_reader_limits,
                )

            if prepared is None:
                raise RuntimeError("prepared run must be non-empty")

            self._steps.set_empire_profile(
                EmpireProfile.from_save_context(
                    prepared.save_context,
                    country_id=prepared.selected_country_id,
                )
            )

        def _run_cycles() -> None:
            self._steps.report_circular_dependencies()
            self._steps.display_generation_statistics()

        def _run_write_output() -> None:
            nonlocal write_result
            write_result = self._steps.generate_all_yml_files()

        stages = [
            _Stage(
                stage_id=StageId.SAVE_PARSE,
                progress=progress_milestones.save_parse_start,
                message=self._l("msg_start_generation"),
            ),
            _Stage(
                stage_id=StageId.SAVE_PARSE,
                progress=progress_milestones.save_parse_parse,
                message=self._l("msg_parsing_save"),
                details=(("save_path", str(resolved_save_path)),),
                action=_run_save_parse,
            ),
            _Stage(
                stage_id=StageId.LOAD_ORDER,
                progress=progress_milestones.load_order,
                message="",
                action=self._steps.scan_all_technology_files,
            ),
            _Stage(
                stage_id=StageId.RELATIONS,
                progress=progress_milestones.relations,
                message="",
                action=self._steps.build_technology_tree_relationships,
            ),
            _Stage(
                stage_id=StageId.INGEST_L10N,
                progress=progress_milestones.ingest_l10n,
                message="",
                action=self._steps.scan_all_tech_descriptions,
            ),
            _Stage(
                stage_id=StageId.RENDER,
                progress=progress_milestones.render,
                message=self._l("msg_counting_tree"),
                action=self._steps.precompute_overlong_trees,
            ),
            _Stage(
                stage_id=StageId.CYCLES,
                progress=progress_milestones.cycles,
                message="",
                action=_run_cycles,
            ),
            _Stage(
                stage_id=StageId.WRITE_OUTPUT,
                progress=progress_milestones.write_output,
                message=self._l("msg_evaluating_eligibility"),
                action=_run_write_output,
                cancel_progress_after_action=progress_milestones.done,
            ),
        ]

        if _is_cancelled():
            return _finish_outcome(
                RunOutcomeCode.CANCELLED,
                progress=progress_milestones.save_parse_start,
            )

        try:
            for stage in stages:
                if _is_cancelled():
                    return _finish_outcome(
                        RunOutcomeCode.CANCELLED,
                        progress=stage.progress,
                    )
                _emit_progress(stage)
                if _is_cancelled():
                    return _finish_outcome(
                        RunOutcomeCode.CANCELLED,
                        progress=stage.progress,
                    )
                if stage.action is not None:
                    stage.action()
                if _is_cancelled():
                    cancel_progress = (
                        stage.cancel_progress_after_action
                        if stage.cancel_progress_after_action is not None
                        else stage.progress
                    )
                    return _finish_outcome(
                        RunOutcomeCode.CANCELLED,
                        progress=cancel_progress,
                    )
        except (AmbiguousPlayerEmpireError, SaveReaderError):
            raise
        except TypedCoreError as exc:
            return _finish_outcome(
                RunOutcomeCode.ERROR,
                progress=last_progress,
                error_code=exc.code,
                error_details=exc.details,
            )
        except Exception as exc:
            try:
                message = self._l("error_generation_exception", error=exc)
            except Exception:
                message = str(exc)
            return _finish_outcome(
                RunOutcomeCode.ERROR,
                progress=last_progress,
                message=message,
            )

        if write_result is None:
            return _finish_outcome(
                RunOutcomeCode.ERROR,
                progress=progress_milestones.done,
                message="内部错误：缺少写出结果",
            )

        outcome_code = (
            RunOutcomeCode.INCOMPLETE
            if write_result.artifact_summary.has_failures
            else RunOutcomeCode.SUCCESS
        )
        return _finish_outcome(
            outcome_code,
            progress=progress_milestones.done,
        )



__all__ = ["GenerationSteps", "GenerateLocalizationUseCase"]
