# pyright: reportMissingImports=false

from __future__ import annotations

import zipfile
from pathlib import Path

from conftest import _build_settings, _create_minimal_launcher_db
from dtt_core.output import plan_output_file_paths
from generator import TechTreeGenerator


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

    main_paths, main_failures = plan_output_file_paths(
        localisation_root=Path("localisation"),
        yml_targets=generator.config.output.yml_targets,
        lang_code=lang_code,
        filename=main_name,
    )
    assert not main_failures

    replaced_paths, replaced_failures = plan_output_file_paths(
        localisation_root=Path("localisation"),
        yml_targets=generator.config.output.yml_targets,
        lang_code=lang_code,
        filename=replaced_name,
    )
    assert not replaced_failures

    return {
        main_name: _read_identical_output_bytes(main_paths),
        replaced_name: _read_identical_output_bytes(replaced_paths),
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

    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    settings = _build_settings(
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db,
    )
    save_path = _write_synthetic_regular_save(tmp_path / "golden.sav")

    monkeypatch.chdir(tmp_path)
    gen = TechTreeGenerator(settings=settings)
    gen.run_generation_process(save_path=save_path)

    lang_code = "english"
    golden_root = Path(__file__).parent / "golden"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"

    main_paths, main_failures = plan_output_file_paths(
        localisation_root=Path("localisation"),
        yml_targets=gen.config.output.yml_targets,
        lang_code=lang_code,
        filename=main_name,
    )
    assert not main_failures

    replaced_paths, replaced_failures = plan_output_file_paths(
        localisation_root=Path("localisation"),
        yml_targets=gen.config.output.yml_targets,
        lang_code=lang_code,
        filename=replaced_name,
    )
    assert not replaced_failures

    _assert_identical_outputs(main_paths, golden_root / main_name)
    _assert_identical_outputs(replaced_paths, golden_root / replaced_name)
    _assert_single_context_outputs_and_report(
        tmp_path,
        main_name=main_name,
        replaced_name=replaced_name,
    )


def test_output_determinism_across_run_roots(tmp_path: Path, monkeypatch) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    base_game = fixture_root / "stellaris"
    workshop = fixture_root / "workshop"
    assert base_game.is_dir()
    assert workshop.is_dir()

    lang_code = "english"

    run_a = tmp_path / "run_a"
    run_a.mkdir(parents=True)
    launcher_db_a = run_a / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db_a)
    settings_a = _build_settings(
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db_a,
    )
    save_a = _write_synthetic_regular_save(run_a / "run-a.sav")

    monkeypatch.chdir(run_a)
    gen_a = TechTreeGenerator(settings=settings_a)
    gen_a.run_generation_process(save_path=save_a)
    run_a_bytes = _capture_determinism_bytes(
        run_a,
        generator=gen_a,
        lang_code=lang_code,
    )

    run_b = tmp_path / "run_b"
    run_b.mkdir(parents=True)
    launcher_db_b = run_b / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db_b)
    settings_b = _build_settings(
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db_b,
    )
    save_b = _write_synthetic_regular_save(run_b / "run-b.sav")

    monkeypatch.chdir(run_b)
    gen_b = TechTreeGenerator(settings=settings_b)
    gen_b.run_generation_process(save_path=save_b)
    run_b_bytes = _capture_determinism_bytes(
        run_b,
        generator=gen_b,
        lang_code=lang_code,
    )

    assert run_a_bytes == run_b_bytes
