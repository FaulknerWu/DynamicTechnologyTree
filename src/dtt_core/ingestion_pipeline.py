from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

from config import GeneratorConfig
from dtt_core.clausewitz_parser import parse
from dtt_core.events import (
    EventKind,
    EventSink,
    GenerationEvent,
    NullEventSink,
    StageId,
)
from dtt_core.file_decode import format_decode_warning, read_text_with_diagnostics
from dtt_core.file_indexer import FileIndexer
from dtt_core.load_order_resolver import (
    LoadOrderResolver,
    ResolvedModEntry,
)
from dtt_core.localisation_parser import (
    merge_localisation_file_stream,
    parse_localisation_file,
)
from dtt_core.mod_descriptor_loader import load_descriptor
from dtt_core.source_manifest import FileRef, Source, SourceManifest
from dtt_core.tech_extractor import (
    TechDefinitionFragment,
    TechExtractor,
)
from dtt_core.tech_merge import MergedTechDefinition, merge_all_fragments
from models import Technology


_MAX_EXAMPLES = 10
_WORKSHOP_ID_RE = re.compile(r"ugc_(\d+)")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class IngestionReport:
    tech_files_total: int = 0
    tech_files_with_decode_warning: int = 0
    tech_files_failed: int = 0
    tech_files_with_parse_diagnostics: int = 0
    tech_parse_diagnostic_count: int = 0
    tech_override_count: int = 0
    localization_files_total: int = 0
    localization_files_with_diagnostics: int = 0
    localization_diagnostic_count: int = 0
    localization_override_count: int = 0
    examples: List[Tuple[str, str]] = field(default_factory=list)


