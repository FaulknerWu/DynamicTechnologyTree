# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

from conftest import _build_settings, _create_minimal_launcher_db
from generator import TechTreeGenerator


def test_generator_smoke_empty_dirs(tmp_path: Path) -> None:
    base_game = tmp_path / "stellaris"
    workshop = tmp_path / "workshop"
    (base_game / "common" / "technology").mkdir(parents=True)
    (base_game / "localisation").mkdir(parents=True)
    workshop.mkdir(parents=True)

    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    settings = _build_settings(
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db,
    )

    gen = TechTreeGenerator(settings=settings)
    gen.scan_all_technology_files()
    gen.build_technology_tree_relationships()
    gen.scan_all_tech_descriptions()

    assert gen.all_technologies == {}


def test_swap_variant_description_kept_for_non_tech_id(tmp_path: Path) -> None:
    base_game = tmp_path / "stellaris"
    workshop = tmp_path / "workshop"
    tech_dir = base_game / "common" / "technology"
    loc_dir = base_game / "localisation"
    tech_dir.mkdir(parents=True)
    loc_dir.mkdir(parents=True)
    workshop.mkdir(parents=True)

    (tech_dir / "dtt_swaps.txt").write_text(
        """
tech_base = {
    area = physics
    tier = 1
    technology_swap = {
        trigger = { always = yes }
        name = "tech_base_variant"
    }
}
""".strip() + "\n",
        encoding="utf-8",
    )
    (loc_dir / "dtt_l_english.yml").write_text(
        """
l_english:
 tech_base_desc:0 "Base description"
 tech_base_variant_desc:0 "Variant description"
""".strip() + "\n",
        encoding="utf-8",
    )

    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    settings = _build_settings(
        base_game=base_game,
        workshop=workshop,
        launcher_db=launcher_db,
    )

    gen = TechTreeGenerator(settings=settings)
    gen.scan_all_technology_files()
    gen.scan_all_tech_descriptions()

    assert "tech_base_variant" not in gen.all_technologies
    assert (
        gen.tech_descriptions["tech_base_variant"]["english"] == "Variant description"
    )
