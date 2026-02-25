from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from collections.abc import Callable, Mapping, Sequence

from config import GeneratorConfig
from dtt_core.eligibility import EligibilityReport, build_allowed_tech_ids_for_empire
from dtt_core.events import (
    EventEmitterMixin,
    EventKind,
    EventSink,
    StageId,
)
from dtt_core.swap_resolver import (
    SwapResolutionReport,
    resolve_display_overrides_for_profile,
)
from dtt_core.tech_merge import MergedTechDefinition
from dtt_core.trigger_evaluator import EmpireProfile, TriggerEvaluator
from localization import LOCALIZATION_STRINGS
from models import Technology


@dataclass(frozen=True)
class ArtifactWriteFailure:
    path: Path
    error_type: str
    error: str


@dataclass
class ArtifactWriteSummary:
    written: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[ArtifactWriteFailure] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return bool(self.failed)


@dataclass(frozen=True)
class OutputWriteResult:
    eligibility_report: EligibilityReport
    artifact_summary: ArtifactWriteSummary


@dataclass(frozen=True)
class OutputPathFailure:
    raw_target: str
    error: Exception


def plan_output_file_paths(
    *,
    localisation_root: Path,
    yml_targets: Sequence[object],
    lang_code: str,
    filename: str,
) -> tuple[list[Path], list[OutputPathFailure]]:
    candidates: list[Path] = []
    failures: list[OutputPathFailure] = []

    for template in yml_targets:
        raw = "" if template is None else str(template).strip()
        try:
            formatted = raw.format(lang_code=lang_code)
        except Exception as exc:
            failures.append(OutputPathFailure(raw_target=raw, error=exc))
            continue

        rel = Path(formatted) if formatted else Path("")
        if rel.is_absolute() or ".." in rel.parts:
            failures.append(
                OutputPathFailure(
                    raw_target=raw,
                    error=ValueError(
                        "output target must be relative and cannot contain '..': "
                        f"{raw!r}"
                    ),
                )
            )
            continue

        candidates.append(localisation_root / rel / filename)

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        unique.append(path)
        seen.add(path)
    return unique, failures


@dataclass(frozen=True)
class PlannedTextFile:
    path: Path
    content: str
    encoding: str


@dataclass(frozen=True)
class OutputPlan:
    planned_files: tuple[PlannedTextFile, ...]
    eligibility_report: EligibilityReport
    swap_resolution_report: SwapResolutionReport
    missing_description_count: int
    target_failures: tuple[OutputPathFailure, ...]
    lang_code: str


