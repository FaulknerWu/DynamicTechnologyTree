from __future__ import annotations

import importlib
from pathlib import Path

_FILE_INDEXER_MODULE = importlib.import_module("dtt_core.file_indexer")
_SETTINGS_SNAPSHOT_MODULE = importlib.import_module("dtt_core.settings_snapshot")
_SOURCE_MANIFEST_MODULE = importlib.import_module("dtt_core.source_manifest")
_SETTINGS_MODULE = importlib.import_module("settings")

FileIndexer = _FILE_INDEXER_MODULE.FileIndexer
require_settings_snapshot = _SETTINGS_SNAPSHOT_MODULE.require_settings_snapshot
Source = _SOURCE_MANIFEST_MODULE.Source
SourceManifest = _SOURCE_MANIFEST_MODULE.SourceManifest
Settings = _SETTINGS_MODULE.Settings


def _write_file(root: Path, relative_path: str) -> None:
    file_path = root.joinpath(*relative_path.split("/"))
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("placeholder", encoding="utf-8")


def test_file_indexer_custom_pattern_recursive_technology_glob_includes_nested_files(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    _write_file(source_root, "common/technology/00_base.txt")
    _write_file(source_root, "common/technology/nested/99_extra.txt")

    manifest = SourceManifest(
        (
            Source(
                kind="vanilla",
                id="vanilla",
                display_name="Vanilla",
                root_path=source_root,
                load_index=0,
                provenance="base-game",
            ),
        )
    )

    default_files = FileIndexer().index_technology_files(manifest)
    assert [file_ref.relative_path for file_ref in default_files] == [
        "common/technology/00_base.txt"
    ]

    payload = Settings().model_dump(mode="python", round_trip=True)
    payload["file_indexing"]["technology_glob"] = "**/*.txt"
    settings = Settings.model_validate(payload, strict=True)
    config = require_settings_snapshot(settings).generator_config

    custom_files = FileIndexer(config=config.file_indexing).index_technology_files(
        manifest
    )
    assert [file_ref.relative_path for file_ref in custom_files] == [
        "common/technology/00_base.txt",
        "common/technology/nested/99_extra.txt",
    ]
