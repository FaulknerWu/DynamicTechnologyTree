from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from collections.abc import Callable

from dtt_core.events import EventKind, EventSink, GenerationEvent, StageId
from dtt_core.prepared_run import prepare_run
from dtt_core.run_outcome import RunOutcomeCode
from dtt_core.sav_reader import SaveReaderLimits
from dtt_core.settings_snapshot import require_settings_snapshot
from dtt_core.trigger_evaluator import EmpireProfile
from settings import ProgressMilestonesSettings, Settings


def _noop_apply_settings_snapshot(_settings: Settings) -> None:
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
    generate_all_yml_files: Callable[[], object]
    require_settings: Callable[[Settings | None], Settings] = require_settings_snapshot
    apply_settings_snapshot: Callable[[Settings], None] = _noop_apply_settings_snapshot


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
        cancel_event: Event | None = None,
    ) -> None:
        self._run(
            save_path,
            country_id=country_id,
            progress_milestones=ProgressMilestonesSettings(),
            save_reader_limits=None,
            cancel_event=cancel_event,
        )

    def run_with_settings(
        self,
        *,
        settings: Settings | None,
        save_path: Path | str | None = None,
        country_id: int | None = None,
        cancel_event: Event | None = None,
    ) -> None:
        settings_snapshot = self._steps.require_settings(settings)
        self._steps.apply_settings_snapshot(settings_snapshot)

        save_reader_limits = SaveReaderLimits(
            max_member_uncompressed_size_bytes=settings_snapshot.save_reader.max_member_uncompressed_size_bytes,
            max_total_uncompressed_size_bytes=settings_snapshot.save_reader.max_total_uncompressed_size_bytes,
            max_parse_diagnostics_per_member=settings_snapshot.save_reader.max_parse_diagnostics_per_member,
        )
        self._run(
            save_path,
            country_id=country_id,
            progress_milestones=settings_snapshot.progress_milestones,
            save_reader_limits=save_reader_limits,
            cancel_event=cancel_event,
        )

    def _run(
        self,
        save_path: Path | str | None,
        *,
        country_id: int | None,
        progress_milestones: ProgressMilestonesSettings,
        save_reader_limits: SaveReaderLimits | None,
        cancel_event: Event | None,
    ) -> None:
        resolved_save_path = self._steps.require_save_path(save_path)

        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.save_parse_start)
            return

        self._emit(
            StageId.SAVE_PARSE,
            EventKind.PROGRESS,
            self._l("msg_start_generation"),
            progress=progress_milestones.save_parse_start,
        )
        self._emit(
            StageId.SAVE_PARSE,
            EventKind.PROGRESS,
            self._l("msg_parsing_save"),
            progress=progress_milestones.save_parse_parse,
            details=(("save_path", str(resolved_save_path)),),
        )
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.save_parse_parse)
            return

        if save_reader_limits is None:
            prepared = prepare_run(resolved_save_path, country_id=country_id)
        else:
            prepared = prepare_run(
                resolved_save_path,
                country_id=country_id,
                save_reader_limits=save_reader_limits,
            )

        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.save_parse_parse)
            return

        self._steps.set_empire_profile(
            EmpireProfile.from_save_context(
                prepared.save_context,
                country_id=prepared.selected_country_id,
            )
        )

        self._emit(
            StageId.LOAD_ORDER,
            EventKind.PROGRESS,
            "",
            progress=progress_milestones.load_order,
        )
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.load_order)
            return
        self._steps.scan_all_technology_files()
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.load_order)
            return
        self._emit(
            StageId.RELATIONS,
            EventKind.PROGRESS,
            "",
            progress=progress_milestones.relations,
        )
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.relations)
            return
        self._steps.build_technology_tree_relationships()
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.relations)
            return

        self._emit(
            StageId.INGEST_L10N,
            EventKind.PROGRESS,
            "",
            progress=progress_milestones.ingest_l10n,
        )
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.ingest_l10n)
            return
        self._steps.scan_all_tech_descriptions()
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.ingest_l10n)
            return

        self._emit(
            StageId.RENDER,
            EventKind.PROGRESS,
            self._l("msg_counting_tree"),
            progress=progress_milestones.render,
        )
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.render)
            return
        self._steps.precompute_overlong_trees()
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.render)
            return
        self._emit(
            StageId.CYCLES,
            EventKind.PROGRESS,
            "",
            progress=progress_milestones.cycles,
        )
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.cycles)
            return
        self._steps.report_circular_dependencies()
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.cycles)
            return
        self._steps.display_generation_statistics()
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.cycles)
            return

        self._emit(
            StageId.WRITE_OUTPUT,
            EventKind.PROGRESS,
            self._l("msg_evaluating_eligibility"),
            progress=progress_milestones.write_output,
        )
        if cancel_event is not None and cancel_event.is_set():
            self._emit_cancelled(progress=progress_milestones.write_output)
            return
        write_result = self._steps.generate_all_yml_files()
        if cancel_event is not None and cancel_event.is_set():
            # Keep any artifact summary details for diagnostics, but report the
            # overall run outcome as cancelled.
            self._emit_done(
                progress=progress_milestones.done,
                write_result=write_result,
                outcome_override=RunOutcomeCode.CANCELLED,
            )
            return

        self._emit_done(
            progress=progress_milestones.done,
            write_result=write_result,
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

    def _emit_done(
        self,
        *,
        progress: int,
        write_result: object,
        outcome_override: RunOutcomeCode | None = None,
    ) -> None:
        outcome_code = outcome_override or RunOutcomeCode.SUCCESS
        details: list[tuple[str, str]] = [("outcome_code", outcome_code.value)]

        artifact_summary = getattr(write_result, "artifact_summary", None)
        if artifact_summary is not None:
            written = getattr(artifact_summary, "written", ()) or ()
            skipped = getattr(artifact_summary, "skipped", ()) or ()
            failed = getattr(artifact_summary, "failed", ()) or ()
            details.extend(
                [
                    ("artifact_written_count", str(len(written))),
                    ("artifact_skipped_count", str(len(skipped))),
                    ("artifact_failed_count", str(len(failed))),
                ]
            )

            if outcome_override is None and failed:
                details[0] = ("outcome_code", RunOutcomeCode.INCOMPLETE.value)

            if failed:
                failed_paths = []
                for entry in failed:
                    path = getattr(entry, "path", None)
                    failed_paths.append(str(path) if path is not None else str(entry))
                details.append(("artifact_failed_paths", "\n".join(failed_paths)))

        self._emit(
            StageId.DONE,
            EventKind.PROGRESS,
            self._l("msg_generation_done"),
            progress=progress,
            details=tuple(details),
        )

    def _emit_cancelled(self, *, progress: int) -> None:
        self._emit(
            StageId.DONE,
            EventKind.PROGRESS,
            self._l("msg_generation_done"),
            progress=progress,
            details=(("outcome_code", RunOutcomeCode.CANCELLED.value),),
        )


__all__ = ["GenerationSteps", "GenerateLocalizationUseCase"]
