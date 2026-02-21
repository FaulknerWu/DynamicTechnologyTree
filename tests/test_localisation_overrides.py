# pyright: reportMissingImports=false

from __future__ import annotations

import importlib
from pathlib import Path

from conftest import _build_settings, _create_minimal_launcher_db
from generator import TechTreeGenerator

_LOCALISATION_PARSER = importlib.import_module("dtt_core.localisation_parser")


def _write_yml(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def test_localisation_overrides_count_is_occurrence_based(tmp_path: Path) -> None:
    merge_localisation_file_stream = _LOCALISATION_PARSER.merge_localisation_file_stream

    first = _write_yml(
        tmp_path / "localisation" / "00_first_l_english.yml",
        'l_english:\ntech_a_desc:0 "from first"\n',
    )
    second = _write_yml(
        tmp_path / "localisation" / "01_second_l_english.yml",
        'l_english:\ntech_a_desc:0 "from second"\n',
    )
    third = _write_yml(
        tmp_path / "localisation" / "02_third_l_english.yml",
        'l_english:\ntech_a_desc:0 "from third"\n',
    )

    merged = merge_localisation_file_stream(
        [first, second, third],
        expected_language="english",
    )

    assert merged.override_count == 2


def test_localisation_overrides_are_counted_in_single_parse_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_game = tmp_path / "stellaris"
    workshop = tmp_path / "workshop"
    loc_dir = base_game / "localisation"
    loc_dir.mkdir(parents=True)
    workshop.mkdir(parents=True)

    first = _write_yml(
        loc_dir / "00_base_l_english.yml",
        'l_english:\ntech_a_desc:0 "from first"\n',
    )
    second = _write_yml(
        loc_dir / "01_patch_l_english.yml",
        'l_english:\ntech_a_desc:0 "from second"\n',
    )
    _write_yml(
        loc_dir / "ignored_l_french.yml",
        'l_french:\ntech_a_desc:0 "bonjour"\n',
    )

    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    settings = _build_settings(
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db,
    )

    read_counts: dict[Path, int] = {}
    original_read = _LOCALISATION_PARSER.read_text_with_diagnostics

    def _counting_read(path: Path, **kwargs):
        read_counts[path] = read_counts.get(path, 0) + 1
        return original_read(path, **kwargs)

    monkeypatch.setattr(
        _LOCALISATION_PARSER, "read_text_with_diagnostics", _counting_read
    )

    gen = TechTreeGenerator.from_settings(settings)
    gen.scan_all_tech_descriptions()

    assert read_counts == {first: 1, second: 1}
    assert gen._ingestion_pipeline.report.localization_override_count == 1
