from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from collections.abc import Callable, Mapping

from config import (
    DEFAULT_ELIGIBILITY_SAMPLE_SIZE,
    DEFAULT_ELIGIBILITY_UNKNOWN_WARNING_THRESHOLD,
    DEFAULT_YML_OUTPUT_TARGETS,
)
from dtt_core.eligibility import EligibilityReport, build_allowed_tech_ids_for_empire
from dtt_core.events import (
    EventKind,
    EventSink,
    GenerationEvent,
    NullEventSink,
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


class OutputWriter:
    def __init__(
        self,
        *,
        all_technologies: dict[str, Technology],
        tech_descriptions: dict[str, dict[str, str]],
        config,
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
        # Reference the shared mapping that ingestion mutates per run.
        # Copying here silently disconnects save-driven eligibility/swap logic.
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
        self._event_sink: EventSink = (
            event_sink if event_sink is not None else NullEventSink()
        )
        self._cancel_event: Event | None = None
        self.eligibility_report = EligibilityReport()
        self.swap_resolution_report = SwapResolutionReport()
        self.artifact_summary = ArtifactWriteSummary()

    def _localisation_root(self) -> Path:
        if self.application_root is None:
            return Path("localisation")
        return self.application_root / "localisation"

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink if event_sink is not None else NullEventSink()

    def set_cancel_event(self, cancel_event: Event | None) -> None:
        self._cancel_event = cancel_event

    def _is_cancelled(self) -> bool:
        return self._cancel_event is not None and self._cancel_event.is_set()

    def _emit(
        self,
        kind: EventKind,
        message: str,
        *,
        artifact_path: str | None = None,
        details: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._event_sink.emit(
            GenerationEvent(
                stage_id=StageId.WRITE_OUTPUT,
                kind=kind,
                message=message,
                artifact_path=artifact_path,
                details=details,
            )
        )

    def _write_text_file(self, file_path: Path, content: str, *, encoding: str) -> None:
        output = getattr(self.config, "output", None)
        on_write_error = getattr(output, "on_write_error", "warn_and_continue")
        on_existing_file = getattr(output, "on_existing_file", "overwrite")

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if on_existing_file != "overwrite" and file_path.exists():
                if on_existing_file == "skip":
                    self.artifact_summary.skipped.append(file_path)
                    return
                if on_existing_file == "fail":
                    raise FileExistsError(
                        f"refusing to overwrite existing file: {file_path}"
                    )

            with file_path.open("w", encoding=encoding, newline="\n") as handle:
                handle.write(content)
            self.artifact_summary.written.append(file_path)
            self._emit(
                EventKind.ARTIFACT,
                "",
                artifact_path=str(file_path),
            )
        except OSError as e:
            self.artifact_summary.failed.append(
                ArtifactWriteFailure(
                    path=file_path,
                    error_type=type(e).__name__,
                    error=str(e),
                )
            )
            failure_kind = (
                EventKind.ERROR if on_write_error == "fail_fast" else EventKind.WARNING
            )
            self._emit(
                failure_kind,
                self._localize("warn_write_file_failed", file=file_path, error=e),
                details=(
                    ("file", str(file_path)),
                    ("error_type", type(e).__name__),
                    ("error", str(e)),
                ),
            )
            if on_write_error == "fail_fast":
                raise

    def _get_output_file_paths(self, lang_code: str, filename: str):
        base = self._localisation_root()

        output = getattr(self.config, "output", None)
        templates = getattr(output, "yml_targets", DEFAULT_YML_OUTPUT_TARGETS)
        on_write_error = getattr(output, "on_write_error", "warn_and_continue")

        candidates: list[Path] = []
        for template in templates:
            raw = "" if template is None else str(template).strip()
            try:
                formatted = raw.format(lang_code=lang_code)
            except Exception as e:
                self._emit(
                    EventKind.WARNING,
                    self._localize(
                        "warn_write_file_failed",
                        file=raw or "<empty target>",
                        error=e,
                    ),
                )
                if on_write_error == "fail_fast":
                    raise
                continue

            rel = Path(formatted) if formatted else Path("")
            if rel.is_absolute() or ".." in rel.parts:
                error = ValueError(
                    f"output target must be relative and cannot contain '..': {raw!r}"
                )
                self._emit(
                    EventKind.WARNING,
                    self._localize(
                        "warn_write_file_failed",
                        file=raw or "<empty target>",
                        error=error,
                    ),
                )
                if on_write_error == "fail_fast":
                    raise error
                continue

            candidates.append(base / rel / filename)
        unique = []
        seen: set[Path] = set()
        for p in candidates:
            if p not in seen:
                unique.append(p)
                seen.add(p)
        return unique

    def _lookup_description(self, tech_id: str, lang_code: str) -> str:
        if tech_id not in self.tech_descriptions:
            return ""
        return self.tech_descriptions[tech_id].get(lang_code, "")

    def _active_display_id(
        self,
        base_tech_id: str,
        display_overrides: Mapping[str, str],
    ) -> str:
        return display_overrides.get(base_tech_id, base_tech_id)

    def _build_allowed_tech_ids(self) -> set[str]:
        output = getattr(self.config, "output", None)
        sample_size = getattr(
            output,
            "eligibility_sample_size",
            DEFAULT_ELIGIBILITY_SAMPLE_SIZE,
        )
        unknown_warning_threshold = getattr(
            output,
            "eligibility_unknown_warning_threshold",
            DEFAULT_ELIGIBILITY_UNKNOWN_WARNING_THRESHOLD,
        )
        allowed_tech_ids, report = build_allowed_tech_ids_for_empire(
            self.all_technologies,
            self.empire_profile,
            self.merged_tech_definitions,
            evaluator=self.trigger_evaluator,
            sample_size=sample_size,
            unknown_warning_threshold=unknown_warning_threshold,
        )
        self.eligibility_report = report
        return allowed_tech_ids

    def _build_display_overrides(self) -> dict[str, str]:
        display_overrides, report = resolve_display_overrides_for_profile(
            self.merged_tech_definitions,
            self.empire_profile,
            evaluator=self.trigger_evaluator,
        )
        self.swap_resolution_report = report
        return display_overrides

    def _sorted_unknown_predicate_frequency(self):
        return sorted(
            self.eligibility_report.unknown_predicate_frequency.items(),
            key=lambda item: (-item[1].count, item[0]),
        )

    def _write_save_report(self) -> None:
        if self._is_cancelled():
            return
        report_path = self._localisation_root() / "dtt-save-report.txt"
        lines = [
            "dtt-save-report",
            f"profile_mode: {self.empire_profile.mode}",
            f"profile_name: {self.empire_profile.name}",
            "",
            "eligibility_counts:",
            f"excluded_by_false: {self.eligibility_report.excluded_by_false_count}",
            f"excluded_by_unknown: {self.eligibility_report.excluded_by_unknown_count}",
            f"excluded_by_prereq: {self.eligibility_report.excluded_by_prereq_count}",
            "",
            "unknown_predicate_frequency_top:",
        ]

        unknown_predicate_frequency = self._sorted_unknown_predicate_frequency()
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
        lines.append(f"count: {len(self.swap_resolution_report.ambiguities)}")
        if not self.swap_resolution_report.ambiguities:
            lines.append("none")
        else:
            for tech_id in sorted(self.swap_resolution_report.ambiguities):
                ambiguity = self.swap_resolution_report.ambiguities[tech_id]
                unknown_predicates = ", ".join(ambiguity.unknown_predicates) or "-"
                lines.append(
                    f"- tech_id={tech_id}; swap_index={ambiguity.swap_index}; "
                    f"unknown_preds={unknown_predicates}"
                )

        report_content = "\n".join(lines) + "\n"

        output = getattr(self.config, "output", None)
        encoding = getattr(output, "report_encoding", "utf-8")
        self._write_text_file(report_path, report_content, encoding=encoding)

    def _generate_localization_files_for_language(self, lang_code: str, lang_key: str):
        allowed_tech_ids = self._build_allowed_tech_ids()
        if self._is_cancelled():
            return
        display_overrides = self._build_display_overrides()
        if self._is_cancelled():
            return
        self._generate_main_tech_tree_file(
            lang_code,
            lang_key,
            allowed_tech_ids,
            display_overrides,
        )
        if self._is_cancelled():
            return
        self._generate_tech_description_replacement_file(
            lang_code,
            lang_key,
            allowed_tech_ids,
            display_overrides,
        )
        if self._is_cancelled():
            return
        self._write_save_report()

    def _generate_main_tech_tree_file(
        self,
        lang_code: str,
        lang_key: str,
        allowed_tech_ids: set[str],
        display_overrides: Mapping[str, str],
    ):
        file_paths = self._get_output_file_paths(
            lang_code,
            f"zztechtreemain_l_{lang_code}.yml",
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
            tree_content = self.generate_tech_tree_content(
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
        for file_path in file_paths:
            if self._is_cancelled():
                return
            output = getattr(self.config, "output", None)
            encoding = getattr(output, "yml_encoding", "utf-8-sig")
            self._write_text_file(file_path, content, encoding=encoding)

    def _generate_tech_description_replacement_file(
        self,
        lang_code: str,
        lang_key: str,
        allowed_tech_ids: set[str],
        display_overrides: Mapping[str, str],
    ):
        file_paths = self._get_output_file_paths(
            lang_code,
            f"zztechtreereplaced_l_{lang_code}.yml",
        )
        lines = [f"{lang_key}:"]
        missing_descriptions = []
        lang_config = LOCALIZATION_STRINGS.get(
            lang_code, LOCALIZATION_STRINGS["english"]
        )

        for tech_id in sorted(allowed_tech_ids):
            tech = self.all_technologies.get(tech_id)
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

        if missing_descriptions and len(missing_descriptions) > 0:
            self._emit(
                EventKind.WARNING,
                self._localize(
                    "warn_missing_descriptions",
                    lang=lang_code,
                    count=len(missing_descriptions),
                ),
            )
        content = "\n".join(lines)
        for file_path in file_paths:
            if self._is_cancelled():
                return
            output = getattr(self.config, "output", None)
            encoding = getattr(output, "yml_encoding", "utf-8-sig")
            self._write_text_file(file_path, content, encoding=encoding)

    def generate_all_yml_files(self) -> OutputWriteResult:
        self.artifact_summary = ArtifactWriteSummary()
        output_dir = self._localisation_root()
        output_dir.mkdir(parents=True, exist_ok=True)
        lang_code = self.config.localization.target_language_code
        self._generate_localization_files_for_language(
            lang_code, self.config.target_lang_key
        )
        return OutputWriteResult(
            eligibility_report=self.eligibility_report,
            artifact_summary=self.artifact_summary,
        )