class _OutputPlanBuilder:
    def __init__(
        self,
        *,
        all_technologies: Mapping[str, Technology],
        tech_descriptions: Mapping[str, Mapping[str, str]],
        config: GeneratorConfig,
        generate_tech_tree_content: Callable[..., str],
        merged_tech_definitions: Mapping[str, MergedTechDefinition],
        trigger_evaluator: TriggerEvaluator,
        empire_profile: EmpireProfile,
        localisation_root: Path,
        yml_targets: Sequence[object],
        yml_encoding: str,
        report_encoding: str,
    ) -> None:
        self._all_technologies = all_technologies
        self._tech_descriptions = tech_descriptions
        self._config = config
        self._generate_tech_tree_content = generate_tech_tree_content
        self._merged_tech_definitions = merged_tech_definitions
        self._trigger_evaluator = trigger_evaluator
        self._empire_profile = empire_profile
        self._localisation_root = localisation_root
        self._yml_targets = yml_targets
        self._yml_encoding = yml_encoding
        self._report_encoding = report_encoding

    def build_plan(self) -> OutputPlan:
        allowed_tech_ids, eligibility_report = self._build_allowed_tech_ids()
        display_overrides, swap_resolution_report = self._build_display_overrides()

        planned_files: list[PlannedTextFile] = []
        target_failures: list[OutputPathFailure] = []

        lang_code = self._config.localization.target_language_code
        lang_key = self._config.target_lang_key

        main_files, main_failures = self._plan_main_tree_files(
            lang_code=lang_code,
            lang_key=lang_key,
            allowed_tech_ids=allowed_tech_ids,
            display_overrides=display_overrides,
        )
        planned_files.extend(main_files)
        target_failures.extend(main_failures)

        replaced_files, replaced_failures, missing_description_count = (
            self._plan_replaced_description_files(
                lang_code=lang_code,
                lang_key=lang_key,
                allowed_tech_ids=allowed_tech_ids,
                display_overrides=display_overrides,
            )
        )
        planned_files.extend(replaced_files)
        target_failures.extend(replaced_failures)

        report_file = self._plan_save_report_file(
            eligibility_report=eligibility_report,
            swap_resolution_report=swap_resolution_report,
        )
        planned_files.append(report_file)

        return OutputPlan(
            planned_files=tuple(planned_files),
            eligibility_report=eligibility_report,
            swap_resolution_report=swap_resolution_report,
            missing_description_count=missing_description_count,
            target_failures=tuple(target_failures),
            lang_code=lang_code,
        )

    def _build_allowed_tech_ids(self) -> tuple[set[str], EligibilityReport]:
        return build_allowed_tech_ids_for_empire(
            self._all_technologies,
            self._empire_profile,
            self._merged_tech_definitions,
            evaluator=self._trigger_evaluator,
            sample_size=self._config.output.eligibility_sample_size,
            unknown_warning_threshold=self._config.output.eligibility_unknown_warning_threshold,
        )

    def _build_display_overrides(self) -> tuple[dict[str, str], SwapResolutionReport]:
        return resolve_display_overrides_for_profile(
            self._merged_tech_definitions,
            self._empire_profile,
            evaluator=self._trigger_evaluator,
        )

    def _active_display_id(
        self,
        base_tech_id: str,
        display_overrides: Mapping[str, str],
    ) -> str:
        return display_overrides.get(base_tech_id, base_tech_id)

    def _lookup_description(self, tech_id: str, lang_code: str) -> str:
        if tech_id not in self._tech_descriptions:
            return ""
        return str(self._tech_descriptions[tech_id].get(lang_code, ""))

    def _plan_yml_file_targets(
        self,
        *,
        lang_code: str,
        filename: str,
    ) -> tuple[list[Path], list[OutputPathFailure]]:
        return plan_output_file_paths(
            localisation_root=self._localisation_root,
            yml_targets=self._yml_targets,
            lang_code=lang_code,
            filename=filename,
        )

    def _plan_main_tree_files(
        self,
        *,
        lang_code: str,
        lang_key: str,
        allowed_tech_ids: set[str],
        display_overrides: Mapping[str, str],
    ) -> tuple[list[PlannedTextFile], list[OutputPathFailure]]:
        file_paths, failures = self._plan_yml_file_targets(
            lang_code=lang_code,
            filename=f"zztechtreemain_l_{lang_code}.yml",
        )
        lang_config = LOCALIZATION_STRINGS.get(
            lang_code, LOCALIZATION_STRINGS["english"]
        )
        lines = [
            f"{lang_key}:",
            f' technology_tree_title:0 "{lang_config["title"]}"',
            f' tech_tree_max_level:0 "{lang_config["top_level"]}"',
        ]

        for tech_id in sorted(allowed_tech_ids):
            tree_content = self._generate_tech_tree_content(
                tech_id,
                lang_code,
                display_overrides=display_overrides,
                allowed_tech_ids=allowed_tech_ids,
            )
            if not tree_content:
                continue

            active_id = self._active_display_id(tech_id, display_overrides)
            lines.append(f' {active_id}_techtree:0 "{tree_content}"')

        content = "\n".join(lines)
        planned = [
            PlannedTextFile(
                path=path,
                content=content,
                encoding=self._yml_encoding,
            )
            for path in file_paths
        ]
        return planned, failures

    def _plan_replaced_description_files(
        self,
        *,
        lang_code: str,
        lang_key: str,
        allowed_tech_ids: set[str],
        display_overrides: Mapping[str, str],
    ) -> tuple[list[PlannedTextFile], list[OutputPathFailure], int]:
        file_paths, failures = self._plan_yml_file_targets(
            lang_code=lang_code,
            filename=f"zztechtreereplaced_l_{lang_code}.yml",
        )
        lines = [f"{lang_key}:"]
        missing_descriptions: list[str] = []
        lang_config = LOCALIZATION_STRINGS.get(
            lang_code, LOCALIZATION_STRINGS["english"]
        )

        for tech_id in sorted(allowed_tech_ids):
            tech = self._all_technologies.get(tech_id)
            if tech is None:
                continue

            active_id = self._active_display_id(tech_id, display_overrides)
            tech_desc = self._lookup_description(active_id, lang_code)
            if not tech_desc and active_id != tech_id:
                tech_desc = self._lookup_description(tech_id, lang_code)
            if not tech_desc:
                missing_descriptions.append(active_id)

            tier_text = f"{lang_config['tier_label']}{tech.tier_level}"

            tree_content = f"${active_id}_techtree$"
            if tech_desc:
                full_desc = f"{tech_desc}({tier_text}){tree_content}"
            else:
                full_desc = f"({tier_text}){tree_content}"
            lines.append(f' {active_id}_desc:0 "{full_desc}"')

        content = "\n".join(lines)
        planned = [
            PlannedTextFile(
                path=path,
                content=content,
                encoding=self._yml_encoding,
            )
            for path in file_paths
        ]
        return planned, failures, len(missing_descriptions)

    def _sorted_unknown_predicate_frequency(
        self,
        eligibility_report: EligibilityReport,
    ):
        return sorted(
            eligibility_report.unknown_predicate_frequency.items(),
            key=lambda item: (-item[1].count, item[0]),
        )

    def _plan_save_report_file(
        self,
        *,
        eligibility_report: EligibilityReport,
        swap_resolution_report: SwapResolutionReport,
    ) -> PlannedTextFile:
        report_path = self._localisation_root / "dtt-save-report.txt"
        lines = [
            "dtt-save-report",
            f"profile_mode: {self._empire_profile.mode}",
            f"profile_name: {self._empire_profile.name}",
            "",
            "eligibility_counts:",
            f"excluded_by_false: {eligibility_report.excluded_by_false_count}",
            f"excluded_by_unknown: {eligibility_report.excluded_by_unknown_count}",
            f"excluded_by_prereq: {eligibility_report.excluded_by_prereq_count}",
            "",
            "unknown_predicate_frequency_top:",
        ]

        unknown_predicate_frequency = self._sorted_unknown_predicate_frequency(
            eligibility_report
        )
        if not unknown_predicate_frequency:
            lines.append("none")
        else:
            for predicate, frequency in unknown_predicate_frequency:
                example_tech_ids = ", ".join(frequency.example_tech_ids) or "-"
                lines.append(
                    f"- {predicate}: count={frequency.count}; "
                    f"examples={example_tech_ids}"
                )

        lines.extend(["", "swap_ambiguities:"])
        lines.append(f"count: {len(swap_resolution_report.ambiguities)}")
        if not swap_resolution_report.ambiguities:
            lines.append("none")
        else:
            for tech_id in sorted(swap_resolution_report.ambiguities):
                ambiguity = swap_resolution_report.ambiguities[tech_id]
                unknown_predicates = ", ".join(ambiguity.unknown_predicates) or "-"
                lines.append(
                    f"- tech_id={tech_id}; swap_index={ambiguity.swap_index}; "
                    f"unknown_preds={unknown_predicates}"
                )

        report_content = "\n".join(lines) + "\n"
        return PlannedTextFile(
            path=report_path,
            content=report_content,
            encoding=self._report_encoding,
        )