class IntegratedIngestionPipeline:
    _VANILLA_SOURCE_ID = "vanilla"

    def __init__(
        self,
        *,
        config: GeneratorConfig,
        localize,
        all_technologies: Dict[str, Technology],
        base_game_tech_ids: Set[str],
        tech_descriptions: Dict[str, Dict[str, str]],
        merged_tech_definitions: Dict[str, MergedTechDefinition],
        event_sink: EventSink | None = None,
    ) -> None:
        self.config = config
        self._l = localize
        self.all_technologies = all_technologies
        self.base_game_tech_ids = base_game_tech_ids
        self.tech_descriptions = tech_descriptions
        self.merged_tech_definitions = merged_tech_definitions
        self._event_sink: EventSink = (
            event_sink if event_sink is not None else NullEventSink()
        )
        self._swap_variant_ids: Set[str] = set()

        self._resolver = LoadOrderResolver()
        self._indexer = FileIndexer()
        self._extractor = TechExtractor()

        self._manifest: Optional[SourceManifest] = None
        self._report = IngestionReport()

    @property
    def report(self) -> IngestionReport:
        return self._report

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink if event_sink is not None else NullEventSink()

    def _emit(self, stage_id: StageId, kind: EventKind, message: str) -> None:
        self._event_sink.emit(
            GenerationEvent(
                stage_id=stage_id,
                kind=kind,
                message=message,
            )
        )

    def scan_all_technology_files(self) -> None:
        self.all_technologies.clear()
        self.base_game_tech_ids.clear()
        self._swap_variant_ids.clear()
        self.merged_tech_definitions.clear()

        self._report = IngestionReport()
        manifest = self._build_manifest()
        tech_files = self._indexer.index_technology_files(manifest)
        self._report.tech_files_total = len(tech_files)

        fragments: List[TechDefinitionFragment] = []
        for file_ref in tech_files:
            self._consume_technology_file(file_ref, fragments)

        merged = merge_all_fragments(fragments)
        override_count = self._count_tech_overrides(fragments)
        self._report.tech_override_count = override_count
        self.merged_tech_definitions.update(merged)

        for tech_id in sorted(merged):
            tech = self._create_runtime_technology(merged[tech_id])
            self.all_technologies[tech_id] = tech

        self._collect_swap_variant_ids(merged)

        self._print_tech_report()

    def scan_all_tech_descriptions(self) -> None:
        self.tech_descriptions.clear()
        self._swap_variant_ids.clear()
        self._collect_swap_variant_ids(self.merged_tech_definitions)

        manifest = self._build_manifest()
        all_loc_files = self._indexer.index_localisation_files(manifest)
        target_lang = self.config.localization.target_language_code
        selected_loc_files = [
            file_ref
            for file_ref in all_loc_files
            if self._matches_language(file_ref, target_lang)
        ]

        self._report.localization_files_total = len(selected_loc_files)

        merge_result = merge_localisation_file_stream(
            selected_loc_files,
            expected_language=target_lang,
        )

        diagnostics = merge_result.diagnostics
        self._report.localization_diagnostic_count = len(diagnostics)
        if diagnostics:
            failed_paths = {diag.path for diag in diagnostics}
            self._report.localization_files_with_diagnostics = len(failed_paths)
            for diag in diagnostics[:_MAX_EXAMPLES]:
                self._report.examples.append((str(diag.path), diag.message))

        self._report.localization_override_count = self._count_localization_overrides(
            merge_result.ordered_files,
            target_lang,
        )

        for desc_key, description in merge_result.entries.items():
            self._consume_localization_entry(desc_key, description, target_lang)

        self._print_localization_report()

    def _build_manifest(self) -> SourceManifest:
        resolution = self._resolver.resolve_enabled_mods(
            self.config.paths.launcher_db_path,
        )

        sources: List[Source] = [
            Source(
                kind="vanilla",
                id=self._VANILLA_SOURCE_ID,
                display_name="Vanilla",
                root_path=Path(self.config.paths.base_game_path),
                load_index=0,
                provenance="base-game",
            )
        ]

        seen_roots: Set[str] = set()
        missing_mod_dirs = 0
        for entry in resolution.entries:
            root_path = self._resolve_mod_root(entry)
            if root_path is None:
                missing_mod_dirs += 1
                continue

            root_key = str(root_path.resolve())
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)

            replace_paths = self._load_replace_paths(entry, root_path)
            load_index = len(sources)
            source_id = f"mod:{load_index}:{root_path.name}"
            sources.append(
                Source(
                    kind="mod",
                    id=source_id,
                    display_name=root_path.name,
                    root_path=root_path,
                    load_index=load_index,
                    replace_paths=replace_paths,
                    provenance=entry.raw_entry,
                )
            )

        self._manifest = SourceManifest(tuple(sources))

        if missing_mod_dirs:
            self._emit(
                StageId.LOAD_ORDER,
                EventKind.WARNING,
                self._l("msg_missing_mod_dirs", count=missing_mod_dirs),
            )
        self._emit(
            StageId.LOAD_ORDER,
            EventKind.LOG,
            self._l("msg_enabled_mods_count", count=max(0, len(sources) - 1)),
        )

        for warning in resolution.warnings:
            self._emit(
                StageId.LOAD_ORDER,
                EventKind.WARNING,
                f"Warning: {warning}",
            )

        return self._manifest

    def _consume_technology_file(
        self,
        file_ref: FileRef,
        fragments: List[TechDefinitionFragment],
    ) -> None:
        file_path = file_ref.absolute_path
        try:
            decoded = read_text_with_diagnostics(file_path)
        except OSError as exc:
            self._report.tech_files_failed += 1
            self._record_example(str(file_path), f"{type(exc).__name__}: {exc}")
            return

        if decoded.diagnostics.has_warning:
            self._report.tech_files_with_decode_warning += 1
            self._record_example(
                str(file_path), format_decode_warning(decoded.diagnostics)
            )

        parsed = parse(decoded.text, path=str(file_path))
        if parsed.diagnostics:
            self._report.tech_files_with_parse_diagnostics += 1
            self._report.tech_parse_diagnostic_count += len(parsed.diagnostics)
            self._record_example(str(file_path), parsed.diagnostics[0].format())

        extracted = self._extractor.extract_from_root(
            parsed.root, source=str(file_path)
        )
        if file_ref.source_id == self._VANILLA_SOURCE_ID:
            self.base_game_tech_ids.update(frag.tech_id for frag in extracted)
        fragments.extend(extracted)

    def _create_runtime_technology(self, merged: MergedTechDefinition) -> Technology:
        tech = Technology(merged.tech_id)
        if merged.area is not None:
            tech.research_area = merged.area
        if merged.tier is not None:
            tech.tier_level = merged.tier
        tech.prerequisite_tech_ids = list(merged.prerequisites)

        if merged.levels == -1:
            tech.is_repeatable_tech = True
        if merged.is_repeatable is not None:
            tech.is_repeatable_tech = tech.is_repeatable_tech or merged.is_repeatable
        if merged.is_dangerous is not None:
            tech.is_dangerous_tech = tech.is_dangerous_tech or merged.is_dangerous
        return tech

    def _collect_swap_variant_ids(
        self,
        merged_definitions: Dict[str, MergedTechDefinition],
    ) -> None:
        for tech_id in sorted(merged_definitions):
            merged = merged_definitions[tech_id]
            for swap in merged.technology_swaps:
                variant_id = (swap.name or "").strip()
                if variant_id:
                    self._swap_variant_ids.add(variant_id)

    def _consume_localization_entry(
        self,
        desc_key: str,
        description: str,
        lang_code: str,
    ) -> None:
        if not desc_key.endswith("_desc"):
            return

        target_tech_id = desc_key[: -len("_desc")]
        if not target_tech_id:
            return

        if (
            target_tech_id not in self.all_technologies
            and target_tech_id not in self._swap_variant_ids
        ):
            return

        cleaned = self._clean_description_text(description)
        self.tech_descriptions.setdefault(target_tech_id, {})[lang_code] = cleaned

    def _count_tech_overrides(self, fragments: List[TechDefinitionFragment]) -> int:
        grouped: dict[str, int] = defaultdict(int)
        for fragment in fragments:
            grouped[fragment.tech_id] += 1
        return sum(max(0, count - 1) for count in grouped.values())

    def _count_localization_overrides(
        self,
        ordered_files: tuple[Path, ...],
        target_lang: str,
    ) -> int:
        seen_keys: Set[str] = set()
        overrides = 0
        for file_path in ordered_files:
            try:
                parsed = parse_localisation_file(
                    file_path, expected_language=target_lang
                )
            except OSError:
                continue
            for key in parsed.entries:
                if key in seen_keys:
                    overrides += 1
                else:
                    seen_keys.add(key)
        return overrides

    def _matches_language(self, file_ref: FileRef, language_code: str) -> bool:
        needle = f"l_{language_code}".casefold()
        return needle in file_ref.relative_path.casefold()

    def _record_example(self, path: str, message: str) -> None:
        if len(self._report.examples) >= _MAX_EXAMPLES:
            return
        self._report.examples.append((path, message))

    def _print_tech_report(self) -> None:
        total = self._report.tech_files_total
        failed = (
            self._report.tech_files_failed
            + self._report.tech_files_with_parse_diagnostics
        )
        shown = min(len(self._report.examples), _MAX_EXAMPLES)
        suppressed = max(failed - shown, 0)
        ok = max(total - failed, 0)

        self._emit(
            StageId.INGEST_TECH,
            EventKind.WARNING,
            self._l(
                "warn_tech_parse_summary",
                total=total,
                ok=ok,
                failed=failed,
                shown=shown,
                suppressed=suppressed,
            ),
        )
        for path, error in self._report.examples[:_MAX_EXAMPLES]:
            self._emit(
                StageId.INGEST_TECH,
                EventKind.WARNING,
                self._l("warn_tech_parse_failure_example", path=path, error=error),
            )
        self._emit(
            StageId.INGEST_TECH,
            EventKind.LOG,
            f"Notice: tech overrides applied: {self._report.tech_override_count}",
        )

    def _print_localization_report(self) -> None:
        total = self._report.localization_files_total
        failed = self._report.localization_files_with_diagnostics
        shown = min(failed, _MAX_EXAMPLES)
        suppressed = max(failed - shown, 0)
        ok = max(total - failed, 0)

        self._emit(
            StageId.INGEST_L10N,
            EventKind.WARNING,
            self._l(
                "warn_loc_parse_summary",
                total=total,
                ok=ok,
                failed=failed,
                shown=shown,
                suppressed=suppressed,
            ),
        )
        if failed:
            seen_paths: Set[str] = set()
            for path, error in self._report.examples:
                if path in seen_paths:
                    continue
                self._emit(
                    StageId.INGEST_L10N,
                    EventKind.WARNING,
                    self._l("warn_loc_parse_failure_example", path=path, error=error),
                )
                seen_paths.add(path)
                if len(seen_paths) >= _MAX_EXAMPLES:
                    break
        self._emit(
            StageId.INGEST_L10N,
            EventKind.LOG,
            "Notice: localisation overrides applied: "
            f"{self._report.localization_override_count}",
        )

    def _resolve_mod_root(self, entry: ResolvedModEntry) -> Optional[Path]:
        for candidate in self._candidate_mod_roots(entry):
            if candidate.is_dir():
                return candidate
        return None

    def _candidate_mod_roots(self, entry: ResolvedModEntry) -> List[Path]:
        workshop_root = Path(self.config.paths.mod_folder_path).expanduser()
        user_data_root = Path(self.config.paths.launcher_db_path).expanduser().parent
        local_mod_root = (
            Path(self.config.paths.local_mod_folder_path).expanduser()
            if self.config.paths.local_mod_folder_path
            else user_data_root / "mod"
        )

        candidates: List[Path] = []

        def add_candidate(path: Path) -> None:
            expanded = path.expanduser()
            if expanded in candidates:
                return
            candidates.append(expanded)

        if entry.dir_path:
            dir_path = Path(entry.dir_path)
            if dir_path.is_absolute():
                add_candidate(dir_path)
            else:
                add_candidate(user_data_root / dir_path)
                add_candidate(local_mod_root / dir_path.name)
                add_candidate(workshop_root / dir_path.name)

        for value in (entry.raw_entry, entry.mod_id, entry.game_registry_id):
            if not value:
                continue
            workshop_id = self._extract_workshop_id(value)
            if workshop_id:
                add_candidate(workshop_root / workshop_id)

        if entry.steam_id and entry.steam_id.isdigit():
            add_candidate(workshop_root / entry.steam_id)

        raw_name = Path(entry.raw_entry).name if entry.raw_entry else ""
        if raw_name.endswith(".mod"):
            mod_stem = Path(raw_name).stem
            add_candidate(local_mod_root / mod_stem)

        if entry.dir_path:
            add_candidate(Path(entry.dir_path))

        return candidates

    def _load_replace_paths(
        self, entry: ResolvedModEntry, root_path: Path
    ) -> tuple[str, ...]:
        for descriptor_path in self._descriptor_candidates(entry, root_path):
            if not descriptor_path.exists():
                continue
            try:
                descriptor = load_descriptor(descriptor_path)
            except Exception as exc:
                self._record_example(
                    str(descriptor_path), f"descriptor read failed: {exc}"
                )
                continue
            for diagnostic in descriptor.parse_diagnostics[:1]:
                self._record_example(str(descriptor_path), diagnostic.format())
            if (
                descriptor.decode_diagnostics is not None
                and descriptor.decode_diagnostics.has_warning
            ):
                self._record_example(
                    str(descriptor_path),
                    format_decode_warning(descriptor.decode_diagnostics),
                )
            if descriptor.replace_paths:
                return descriptor.replace_paths
        return ()

    def _descriptor_candidates(
        self,
        entry: ResolvedModEntry,
        root_path: Path,
    ) -> tuple[Path, ...]:
        candidates: List[Path] = [root_path / "descriptor.mod"]

        user_data_root = Path(self.config.paths.launcher_db_path).expanduser().parent
        local_mod_root = (
            Path(self.config.paths.local_mod_folder_path).expanduser()
            if self.config.paths.local_mod_folder_path
            else user_data_root / "mod"
        )

        raw_name = Path(entry.raw_entry).name if entry.raw_entry else ""
        if raw_name.endswith(".mod"):
            candidates.append(local_mod_root / raw_name)

        local_descriptor = local_mod_root / f"{root_path.name}.mod"
        candidates.append(local_descriptor)

        deduped: List[Path] = []
        seen: Set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return tuple(deduped)

    def _extract_workshop_id(self, value: str) -> str:
        match = _WORKSHOP_ID_RE.search(value)
        if not match:
            return ""
        return match.group(1)

    def _clean_description_text(self, description: str) -> str:
        normalized = description.replace("\n", " ").replace("\t", " ")
        return _WHITESPACE_RE.sub(" ", normalized).strip()
