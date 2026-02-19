from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Set

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


class OutputWriter:
    def __init__(
        self,
        *,
        all_technologies: Dict[str, Technology],
        tech_descriptions: Dict[str, Dict[str, str]],
        config,
        localize: Callable[..., str],
        generate_tech_tree_content: Callable[..., str],
        merged_tech_definitions: Optional[Mapping[str, MergedTechDefinition]] = None,
        trigger_evaluator: Optional[TriggerEvaluator] = None,
        empire_profile: Optional[EmpireProfile] = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self.all_technologies = all_technologies
        self.tech_descriptions = tech_descriptions
        self.config = config
        self._localize = localize
        self.generate_tech_tree_content = generate_tech_tree_content
        self.merged_tech_definitions = dict(merged_tech_definitions or {})
        self.trigger_evaluator = (
            trigger_evaluator if trigger_evaluator is not None else TriggerEvaluator()
        )
        self.empire_profile = empire_profile or EmpireProfile.auto("regular")
        self._event_sink: EventSink = (
            event_sink if event_sink is not None else NullEventSink()
        )
        self.eligibility_report = EligibilityReport()
        self.swap_resolution_report = SwapResolutionReport()

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink if event_sink is not None else NullEventSink()

    def _emit(self, kind: EventKind, message: str) -> None:
        self._event_sink.emit(
            GenerationEvent(
                stage_id=StageId.WRITE_OUTPUT,
                kind=kind,
                message=message,
            )
        )

    def _get_output_file_paths(self, lang_code: str, filename: str):
        base = Path("localisation")
        candidates = [
            base / filename,
            base / lang_code / filename,
            base / "replace" / filename,
            base / lang_code / "replace" / filename,
            base / "zzz_tech_trees" / "replace" / filename,
        ]
        unique = []
        seen: Set[Path] = set()
        for p in candidates:
            if p not in seen:
                unique.append(p)
                seen.add(p)
        for path in unique:
            path.parent.mkdir(parents=True, exist_ok=True)
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

    def _build_allowed_tech_ids(self) -> Set[str]:
        allowed_tech_ids, report = build_allowed_tech_ids_for_empire(
            self.all_technologies,
            self.empire_profile,
            self.merged_tech_definitions,
            evaluator=self.trigger_evaluator,
        )
        self.eligibility_report = report
        return allowed_tech_ids

    def _build_display_overrides(self) -> Dict[str, str]:
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
        report_path = Path("localisation") / "dtt-save-report.txt"
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
        try:
            report_path.write_text(report_content, encoding="utf-8")
        except (OSError, PermissionError) as e:
            self._emit(
                EventKind.WARNING,
                self._localize("warn_write_file_failed", file=report_path, error=e),
            )

    def _generate_localization_files_for_language(self, lang_code: str, lang_key: str):
        allowed_tech_ids = self._build_allowed_tech_ids()
        display_overrides = self._build_display_overrides()
        self._generate_main_tech_tree_file(
            lang_code,
            lang_key,
            allowed_tech_ids,
            display_overrides,
        )
        self._generate_tech_description_replacement_file(
            lang_code,
            lang_key,
            allowed_tech_ids,
            display_overrides,
        )
        self._write_save_report()

    def _generate_main_tech_tree_file(
        self,
        lang_code: str,
        lang_key: str,
        allowed_tech_ids: Set[str],
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
            try:
                file_path.write_text(content, encoding="utf-8-sig")
            except (OSError, PermissionError) as e:
                self._emit(
                    EventKind.WARNING,
                    self._localize("warn_write_file_failed", file=file_path, error=e),
                )

    def _generate_tech_description_replacement_file(
        self,
        lang_code: str,
        lang_key: str,
        allowed_tech_ids: Set[str],
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
            try:
                file_path.write_text(content, encoding="utf-8-sig")
            except (OSError, PermissionError) as e:
                self._emit(
                    EventKind.WARNING,
                    self._localize("warn_write_file_failed", file=file_path, error=e),
                )

    def generate_all_yml_files(self) -> EligibilityReport:
        output_dir = Path("localisation")
        output_dir.mkdir(parents=True, exist_ok=True)
        lang_code = self.config.localization.target_language_code
        self._generate_localization_files_for_language(
            lang_code, self.config.target_lang_key
        )
        return self.eligibility_report
