# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _build_settings, _create_minimal_launcher_db, _write_sav
from generator import TechTreeGenerator


def test_run_generation_process_requires_save_path(
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
    gen = TechTreeGenerator.from_settings(settings)

    with pytest.raises(ValueError, match="save_path is required and cannot be empty"):
        gen.run_generation_process()

    with pytest.raises(ValueError, match="save_path is required and cannot be empty"):
        gen.run_generation_process(save_path="  ")


def test_save_required_ambiguous_requires_country_id(
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

    save_path = _write_sav(
        tmp_path / "ambiguous.sav",
        meta='name = "Ambiguous Save"\n',
        gamestate="\n".join(
            [
                "player = {",
                "  1 = { country = 42 }",
                "  0 = { country = 7 }",
                "}",
                "country = {",
                "  7 = {",
                '    name = "Alpha Union"',
                "    authority = auth_democratic",
                "  }",
                "  42 = {",
                '    name = "Beta Directorate"',
                "    authority = auth_machine_intelligence",
                "  }",
                "}",
            ]
        ),
    )

    monkeypatch.chdir(tmp_path)
    gen = TechTreeGenerator.from_settings(settings)

    with pytest.raises(ValueError, match="ambiguous player empire") as exc:
        gen.run_generation_process(save_path=save_path)

    assert "candidates=[7, 42]" in str(exc.value)


def test_save_required_non_ambiguous_allows_country_id_to_be_omitted(
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

    save_path = _write_sav(
        tmp_path / "single-candidate.sav",
        meta='name = "Non-Ambiguous Save"\n',
        gamestate="\n".join(
            [
                "player = {",
                "  0 = { country = 7 }",
                "}",
                "country = {",
                '  7 = { name = "Alpha Union" authority = auth_democratic }',
                "}",
            ]
        ),
    )

    monkeypatch.chdir(tmp_path)
    gen = TechTreeGenerator.from_settings(settings)

    gen.run_generation_process(save_path=save_path)
    assert (Path("localisation") / "dtt-save-report.txt").is_file()
