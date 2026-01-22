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


def test_generator_smoke_empty_dirs(tmp_path: Path) -> None:
    base_game = tmp_path / "stellaris"
    workshop = tmp_path / "workshop"
    (base_game / "common" / "technology").mkdir(parents=True)
    (base_game / "localisation").mkdir(parents=True)
    workshop.mkdir(parents=True)

    cfg = tmp_path / "config.ini"
    _write_config(cfg, base_game=base_game, workshop=workshop)

    gen = TechTreeGenerator(str(cfg))
    gen.scan_all_technology_files()
    gen.build_technology_tree_relationships()
    gen.scan_all_tech_descriptions()

    assert gen.all_technologies == {}
