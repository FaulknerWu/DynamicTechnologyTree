from __future__ import annotations

from pathlib import Path

from generator import TechTreeGenerator


def _write_config(path: Path, *, base_game: Path, workshop: Path) -> None:
    path.write_text(
        """
[paths]
base_game_path = {base}
mod_folder_path = {workshop}
local_mod_folder_path =
dlc_load_path =

[localization]
language = english

""".strip().format(base=base_game, workshop=workshop),
        encoding="utf-8",
    )


def _assert_identical_outputs(paths: list[Path], golden_path: Path) -> None:
    assert paths, "expected at least one output path"
    for path in paths:
        assert path.exists(), f"missing output file: {path}"
    first = paths[0].read_bytes()
    for path in paths[1:]:
        assert path.read_bytes() == first
    assert golden_path.read_bytes() == first


def test_generator_golden_output(tmp_path: Path, monkeypatch) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    base_game = fixture_root / "stellaris"
    workshop = fixture_root / "workshop"
    assert base_game.is_dir()
    assert workshop.is_dir()

    cfg = tmp_path / "config.ini"
    _write_config(cfg, base_game=base_game, workshop=workshop)

    monkeypatch.chdir(tmp_path)
    gen = TechTreeGenerator(str(cfg))
    gen.run_generation_process()

    lang_code = "english"
    golden_root = Path(__file__).parent / "golden"
    main_name = f"zztechtreemain_l_{lang_code}.yml"
    replaced_name = f"zztechtreereplaced_l_{lang_code}.yml"

    main_paths = gen._get_output_file_paths(lang_code, main_name)
    replaced_paths = gen._get_output_file_paths(lang_code, replaced_name)

    _assert_identical_outputs(main_paths, golden_root / main_name)
    _assert_identical_outputs(replaced_paths, golden_root / replaced_name)