class _OutputPlanWriter:
    def __init__(
        self,
        *,
        config: GeneratorConfig,
        localize: Callable[..., str],
        emit: Callable[..., None],
        artifact_summary: ArtifactWriteSummary,
        cancel_event: Event | None,
    ) -> None:
        self._config = config
        self._localize = localize
        self._emit = emit
        self._artifact_summary = artifact_summary
        self._cancel_event = cancel_event

    def write_plan(self, plan: OutputPlan) -> None:
        for planned in plan.planned_files:
            if self._is_cancelled():
                return
            self._write_text_file(planned.path, planned.content, encoding=planned.encoding)

    def _is_cancelled(self) -> bool:
        return self._cancel_event is not None and self._cancel_event.is_set()

    def _write_text_file(self, file_path: Path, content: str, *, encoding: str) -> None:
        on_write_error = self._config.output.on_write_error
        on_existing_file = self._config.output.on_existing_file

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if on_existing_file != "overwrite" and file_path.exists():
                if on_existing_file == "skip":
                    self._artifact_summary.skipped.append(file_path)
                    return
                if on_existing_file == "fail":
                    raise FileExistsError(
                        f"refusing to overwrite existing file: {file_path}"
                    )

            with file_path.open("w", encoding=encoding, newline="\n") as handle:
                handle.write(content)
            self._artifact_summary.written.append(file_path)
            self._emit(
                EventKind.ARTIFACT,
                "",
                artifact_path=str(file_path),
            )
        except OSError as exc:
            self._artifact_summary.failed.append(
                ArtifactWriteFailure(
                    path=file_path,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
            )
            failure_kind = (
                EventKind.ERROR if on_write_error == "fail_fast" else EventKind.WARNING
            )
            self._emit(
                failure_kind,
                self._localize("warn_write_file_failed", file=file_path, error=exc),
                details=(
                    ("file", str(file_path)),
                    ("error_type", type(exc).__name__),
                    ("error", str(exc)),
                ),
            )
            if on_write_error == "fail_fast":
                raise


class OutputWriter(EventEmitterMixin):
    _STAGE_ID = StageId.WRITE_OUTPUT

    def __init__(
        self,
        *,
        all_technologies: dict[str, Technology],
        tech_descriptions: dict[str, dict[str, str]],
        config: GeneratorConfig,
        localize: Callable[..., str],
        generate_tech_tree_content: Callable[..., str],
        merged_tech_definitions: Mapping[str, MergedTechDefinition] | None = None,
        trigger_evaluator: TriggerEvaluator | None = None,
        empire_profile: EmpireProfile | None = None,
        application_root: Path | str | None = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self.all_technologies = all_technologies
        self.tech_descriptions = tech_descriptions
        self.config = config
        self._localize = localize
        self.generate_tech_tree_content = generate_tech_tree_content
        # 引用 ingestion 每次运行时变更的共享映射。
        # 在此处复制会默默断开存档驱动的资格/交换逻辑。
        self.merged_tech_definitions = (
            merged_tech_definitions if merged_tech_definitions is not None else {}
        )
        self.trigger_evaluator = (
            trigger_evaluator if trigger_evaluator is not None else TriggerEvaluator()
        )
        self.empire_profile = empire_profile or EmpireProfile.auto("regular")
        self.application_root = (
            Path(application_root) if application_root is not None else None
        )
        self._init_event_sink(event_sink)
        self._cancel_event: Event | None = None
        self.eligibility_report = EligibilityReport()
        self.swap_resolution_report = SwapResolutionReport()
        self.artifact_summary = ArtifactWriteSummary()

    def _localisation_root(self) -> Path:
        if self.application_root is None:
            return Path("localisation")
        return self.application_root / "localisation"

    def set_cancel_event(self, cancel_event: Event | None) -> None:
        self._cancel_event = cancel_event

    def _is_cancelled(self) -> bool:
        return self._cancel_event is not None and self._cancel_event.is_set()

    def generate_all_yml_files(self) -> OutputWriteResult:
        self.artifact_summary = ArtifactWriteSummary()
        output_config = self.config.output

        builder = _OutputPlanBuilder(
            all_technologies=self.all_technologies,
            tech_descriptions=self.tech_descriptions,
            config=self.config,
            generate_tech_tree_content=self.generate_tech_tree_content,
            merged_tech_definitions=self.merged_tech_definitions,
            trigger_evaluator=self.trigger_evaluator,
            empire_profile=self.empire_profile,
            localisation_root=self._localisation_root(),
            yml_targets=output_config.yml_targets,
            yml_encoding=output_config.yml_encoding,
            report_encoding=output_config.report_encoding,
        )
        plan = builder.build_plan()
        self.eligibility_report = plan.eligibility_report
        self.swap_resolution_report = plan.swap_resolution_report

        for failure in plan.target_failures:
            self._emit(
                EventKind.WARNING,
                self._localize(
                    "warn_write_file_failed",
                    file=failure.raw_target or "<empty target>",
                    error=failure.error,
                ),
            )
            if output_config.on_write_error == "fail_fast":
                raise failure.error

        if plan.missing_description_count > 0:
            self._emit(
                EventKind.WARNING,
                self._localize(
                    "warn_missing_descriptions",
                    lang=plan.lang_code,
                    count=plan.missing_description_count,
                ),
            )

        writer = _OutputPlanWriter(
            config=self.config,
            localize=self._localize,
            emit=self._emit,
            artifact_summary=self.artifact_summary,
            cancel_event=self._cancel_event,
        )
        writer.write_plan(plan)
        return OutputWriteResult(
            eligibility_report=self.eligibility_report,
            artifact_summary=self.artifact_summary,
        )
