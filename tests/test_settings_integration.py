# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _build_settings, _create_minimal_launcher_db, _write_sav
from generator import TechTreeGenerator
from settings import LocalizationSettings, PathsSettings, Settings

def test_settings_integration_snapshot_uses_passed_settings_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)

    settings = _build_settings(
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=launcher_db,
    )
    monkeypatch.chdir(tmp_path)

    generator = TechTreeGenerator.from_settings(settings)

    settings.localization.language = "simp_chinese"
    save_path = _write_sav(
        tmp_path / "settings-snapshot.sav",
        meta='name = "Settings Integration Save"\n',
        gamestate="\n".join(
            [
                "player = {",
                "  0 = { country = 7 }",
                "}",
                "country = {",
                "  7 = {",
                '    name = "Settings Snapshot Empire"',
                "    authority = auth_democratic",
                "  }",
                "}",
            ]
        ),
    )
    generator.run_generation_process(save_path=save_path)

    output_root = tmp_path / "localisation"
    assert (output_root / "zztechtreemain_l_english.yml").exists()
    assert not (output_root / "zztechtreemain_l_simp_chinese.yml").exists()


def test_settings_integration_requires_settings_is_hard_error(
    tmp_path: Path,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)

    generator = TechTreeGenerator.from_settings(
        _build_settings(
            base_game=fixture_root / "stellaris",
            workshop=fixture_root / "workshop",
            launcher_db=launcher_db,
        )
    )

    with pytest.raises(ValueError, match="settings is required and cannot be empty"):
        generator.run_generation_process_with_settings(
            save_path=tmp_path / "missing-settings.sav",
            settings=None,
        )


def test_settings_snapshot_refreshes_file_indexer_between_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_game = tmp_path / "stellaris"
    tech_dir = base_game / "common" / "technology"
    loc_dir = base_game / "localisation"
    tech_dir.mkdir(parents=True)
    loc_dir.mkdir(parents=True)

    (tech_dir / "a_techs.txt").write_text(
        """
tech_a = {
    area = physics
    tier = 1
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tech_dir / "b_techs.txt").write_text(
        """
tech_b = {
    area = physics
    tier = 1
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (loc_dir / "dtt_l_english.yml").write_text(
        """
l_english:
 tech_a_desc:0 "A"
 tech_b_desc:0 "B"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workshop = tmp_path / "workshop"
    workshop.mkdir(parents=True)

    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)

    base_settings = Settings(
        paths=PathsSettings(
            base_game_path=str(base_game),
            mod_folder_path=str(workshop),
            local_mod_folder_path="",
            launcher_db_path=str(launcher_db),
        ),
        localization=LocalizationSettings(language="english"),
    )
    settings_a = base_settings.model_copy(deep=True)
    settings_a.file_indexing.technology_glob = "a_*.txt"

    settings_b = base_settings.model_copy(deep=True)
    settings_b.file_indexing.technology_glob = "b_*.txt"

    save_path = _write_sav(
        tmp_path / "glob-refresh.sav",
        meta='name = "Settings Integration Save"\n',
        gamestate="\n".join(
            [
                "player = {",
                "  0 = { country = 7 }",
                "}",
                "country = {",
                "  7 = {",
                '    name = "Settings Snapshot Empire"',
                "    authority = auth_democratic",
                "  }",
                "}",
            ]
        ),
    )
    monkeypatch.chdir(tmp_path)

    generator = TechTreeGenerator.from_settings(settings_a)
    generator.run_generation_process_with_settings(save_path=save_path, settings=settings_a)

    assert set(generator.all_technologies) == {"tech_a"}

    generator.run_generation_process_with_settings(save_path=save_path, settings=settings_b)
    assert set(generator.all_technologies) == {"tech_b"}


def test_settings_snapshot_refreshes_ingestion_diagnostic_cap_between_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_game = tmp_path / "stellaris"
    tech_dir = base_game / "common" / "technology"
    loc_dir = base_game / "localisation"
    tech_dir.mkdir(parents=True)
    loc_dir.mkdir(parents=True)

    # Seed multiple files with parse diagnostics so the example cap has an effect.
    for index in range(6):
        (tech_dir / f"bad_{index}.txt").write_text(
            f"tech_bad_{index} = {{\n area = physics\n",  # missing closing braces
            encoding="utf-8",
        )

    workshop = tmp_path / "workshop"
    workshop.mkdir(parents=True)

    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)

    base_settings = Settings(
        paths=PathsSettings(
            base_game_path=str(base_game),
            mod_folder_path=str(workshop),
            local_mod_folder_path="",
            launcher_db_path=str(launcher_db),
        ),
        localization=LocalizationSettings(language="english"),
    )

    settings_one = base_settings.model_copy(deep=True)
    settings_one.ingestion.diagnostic_example_limit = 1

    settings_three = base_settings.model_copy(deep=True)
    settings_three.ingestion.diagnostic_example_limit = 3

    save_path = _write_sav(
        tmp_path / "cap-refresh.sav",
        meta='name = "Settings Integration Save"\n',
        gamestate="\n".join(
            [
                "player = {",
                "  0 = { country = 7 }",
                "}",
                "country = {",
                "  7 = {",
                '    name = "Settings Snapshot Empire"',
                "    authority = auth_democratic",
                "  }",
                "}",
            ]
        ),
    )
    monkeypatch.chdir(tmp_path)

    generator = TechTreeGenerator.from_settings(settings_one)
    generator.run_generation_process_with_settings(save_path=save_path, settings=settings_one)
    assert len(generator._ingestion_pipeline.report.tech_examples) == 1

    generator.run_generation_process_with_settings(save_path=save_path, settings=settings_three)
    assert len(generator._ingestion_pipeline.report.tech_examples) == 3
