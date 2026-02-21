from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from collections.abc import Iterator

SourceKind = Literal["vanilla", "mod"]
Domain = Literal["technology", "localisation"]
SortKey = tuple[int, str, int, int]


def normalize_manifest_path(path: str | Path) -> str:
    text = str(path).replace("\\", "/").strip()
    if not text:
        return ""

    normalized = posixpath.normpath(text)
    if normalized == ".":
        return ""

    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


@dataclass(frozen=True)
class Source:
    kind: SourceKind
    id: str
    display_name: str
    root_path: Path
    load_index: int
    replace_paths: tuple[str, ...] = ()
    provenance: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "root_path", Path(self.root_path))

        normalized_replace_paths = tuple(
            normalized
            for raw in self.replace_paths
            if (normalized := normalize_manifest_path(raw))
        )
        object.__setattr__(self, "replace_paths", normalized_replace_paths)


@dataclass(frozen=True)
class SourceManifest:
    ordered_sources: tuple[Source, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ordered_sources", tuple(self.ordered_sources))

    def __iter__(self) -> Iterator[Source]:
        return iter(self.ordered_sources)


@dataclass(frozen=True)
class FileRef:
    source_id: str
    relative_path: str
    absolute_path: Path
    domain: Domain
    sort_key: SortKey

    def __post_init__(self) -> None:
        object.__setattr__(self, "absolute_path", Path(self.absolute_path))
        object.__setattr__(
            self,
            "relative_path",
            normalize_manifest_path(self.relative_path),
        )
