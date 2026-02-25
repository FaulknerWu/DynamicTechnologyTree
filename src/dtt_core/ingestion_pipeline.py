from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import TypedDict

from config import DecodeFailurePolicy, GeneratorConfig
from dtt_core.clausewitz_parser import parse
from dtt_core.events import (
    EventEmitterMixin,
    EventKind,
    EventSink,
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
)
from dtt_core.mod_descriptor_loader import load_descriptor
from dtt_core.source_manifest import FileRef, Source, SourceManifest
from dtt_core.tech_extractor import (
    TechDefinitionFragment,
    TechExtractor,
)
from dtt_core.tech_merge import MergedTechDefinition, merge_all_fragments
from models import Technology

_WORKSHOP_ID_RE = re.compile(r"ugc_(\d+)")
_WHITESPACE_RE = re.compile(r"\s+")


class _DecodeReadKwargs(TypedDict):
    preferred_encodings: tuple[str, ...]
    fallback_encodings: tuple[str, ...]
    replacement_encoding: str
    on_failure: DecodeFailurePolicy


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
    tech_examples: list[tuple[str, str]] = field(default_factory=list)
    localisation_examples: list[tuple[str, str]] = field(default_factory=list)


class IntegratedIngestionPipeline(EventEmitterMixin):
    _STAGE_ID = StageId.INGEST_TECH
    _VANILLA_SOURCE_ID = "vanilla"

    def __init__(
        self,
        *,
        config: GeneratorConfig,
        localize,
        all_technologies: dict[str, Technology],
        base_game_tech_ids: set[str],
        tech_descriptions: dict[str, dict[str, str]],
        merged_tech_definitions: dict[str, MergedTechDefinition],
        event_sink: EventSink | None = None,
    ) -> None:
        self.config = config
        self._l = localize
        self.all_technologies = all_technologies
        self.base_game_tech_ids = base_game_tech_ids
        self.tech_descriptions = tech_descriptions
        self.merged_tech_definitions = merged_tech_definitions
        self._init_event_sink(event_sink)
        self._cancel_event: Event | None = None
        self._swap_variant_ids: set[str] = set()

        self._resolver = LoadOrderResolver()
        self._indexer = FileIndexer(config=self.config.file_indexing)
        self._extractor = TechExtractor()

        self._manifest: SourceManifest | None = None
        self._report = IngestionReport()
        self._diagnostic_example_limit = max(
            0,
            self.config.ingestion.diagnostic_example_limit,
        )

    @property
    def report(self) -> IngestionReport:
        return self._report

    def apply_config(self, config: GeneratorConfig) -> None:
        """Apply a new settings snapshot.

        The generator can reuse this pipeline across runs. When settings change we
        must refresh any config-dependent helpers and cached manifests.
        """

        self.config = config
        self._indexer = FileIndexer(config=self.config.file_indexing)
        self._diagnostic_example_limit = max(
            0,
            self.config.ingestion.diagnostic_example_limit,
        )
        self._manifest = None

    def set_cancel_event(self, cancel_event: Event | None) -> None:
        self._cancel_event = cancel_event

    def scan_all_technology_files(self) -> None:
        self.all_technologies.clear()
        self.base_game_tech_ids.clear()
        self._swap_variant_ids.clear()
        self.merged_tech_definitions.clear()

        self._report = IngestionReport()

        # New generation run: ensure we don't reuse a manifest built with a
        # previous settings snapshot (paths/load-order).
        self._manifest = None
        manifest = self._build_manifest()
        tech_files = self._indexer.index_technology_files(manifest)
        self._report.tech_files_total = len(tech_files)

        fragments: list[TechDefinitionFragment] = []
        for file_ref in tech_files:
            if self._cancel_event is not None and self._cancel_event.is_set():
                return
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
        self._report.localisation_examples.clear()

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
            cancel_event=self._cancel_event,
            **self._decode_read_kwargs(),
        )

        diagnostics = merge_result.diagnostics
        self._report.localization_diagnostic_count = len(diagnostics)
        if diagnostics:
            failed_paths = {diag.path for diag in diagnostics}
            self._report.localization_files_with_diagnostics = len(failed_paths)
            seen_paths: set[Path] = set()
            for diag in diagnostics:
                if diag.path in seen_paths:
                    continue
                if len(self._report.localisation_examples) >= self._diagnostic_example_limit:
                    break
                seen_paths.add(diag.path)
                self._record_example(self._report.localisation_examples, str(diag.path), diag.message)

        self._report.localization_override_count = merge_result.override_count

        for desc_key, description in merge_result.entries.items():
            self._consume_localization_entry(desc_key, description, target_lang)

        self._print_localization_report()

    def _build_manifest(self) -> SourceManifest:
        if self._manifest is not None:
            return self._manifest

        policy = self.config.load_order.multi_active_playset_selection_policy
        if policy == "latest_created_then_name_then_id":
            resolution = self._resolver.resolve_enabled_mods(
                self.config.paths.launcher_db_path,
            )
        else:
            resolution = self._resolver.resolve_enabled_mods(
                self.config.paths.launcher_db_path,
                multi_active_playset_selection_policy=policy,
            )

        sources: list[Source] = [
            Source(
                kind="vanilla",
                id=self._VANILLA_SOURCE_ID,
                display_name="Vanilla",
                root_path=Path(self.config.paths.base_game_path),
                load_index=0,
                provenance="base-game",
            )
        ]

        seen_roots: set[str] = set()
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

        manifest = SourceManifest(tuple(sources))
        self._manifest = manifest

        if missing_mod_dirs:
            self._emit(
                EventKind.WARNING,
                self._l("msg_missing_mod_dirs", count=missing_mod_dirs),
                stage_id=StageId.LOAD_ORDER,
            )
        self._emit(
            EventKind.LOG,
            self._l("msg_enabled_mods_count", count=max(0, len(sources) - 1)),
            stage_id=StageId.LOAD_ORDER,
        )

        for warning in resolution.warnings:
            self._emit(
                EventKind.WARNING,
                f"Warning: {warning}",
                stage_id=StageId.LOAD_ORDER,
            )

        return manifest

    def _consume_technology_file(
        self,
        file_ref: FileRef,
        fragments: list[TechDefinitionFragment],
    ) -> None:
        file_path = file_ref.absolute_path
        try:
            decoded = read_text_with_diagnostics(
                file_path,
                **self._decode_read_kwargs(),
            )
        except OSError as exc:
            self._report.tech_files_failed += 1
            self._record_example(self._report.tech_examples, str(file_path), f"{type(exc).__name__}: {exc}")
            return

        if decoded.diagnostics.has_warning:
            self._report.tech_files_with_decode_warning += 1

        parsed = parse(decoded.text, path=str(file_path))
        if parsed.diagnostics:
            self._report.tech_files_with_parse_diagnostics += 1
            self._report.tech_parse_diagnostic_count += len(parsed.diagnostics)
            self._record_example(self._report.tech_examples, str(file_path), parsed.diagnostics[0].format())

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

        # Parsed booleans are authoritative; heuristics are fallback behavior.
        if merged.is_repeatable is not None:
            tech.is_repeatable_tech = merged.is_repeatable
        elif merged.levels == -1:
            tech.is_repeatable_tech = True

        if merged.is_dangerous is not None:
            tech.is_dangerous_tech = merged.is_dangerous
        return tech

    def _collect_swap_variant_ids(
        self,
        merged_definitions: dict[str, MergedTechDefinition],
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

    def _count_tech_overrides(self, fragments: list[TechDefinitionFragment]) -> int:
        grouped: dict[str, int] = defaultdict(int)
        for fragment in fragments:
            grouped[fragment.tech_id] += 1
        return sum(max(0, count - 1) for count in grouped.values())

    def _matches_language(self, file_ref: FileRef, language_code: str) -> bool:
        needle = f"l_{language_code}".casefold()
        return needle in file_ref.relative_path.casefold()

    def _record_example(
        self, examples: list[tuple[str, str]], path: str, message: str
    ) -> None:
        """将诊断示例追加到目标列表，受限于最大诊断示例数。"""
        if len(examples) >= self._diagnostic_example_limit:
            return
        examples.append((path, message))

    def _decode_read_kwargs(self) -> _DecodeReadKwargs:
        decode = self.config.decode
        kwargs: _DecodeReadKwargs = {
            "preferred_encodings": decode.preferred_encodings,
            "fallback_encodings": decode.fallback_encodings,
            "replacement_encoding": decode.replacement_encoding,
            "on_failure": decode.on_failure,
        }
        return kwargs

    def _print_parse_report(
        self,
        *,
        stage_id: StageId | None,
        total: int,
        failed: int,
        examples: list[tuple[str, str]],
        summary_key: str,
        example_key: str,
        override_notice: str,
    ) -> None:
        """输出解析报告——tech 和 localization 共用同构逻辑。"""
        shown = min(len(examples), self._diagnostic_example_limit)
        suppressed = max(failed - shown, 0)
        ok = max(total - failed, 0)

        self._emit(
            EventKind.WARNING,
            self._l(
                summary_key,
                total=total,
                ok=ok,
                failed=failed,
                shown=shown,
                suppressed=suppressed,
            ),
            stage_id=stage_id,
        )
        for path, error in examples[: self._diagnostic_example_limit]:
            self._emit(
                EventKind.WARNING,
                self._l(example_key, path=path, error=error),
                stage_id=stage_id,
            )
        self._emit(EventKind.LOG, override_notice, stage_id=stage_id)

    def _print_tech_report(self) -> None:
        self._print_parse_report(
            stage_id=None,
            total=self._report.tech_files_total,
            failed=(
                self._report.tech_files_failed
                + self._report.tech_files_with_parse_diagnostics
            ),
            examples=self._report.tech_examples,
            summary_key="warn_tech_parse_summary",
            example_key="warn_tech_parse_failure_example",
            override_notice=f"Notice: tech overrides applied: {self._report.tech_override_count}",
        )

    def _print_localization_report(self) -> None:
        self._print_parse_report(
            stage_id=StageId.INGEST_L10N,
            total=self._report.localization_files_total,
            failed=self._report.localization_files_with_diagnostics,
            examples=self._report.localisation_examples,
            summary_key="warn_loc_parse_summary",
            example_key="warn_loc_parse_failure_example",
            override_notice=(
                "Notice: localisation overrides applied: "
                f"{self._report.localization_override_count}"
            ),
        )

    def _resolve_mod_root(self, entry: ResolvedModEntry) -> Path | None:
        for candidate in self._candidate_mod_roots(entry):
            if candidate.is_dir():
                return candidate
        return None

    def _resolve_mod_paths(self) -> tuple[Path, Path]:
        """从配置解析 user_data_root 和 local_mod_root，消除重复计算。"""
        user_data_root = Path(self.config.paths.launcher_db_path).expanduser().parent
        local_mod_root = (
            Path(self.config.paths.local_mod_folder_path).expanduser()
            if self.config.paths.local_mod_folder_path
            else user_data_root / "mod"
        )
        return user_data_root, local_mod_root

    def _candidate_mod_roots(self, entry: ResolvedModEntry) -> list[Path]:
        workshop_root = Path(self.config.paths.mod_folder_path).expanduser()
        user_data_root, local_mod_root = self._resolve_mod_paths()

        candidates: list[Path] = []

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
                descriptor = load_descriptor(
                    descriptor_path,
                    **self._decode_read_kwargs(),
                )
            except Exception as exc:
                self._emit(
                    EventKind.WARNING,
                    f"Warning: mod descriptor read failed: {descriptor_path}: {exc}",
                    stage_id=StageId.LOAD_ORDER,
                )
                continue
            for diagnostic in descriptor.parse_diagnostics[:1]:
                self._emit(
                    EventKind.WARNING,
                    f"Warning: mod descriptor diagnostic: {descriptor_path}: {diagnostic.format()}",
                    stage_id=StageId.LOAD_ORDER,
                )
            if (
                descriptor.decode_diagnostics is not None
                and descriptor.decode_diagnostics.has_warning
            ):
                self._emit(
                    EventKind.WARNING,
                    f"Warning: mod descriptor decode warning: {descriptor_path}: "
                    f"{format_decode_warning(descriptor.decode_diagnostics)}",
                    stage_id=StageId.LOAD_ORDER,
                )
            if descriptor.replace_paths:
                return descriptor.replace_paths
        return ()

    def _descriptor_candidates(
        self,
        entry: ResolvedModEntry,
        root_path: Path,
    ) -> tuple[Path, ...]:
        candidates: list[Path] = [root_path / "descriptor.mod"]
        _, local_mod_root = self._resolve_mod_paths()

        raw_name = Path(entry.raw_entry).name if entry.raw_entry else ""
        if raw_name.endswith(".mod"):
            candidates.append(local_mod_root / raw_name)

        local_descriptor = local_mod_root / f"{root_path.name}.mod"
        candidates.append(local_descriptor)

        deduped: list[Path] = []
        seen: set[Path] = set()
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
