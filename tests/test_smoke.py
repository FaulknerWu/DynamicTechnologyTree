# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path
import sqlite3

from generator import TechTreeGenerator


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
            """
        )
        conn.execute(
            "INSERT INTO playsets (id, name, isActive, isRemoved, createdOn) VALUES (?, ?, ?, ?, ?)",
            ("ps-vanilla", "Vanilla", 1, 0, "2026-01-01T00:00:00Z"),
        )


def _write_config(
    path: Path, *, base_game: Path, workshop: Path, launcher_db: Path
) -> None:
    path.write_text(
        """
[paths]
base_game_path = {base}
mod_folder_path = {workshop}
local_mod_folder_path =
launcher_db_path = {launcher_db}

[localization]
language = english

""".strip().format(base=base_game, workshop=workshop, launcher_db=launcher_db),
        encoding="utf-8",
    )


def test_generator_smoke_empty_dirs(tmp_path: Path) -> None:
    base_game = tmp_path / "stellaris"
    workshop = tmp_path / "workshop"
    (base_game / "common" / "technology").mkdir(parents=True)
    (base_game / "localisation").mkdir(parents=True)
    workshop.mkdir(parents=True)

    cfg = tmp_path / "config.ini"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    _write_config(cfg, base_game=base_game, workshop=workshop, launcher_db=launcher_db)

    gen = TechTreeGenerator(str(cfg))
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
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (loc_dir / "dtt_l_english.yml").write_text(
        """
l_english:
 tech_base_desc:0 "Base description"
 tech_base_variant_desc:0 "Variant description"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cfg = tmp_path / "config.ini"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    _write_config(cfg, base_game=base_game, workshop=workshop, launcher_db=launcher_db)

    gen = TechTreeGenerator(str(cfg))
    gen.scan_all_technology_files()
    gen.scan_all_tech_descriptions()

    assert "tech_base_variant" not in gen.all_technologies
    assert (
        gen.tech_descriptions["tech_base_variant"]["english"] == "Variant description"
    )
