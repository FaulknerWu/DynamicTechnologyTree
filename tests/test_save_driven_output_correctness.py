# pyright: reportMissingImports=false

from __future__ import annotations

import zipfile
from pathlib import Path

from conftest import _build_settings, _create_minimal_launcher_db
from dtt_core.output import plan_output_file_paths
from generator import TechTreeGenerator


def _write_synthetic_machine_save(path: Path) -> Path:
    meta = 'name = "Machine Save"\n'
    gamestate = "\n".join(
        [
            "player = {",
            "  0 = { country = 7 }",
            "}",
            "country = {",
            "  7 = {",
            '    name = "Machine Empire"',
            # sav_reader infers gestalt flags from authority (machine_intelligence substring).
            "    authority = auth_machine_intelligence",
            "  }",
            "}",
        ]
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta", meta.encode("utf-8"))
        archive.writestr("gamestate", gamestate.encode("utf-8"))
    return path


def _write_synthetic_regular_save(path: Path) -> Path:
    meta = 'name = "Regular Save"\n'
    gamestate = "\n".join(
        [
            "player = {",
            "  0 = { country = 7 }",
            "}",
            "country = {",
            "  7 = {",
            '    name = "Regular Empire"',
            "    authority = auth_democratic",
            "  }",
            "}",
        ]
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta", meta.encode("utf-8"))
        archive.writestr("gamestate", gamestate.encode("utf-8"))
    return path


def _output_paths(generator: TechTreeGenerator, *, lang_code: str, filename: str) -> list[Path]:
    paths, failures = plan_output_file_paths(
        localisation_root=Path("localisation"),
        yml_targets=generator.config.output.yml_targets,
        lang_code=lang_code,
        filename=filename,
    )
    assert not failures
    return paths


def test_gestalt_technology_swap_applies_active_display_id(tmp_path: Path, monkeypatch):
    fixture_root = Path(__file__).parent / "fixtures"
    base_game = fixture_root / "stellaris"
    workshop = fixture_root / "workshop"
    assert base_game.is_dir()
    assert workshop.is_dir()

    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    settings = _build_settings(
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db,
    )
    save_path = _write_synthetic_machine_save(tmp_path / "machine.sav")

    monkeypatch.chdir(tmp_path)
    gen = TechTreeGenerator(settings=settings)
    gen.run_generation_process(save_path=save_path)

    lang_code = "english"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"

    for path in _output_paths(gen, lang_code=lang_code, filename=main_name):
        text = path.read_text(encoding="utf-8-sig")
        assert " tech_child_a_gestalt_techtree:0 " in text
        assert " tech_child_a_techtree:0 " not in text

    for path in _output_paths(gen, lang_code=lang_code, filename=replaced_name):
        text = path.read_text(encoding="utf-8-sig")
        assert " tech_child_a_gestalt_desc:0 " in text
        assert " tech_child_a_desc:0 " not in text


def test_potential_filtering_excludes_machine_only_tech_for_regular_save(
    tmp_path: Path, monkeypatch
):
    fixture_root = Path(__file__).parent / "fixtures"

    base_game = tmp_path / "stellaris"
    tech_dir = base_game / "common" / "technology"
    loc_dir = base_game / "localisation"
    tech_dir.mkdir(parents=True)
    loc_dir.mkdir(parents=True)

    # Copy baseline fixtures and add a machine-only tech gated by `potential`.
    (tech_dir / "dtt_techs.txt").write_text(
        (fixture_root / "stellaris" / "common" / "technology" / "dtt_techs.txt").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (loc_dir / "dtt_l_english.yml").write_text(
        (fixture_root / "stellaris" / "localisation" / "dtt_l_english.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (tech_dir / "dtt_machine_only.txt").write_text(
        """
tech_machine_only = {
    area = physics
    tier = 2
    prerequisites = { tech_root }
    potential = { is_machine_empire = yes }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    workshop = tmp_path / "workshop"
    workshop.mkdir(parents=True)

    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    settings = _build_settings(
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db,
    )
    save_path = _write_synthetic_regular_save(tmp_path / "regular.sav")

    monkeypatch.chdir(tmp_path)
    gen = TechTreeGenerator(settings=settings)
    gen.run_generation_process(save_path=save_path)

    lang_code = "english"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"

    for path in _output_paths(gen, lang_code=lang_code, filename=main_name):
        text = path.read_text(encoding="utf-8-sig")
        assert " tech_machine_only_techtree:0 " not in text
        assert "technology:tech_machine_only" not in text

    for path in _output_paths(gen, lang_code=lang_code, filename=replaced_name):
        text = path.read_text(encoding="utf-8-sig")
        assert " tech_machine_only_desc:0 " not in text
