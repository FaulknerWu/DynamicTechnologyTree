# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path
import sqlite3
import zipfile

import pytest

from generator import TechTreeGenerator


def _write_config(
    path: Path,
    *,
    base_game: Path,
    workshop: Path,
    launcher_db: Path,
    priority_mods: str | None = None,
) -> None:
    priority_line = (
        f"priority_mods = {priority_mods}\n" if priority_mods is not None else ""
    )
    path.write_text(
        """
[paths]
base_game_path = {base}
mod_folder_path = {workshop}
local_mod_folder_path =
launcher_db_path = {launcher_db}

[localization]
language = english
{priority_line}

""".strip().format(
            base=base_game,
            workshop=workshop,
            launcher_db=launcher_db,
            priority_line=priority_line,
        ),
        encoding="utf-8",
    )


def _create_minimal_launcher_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE playsets (
                id TEXT PRIMARY KEY,
                name TEXT,
                isActive INTEGER,
                isRemoved INTEGER,
                createdOn TEXT
            );

            CREATE TABLE playsets_mods (
                playsetId TEXT,
                modId TEXT,
                enabled INTEGER,
                position TEXT
            );

            CREATE TABLE mods (
                id TEXT PRIMARY KEY,
                dirPath TEXT,
                gameRegistryId TEXT,
                steamId TEXT,
                pdxId TEXT
            );

            CREATE TABLE knex_migrations (
                id INTEGER PRIMARY KEY,
                name TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO knex_migrations (id, name) VALUES (?, ?)",
            (1, "20250101000000_initial"),
        )
        conn.execute(
            "INSERT INTO playsets (id, name, isActive, isRemoved, createdOn) VALUES (?, ?, ?, ?, ?)",
            ("ps-vanilla", "Vanilla", 1, 0, "2026-01-01T00:00:00Z"),
        )


def _assert_identical_outputs(paths: list[Path], golden_path: Path) -> None:
    first = _read_identical_output_bytes(paths)
    assert golden_path.read_bytes() == first


def _read_identical_output_bytes(paths: list[Path]) -> bytes:
    assert paths, "expected at least one output path"
    for path in paths:
        assert path.exists(), f"missing output file: {path}"
    first = paths[0].read_bytes()
    for path in paths[1:]:
        assert path.read_bytes() == first
    return first


def _capture_determinism_bytes(
    run_root: Path,
    *,
    generator: TechTreeGenerator,
    lang_code: str,
) -> dict[str, bytes]:
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"
    report_rel_path = "localisation/dtt-save-report.txt"

    report_path = run_root / report_rel_path
    assert report_path.exists(), f"missing output file: {report_path}"

    return {
        main_name: _read_identical_output_bytes(
            generator._get_output_file_paths(lang_code, main_name)
        ),
        replaced_name: _read_identical_output_bytes(
            generator._get_output_file_paths(lang_code, replaced_name)
        ),
        report_rel_path: report_path.read_bytes(),
    }


def _assert_single_context_outputs_and_report(
    run_root: Path,
    *,
    main_name: str,
    replaced_name: str,
) -> None:
    main_text = (run_root / "localisation" / main_name).read_text(encoding="utf-8-sig")
    replaced_text = (run_root / "localisation" / replaced_name).read_text(
        encoding="utf-8-sig"
    )
    report_text = (run_root / "localisation" / "dtt-save-report.txt").read_text(
        encoding="utf-8"
    )

    assert "_corporate_techtree" not in main_text
    assert "_hive_mind_techtree" not in main_text
    assert "_machine_intelligence_techtree" not in main_text

    assert "_desc_corporate" not in replaced_text
    assert "_desc_hive_mind" not in replaced_text
    assert "_desc_machine_intelligence" not in replaced_text

    assert "eligibility_counts:" in report_text
    assert "unknown_predicate_frequency_top:" in report_text
    assert "swap_ambiguities:" in report_text


