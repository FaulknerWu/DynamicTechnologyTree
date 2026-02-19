# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path
import sqlite3
import zipfile

import pytest

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
""".strip().format(
            base=base_game,
            workshop=workshop,
            launcher_db=launcher_db,
        ),
        encoding="utf-8",
    )


def _write_sav(path: Path, *, meta: str, gamestate: str) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta", meta.encode("utf-8"))
        archive.writestr("gamestate", gamestate.encode("utf-8"))
    return path


def test_run_generation_process_requires_save_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    cfg = tmp_path / "config.ini"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    _write_config(
        cfg,
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=launcher_db,
    )

    monkeypatch.chdir(tmp_path)
    gen = TechTreeGenerator(str(cfg))

    with pytest.raises(ValueError, match="save_path is required and cannot be empty"):
        gen.run_generation_process()

    with pytest.raises(ValueError, match="save_path is required and cannot be empty"):
        gen.run_generation_process(save_path="  ")


def test_run_generation_process_requires_country_id_when_candidates_are_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    cfg = tmp_path / "config.ini"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_minimal_launcher_db(launcher_db)
    _write_config(
        cfg,
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
    gen = TechTreeGenerator(str(cfg))

    with pytest.raises(ValueError, match="ambiguous player empire") as exc:
        gen.run_generation_process(save_path=save_path)

    assert "candidates=[7, 42]" in str(exc.value)
