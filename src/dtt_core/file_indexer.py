from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dtt_core.source_manifest import (
    Domain,
    FileRef,
    SortKey,
    Source,
    SourceManifest,
    normalize_manifest_path,
)


@dataclass(frozen=True)
class _IndexedFile:
    source_id: str
    relative_path: str
    absolute_path: Path
    load_index: int
    source_order: int


class FileIndexer:
    _TECH_ROOT = Path("common") / "technology"
    _LOCALISATION_ROOT = Path("localisation")
    _LOCALISATION_REPLACE_PREFIX = "localisation/replace"

    def index_technology_files(self, manifest: SourceManifest) -> tuple[FileRef, ...]:
        return self._index_domain(manifest, domain="technology")

    def index_localisation_files(self, manifest: SourceManifest) -> tuple[FileRef, ...]:
        return self._index_domain(manifest, domain="localisation")

    def _index_domain(
        self, manifest: SourceManifest, domain: Domain
    ) -> tuple[FileRef, ...]:
        kept: list[_IndexedFile] = []
        for source_order, source in enumerate(manifest.ordered_sources):
            kept = self._apply_replace_paths(kept, source.replace_paths)
            kept.extend(self._scan_source(source, source_order, domain))

        indexed = sorted(
            kept, key=lambda file_ref: self._build_sort_key(file_ref, domain)
        )
        return tuple(
            FileRef(
                source_id=file_ref.source_id,
                relative_path=file_ref.relative_path,
                absolute_path=file_ref.absolute_path,
                domain=domain,
                sort_key=self._build_sort_key(file_ref, domain),
            )
            for file_ref in indexed
        )

    def _scan_source(
        self,
        source: Source,
        source_order: int,
        domain: Domain,
    ) -> tuple[_IndexedFile, ...]:
        candidates: list[_IndexedFile] = []
        for relative_path, absolute_path in self._iter_domain_files(source, domain):
            candidates.append(
                _IndexedFile(
                    source_id=source.id,
                    relative_path=relative_path,
                    absolute_path=absolute_path,
                    load_index=source.load_index,
                    source_order=source_order,
                )
            )

        candidates.sort(key=lambda candidate: candidate.relative_path)
        return tuple(candidates)

    def _iter_domain_files(
        self,
        source: Source,
        domain: Domain,
    ) -> tuple[tuple[str, Path], ...]:
        root = source.root_path
        if domain == "technology":
            tech_dir = root / self._TECH_ROOT
            if not tech_dir.is_dir():
                return ()
            return tuple(
                self._to_relative_ref(root, file_path)
                for file_path in tech_dir.glob("*.txt")
                if file_path.is_file()
            )

        loc_dir = root / self._LOCALISATION_ROOT
        if not loc_dir.is_dir():
            return ()
        return tuple(
            self._to_relative_ref(root, file_path)
            for file_path in loc_dir.rglob("*.yml")
            if file_path.is_file()
        )

    def _to_relative_ref(self, source_root: Path, file_path: Path) -> tuple[str, Path]:
        relative = normalize_manifest_path(
            file_path.relative_to(source_root).as_posix()
        )
        return relative, file_path

    def _apply_replace_paths(
        self,
        existing: list[_IndexedFile],
        replace_paths: tuple[str, ...],
    ) -> list[_IndexedFile]:
        if not replace_paths:
            return existing

        return [
            file_ref
            for file_ref in existing
            if not any(
                self._is_under_prefix(file_ref.relative_path, prefix)
                for prefix in replace_paths
            )
        ]

    def _build_sort_key(self, file_ref: _IndexedFile, domain: Domain) -> SortKey:
        phase = 0
        if domain == "localisation" and self._is_under_prefix(
            file_ref.relative_path,
            self._LOCALISATION_REPLACE_PREFIX,
        ):
            phase = 1

        return (
            phase,
            file_ref.relative_path,
            file_ref.load_index,
            file_ref.source_order,
        )

    @staticmethod
    def _is_under_prefix(path: str, prefix: str) -> bool:
        normalized_path = normalize_manifest_path(path)
        normalized_prefix = normalize_manifest_path(prefix)
        if not normalized_prefix:
            return False
        return normalized_path == normalized_prefix or normalized_path.startswith(
            f"{normalized_prefix}/"
        )