def _write_synthetic_regular_save(path: Path) -> Path:
    meta = 'name = "Golden Save"\n'
    gamestate = "\n".join(
        [
            "player = {",
            "  0 = { country = 7 }",
            "}",
            "country = {",
            "  7 = {",
            '    name = "Golden Empire"',
            "    authority = auth_democratic",
            "    ethics = { ethic_materialist }",
            "    civics = { civic_meritocracy }",
            "    origin = origin_prosperous_unification",
            "  }",
            "}",
        ]
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta", meta.encode("utf-8"))
        archive.writestr("gamestate", gamestate.encode("utf-8"))
    return path


def test_generator_golden_output(tmp_path: Path, monkeypatch) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    base_game = fixture_root / "stellaris"
    workshop = fixture_root / "workshop"
    assert base_game.is_dir()
    assert workshop.is_dir()

    cfg = tmp_path / "config.ini"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    _write_config(
        cfg,
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db,
    )
    save_path = _write_synthetic_regular_save(tmp_path / "golden.sav")

    monkeypatch.chdir(tmp_path)
    gen = TechTreeGenerator(str(cfg))
    gen.run_generation_process(save_path=save_path)

    lang_code = "english"
    golden_root = Path(__file__).parent / "golden"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"

    main_paths = gen._get_output_file_paths(lang_code, main_name)
    replaced_paths = gen._get_output_file_paths(lang_code, replaced_name)

    _assert_identical_outputs(main_paths, golden_root / main_name)
    _assert_identical_outputs(replaced_paths, golden_root / replaced_name)
    _assert_single_context_outputs_and_report(
        tmp_path,
        main_name=main_name,
        replaced_name=replaced_name,
    )


@pytest.mark.parametrize("priority_mods_value", ["", "12345,67890"])
def test_priority_mods_is_rejected_when_present(
    tmp_path: Path,
    priority_mods_value: str,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    base_game = fixture_root / "stellaris"
    workshop = fixture_root / "workshop"

    cfg_priority = tmp_path / "config.ini"
    launcher_db_priority = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db_priority)
    _write_config(
        cfg_priority,
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db_priority,
        priority_mods=priority_mods_value,
    )

    with pytest.raises(
        ValueError,
        match=r"\[localization\] priority_mods has been removed; delete this key from config\.ini",
    ):
        TechTreeGenerator(str(cfg_priority))


def test_output_determinism_across_run_roots(tmp_path: Path, monkeypatch) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    base_game = fixture_root / "stellaris"
    workshop = fixture_root / "workshop"
    assert base_game.is_dir()
    assert workshop.is_dir()

    lang_code = "english"

    run_a = tmp_path / "run_a"
    run_a.mkdir(parents=True)
    cfg_a = run_a / "config.ini"
    launcher_db_a = run_a / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db_a)
    _write_config(
        cfg_a,
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db_a,
    )
    save_a = _write_synthetic_regular_save(run_a / "run-a.sav")

    monkeypatch.chdir(run_a)
    gen_a = TechTreeGenerator(str(cfg_a))
    gen_a.run_generation_process(save_path=save_a)
    run_a_bytes = _capture_determinism_bytes(
        run_a,
        generator=gen_a,
        lang_code=lang_code,
    )

    run_b = tmp_path / "run_b"
    run_b.mkdir(parents=True)
    cfg_b = run_b / "config.ini"
    launcher_db_b = run_b / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db_b)
    _write_config(
        cfg_b,
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db_b,
    )
    save_b = _write_synthetic_regular_save(run_b / "run-b.sav")

    monkeypatch.chdir(run_b)
    gen_b = TechTreeGenerator(str(cfg_b))
    gen_b.run_generation_process(save_path=save_b)
    run_b_bytes = _capture_determinism_bytes(
        run_b,
        generator=gen_b,
        lang_code=lang_code,
    )

    assert run_a_bytes == run_b_bytes
