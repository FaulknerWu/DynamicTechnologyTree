from __future__ import annotations

from pathlib import Path
from threading import Event

from dtt_core.cycle import CycleDetector
from dtt_core.events import EventKind, EventSink, GenerationEvent, StageId
from dtt_core.generate_localization import GenerateLocalizationUseCase, GenerationSteps
from dtt_core.ingestion_pipeline import IntegratedIngestionPipeline
from dtt_core.output import OutputWriter
from dtt_core.relations import RelationsBuilder
from dtt_core.render import TreeRenderer
from dtt_core.run_outcome import RunOutcome
from dtt_core.settings_snapshot import RunSettingsSnapshot, require_settings_snapshot
from dtt_core.stats import StatsReporter
from dtt_core.stdout_event_sink import StdoutEventSink
from dtt_core.tech_merge import MergedTechDefinition
from dtt_core.trigger_evaluator import EmpireProfile
from gui.i18n import t
from localization import LOCALIZATION_STRINGS, RESEARCH_AREA_ICONS
from models import Technology
from settings import Settings


class TechTreeGenerator:
    def __init__(
        self,
        *,
        settings: Settings | RunSettingsSnapshot | None = None,
        application_root: Path | str | None = None,
    ):
        self._event_sink: EventSink = StdoutEventSink()
        self._cancel_event: Event | None = None
        self.all_technologies: dict[str, Technology] = {}
        self.base_game_tech_ids = set()
        self.tech_descriptions = {}
        self.merged_tech_definitions: dict[str, MergedTechDefinition] = {}
        self.overlong_tech_ids = set()
        self._application_root = (
            Path(application_root) if application_root is not None else None
        )

        self._settings_snapshot = require_settings_snapshot(settings)
        self.config = self._settings_snapshot.generator_config
        self._ingestion_pipeline = IntegratedIngestionPipeline(
            config=self.config,
            localize=self._l,
            all_technologies=self.all_technologies,
            base_game_tech_ids=self.base_game_tech_ids,
            tech_descriptions=self.tech_descriptions,
            merged_tech_definitions=self.merged_tech_definitions,
            event_sink=self._event_sink,
        )
        self._relations_builder = RelationsBuilder(
            self.all_technologies,
            self.overlong_tech_ids,
            self.config.display,
        )
        self._tree_renderer = TreeRenderer(
            self.all_technologies,
            self.config.display,
            localization_strings=LOCALIZATION_STRINGS,
            research_area_icons=RESEARCH_AREA_ICONS,
            overlong_tech_ids=self.overlong_tech_ids,
        )
        self._cycle_detector = CycleDetector(
            self.all_technologies,
            self._l,
            event_sink=self._event_sink,
        )
        self._output_writer = OutputWriter(
            all_technologies=self.all_technologies,
            tech_descriptions=self.tech_descriptions,
            config=self.config,
            localize=self._l,
            generate_tech_tree_content=self.generate_tech_tree_content,
            merged_tech_definitions=self.merged_tech_definitions,
            application_root=self._application_root,
            event_sink=self._event_sink,
        )
        self._stats_reporter = StatsReporter(
            self.all_technologies,
            self.base_game_tech_ids,
            self.tech_descriptions,
            self.overlong_tech_ids,
            self.config,
            self._l,
            self._emit_overlong_tree_roots,
            event_sink=self._event_sink,
        )

    def _l(self, key: str, **kwargs) -> str:
        return t(key, self.config.localization.target_language_code, **kwargs)

    def scan_all_technology_files(self) -> None:
        self._ingestion_pipeline.scan_all_technology_files()

    def build_technology_tree_relationships(self) -> None:
        self._relations_builder.build_technology_tree_relationships()

    def scan_all_tech_descriptions(self) -> None:
        self._ingestion_pipeline.scan_all_tech_descriptions()

    def _precompute_overlong_trees(self) -> None:
        self._relations_builder.precompute_overlong_trees()

    def report_circular_dependencies(self) -> None:
        self._cycle_detector.report_circular_dependencies()

    def display_generation_statistics(self) -> None:
        self._stats_reporter.display_generation_statistics()

    def _set_event_sink(self, event_sink: EventSink | None) -> None:
        sink = event_sink if event_sink is not None else StdoutEventSink()
        self._event_sink = sink
        self._ingestion_pipeline.set_event_sink(sink)
        self._cycle_detector.set_event_sink(sink)
        self._output_writer.set_event_sink(sink)
        self._stats_reporter.set_event_sink(sink)

    def _set_cancel_event(self, cancel_event: Event | None) -> None:
        self._cancel_event = cancel_event
        self._ingestion_pipeline.set_cancel_event(cancel_event)
        self._output_writer.set_cancel_event(cancel_event)

    def _emit_event(
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

    def _emit_overlong_tree_roots(self) -> None:
        T = self.config.display.max_display_nodes
        if T <= 0:
            return
        roots = sorted(self.overlong_tech_ids)
        if not roots:
            return
        limit = self.config.diagnostics.overlong_tree_roots_log_limit
        self._emit_event(
            StageId.RENDER,
            EventKind.LOG,
            self._l("overbreadth_list_header"),
        )
        for idx, tid in enumerate(roots):
            if limit > 0 and idx >= limit:
                remaining = len(roots) - limit
                self._emit_event(
                    StageId.RENDER,
                    EventKind.LOG,
                    self._l("overbreadth_truncated", remaining=remaining),
                )
                break
            tech = self.all_technologies.get(tid)
            child_cnt = len(tech.unlocked_tech_ids) if tech else 0
            self._emit_event(
                StageId.RENDER,
                EventKind.LOG,
                self._l(
                    "overbreadth_entry",
                    tech_id=tid,
                    child_count=child_cnt,
                    threshold=T,
                ),
            )

    def _set_empire_profile(self, profile: EmpireProfile) -> None:
        self._output_writer.empire_profile = profile

    def _require_settings_snapshot(
        self, settings: Settings | RunSettingsSnapshot | None
    ) -> RunSettingsSnapshot:
        return require_settings_snapshot(settings)

    def _apply_settings_snapshot(self, settings: RunSettingsSnapshot) -> None:
        self._settings_snapshot = require_settings_snapshot(settings)
        self.config = self._settings_snapshot.generator_config
        self._ingestion_pipeline.apply_config(self.config)
        self._relations_builder.display_config = self.config.display
        self._tree_renderer.display_config = self.config.display
        self._output_writer.config = self.config
        self._stats_reporter.config = self.config

    def _build_generate_localization_use_case(self) -> GenerateLocalizationUseCase:
        return GenerateLocalizationUseCase(
            localize=self._l,
            event_sink=self._event_sink,
            steps=GenerationSteps(
                require_save_path=self._require_save_path,
                set_empire_profile=self._set_empire_profile,
                scan_all_technology_files=self.scan_all_technology_files,
                build_technology_tree_relationships=self.build_technology_tree_relationships,
                scan_all_tech_descriptions=self.scan_all_tech_descriptions,
                precompute_overlong_trees=self._precompute_overlong_trees,
                report_circular_dependencies=self.report_circular_dependencies,
                display_generation_statistics=self.display_generation_statistics,
                generate_all_yml_files=self.generate_all_yml_files,
                require_settings=self._require_settings_snapshot,
                apply_settings_snapshot=self._apply_settings_snapshot,
            ),
        )

    def generate_tech_tree_content(
        self,
        tech_id: str,
        lang_code: str = "simp_chinese",
        display_overrides: dict[str, str] | None = None,
        allowed_tech_ids: set[str] | None = None,
    ) -> str:
        return self._tree_renderer.generate_tech_tree_content(
            tech_id,
            lang_code,
            display_overrides,
            allowed_tech_ids,
        )

    def generate_all_yml_files(self):
        return self._output_writer.generate_all_yml_files()

    def _require_save_path(self, save_path: Path | str | None) -> Path:
        if save_path is None:
            raise ValueError("save_path is required and cannot be empty")

        save_path_text = str(save_path).strip()
        if not save_path_text:
            raise ValueError("save_path is required and cannot be empty")

        return Path(save_path_text)

    def run_generation_process(
        self,
        save_path: Path | str | None = None,
        *,
        country_id: int | None = None,
        event_sink: EventSink | None = None,
        cancel_event: Event | None = None,
    ) -> RunOutcome:
        return self.run_generation_process_with_settings(
            save_path=save_path,
            settings=self._settings_snapshot,
            country_id=country_id,
            event_sink=event_sink,
            cancel_event=cancel_event,
        )

    def run_generation_process_with_settings(
        self,
        save_path: Path | str | None = None,
        *,
        settings: Settings | RunSettingsSnapshot | None,
        country_id: int | None = None,
        event_sink: EventSink | None = None,
        cancel_event: Event | None = None,
    ) -> RunOutcome:
        self._set_event_sink(event_sink)
        self._set_cancel_event(cancel_event)
        use_case = self._build_generate_localization_use_case()
        try:
            return use_case.run_with_settings(
                settings=settings,
                save_path=save_path,
                country_id=country_id,
                cancel_event=cancel_event,
            )
        finally:
            self._set_cancel_event(None)
