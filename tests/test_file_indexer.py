from __future__ import annotations

import importlib
from pathlib import Path

_FILE_INDEXER_MODULE = importlib.import_module("dtt_core.file_indexer")
_SOURCE_MANIFEST_MODULE = importlib.import_module("dtt_core.source_manifest")

FileIndexer = _FILE_INDEXER_MODULE.FileIndexer
Source = _SOURCE_MANIFEST_MODULE.Source
SourceManifest = _SOURCE_MANIFEST_MODULE.SourceManifest


def _write_file(root: Path, relative_path: str) -> None:
    file_path = root.joinpath(*relative_path.split("/"))
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("placeholder", encoding="utf-8")


def test_replace_path_removes_lower_precedence_files_without_substitute(
    tmp_path: Path,
) -> None:
    vanilla_root = tmp_path / "vanilla"
    patch_root = tmp_path / "patch"

    _write_file(vanilla_root, "common/technology/00_base.txt")
    patch_root.mkdir()

    manifest = SourceManifest(
        (
            Source(
                kind="vanilla",
                id="vanilla",
                display_name="Vanilla",
                root_path=vanilla_root,
                load_index=0,
                provenance="base-game",
            ),
            Source(
                kind="mod",
                id="patch",
                display_name="Patch",
                root_path=patch_root,
                load_index=1,
                replace_paths=("common\\technology\\",),
                provenance="workshop",
            ),
        )
    )

    files = FileIndexer().index_technology_files(manifest)

    assert files == ()


def test_technology_ordering_is_ascii_and_tie_breaks_by_load_order(
    tmp_path: Path,
) -> None:
    vanilla_root = tmp_path / "vanilla"
    mod_root = tmp_path / "mod"

    _write_file(vanilla_root, "common/technology/z_shared.txt")
    _write_file(mod_root, "common/technology/a_first.txt")
    _write_file(mod_root, "common/technology/z_shared.txt")

    manifest = SourceManifest(
        (
            Source(
                kind="vanilla",
                id="vanilla",
                display_name="Vanilla",
                root_path=vanilla_root,
                load_index=0,
                provenance="base-game",
            ),
            Source(
                kind="mod",
                id="mod",
                display_name="Mod",
                root_path=mod_root,
                load_index=1,
                provenance="workshop",
            ),
        )
    )

    files = FileIndexer().index_technology_files(manifest)

    assert [file_ref.relative_path for file_ref in files] == [
        "common/technology/a_first.txt",
        "common/technology/z_shared.txt",
        "common/technology/z_shared.txt",
    ]
    assert [file_ref.source_id for file_ref in files] == ["mod", "vanilla", "mod"]
    assert all("\\" not in file_ref.relative_path for file_ref in files)


def test_localisation_replace_files_are_loaded_in_late_phase(tmp_path: Path) -> None:
    vanilla_root = tmp_path / "vanilla"
    mod_root = tmp_path / "mod"

    _write_file(vanilla_root, "localisation/english/z_l_english.yml")
    _write_file(vanilla_root, "localisation/replace/00_patch_l_english.yml")
    _write_file(mod_root, "localisation/a_l_english.yml")
    _write_file(mod_root, "localisation/replace/99_patch_l_english.yml")

    manifest = SourceManifest(
        (
            Source(
                kind="vanilla",
                id="vanilla",
                display_name="Vanilla",
                root_path=vanilla_root,
                load_index=0,
                provenance="base-game",
            ),
            Source(
                kind="mod",
                id="mod",
                display_name="Mod",
                root_path=mod_root,
                load_index=1,
                provenance="workshop",
            ),
        )
    )

    files = FileIndexer().index_localisation_files(manifest)

    assert [file_ref.relative_path for file_ref in files] == [
        "localisation/a_l_english.yml",
        "localisation/english/z_l_english.yml",
        "localisation/replace/00_patch_l_english.yml",
        "localisation/replace/99_patch_l_english.yml",
    ]
    assert [file_ref.sort_key[0] for file_ref in files] == [0, 0, 1, 1]
