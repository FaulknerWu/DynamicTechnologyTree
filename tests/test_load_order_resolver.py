from __future__ import annotations

import importlib
from pathlib import Path
import sqlite3

import pytest

_MODULE_NAME = ".".join(("dtt_core", "load_order_resolver"))
_resolver_module = importlib.import_module(_MODULE_NAME)
LoadOrderResolver = _resolver_module.LoadOrderResolver
LoadOrderResolutionError = _resolver_module.LoadOrderResolutionError


def _create_launcher_schema(db_path: Path, *, include_created_on: bool = True) -> None:
    created_on_column = ", createdOn TEXT" if include_created_on else ""
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE playsets (
                id TEXT PRIMARY KEY,
                name TEXT,
                isActive INTEGER,
                isRemoved INTEGER{created_on_column}
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


def test_resolver_selects_latest_created_active_playset_deterministically(
    tmp_path: Path,
) -> None:
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_launcher_schema(launcher_db)

    with sqlite3.connect(launcher_db) as conn:
        conn.executemany(
            "INSERT INTO playsets (id, name, isActive, isRemoved, createdOn) VALUES (?, ?, ?, ?, ?)",
            [
                ("ps-old", "Old", 1, 0, "2025-01-01T00:00:00Z"),
                ("ps-new", "New", 1, 0, "2026-01-01T00:00:00Z"),
                ("ps-removed", "Removed", 1, 1, "2030-01-01T00:00:00Z"),
            ],
        )
        conn.executemany(
            "INSERT INTO mods (id, dirPath, gameRegistryId, steamId, pdxId) VALUES (?, ?, ?, ?, ?)",
            [
                ("mod-old", "mod/old", "registry_old", "", ""),
                ("mod-new", "mod/new", "registry_new", "", ""),
                ("mod-removed", "mod/removed", "registry_removed", "", ""),
            ],
        )
        conn.executemany(
            "INSERT INTO playsets_mods (playsetId, modId, enabled, position) VALUES (?, ?, ?, ?)",
            [
                ("ps-old", "mod-old", 1, "1"),
                ("ps-new", "mod-new", 1, "1"),
                ("ps-removed", "mod-removed", 1, "1"),
            ],
        )

    resolver = LoadOrderResolver()
    with pytest.warns(RuntimeWarning, match="Multiple active playsets"):
        result = resolver.resolve_enabled_mods(launcher_db)

    assert result.source == "launcher-v2.sqlite"
    assert [entry.mod_id for entry in result.entries] == ["mod-new"]
    assert any("Multiple active playsets" in warning for warning in result.warnings)


def test_resolver_uses_lexicographic_name_when_created_on_column_missing(
    tmp_path: Path,
) -> None:
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_launcher_schema(launcher_db, include_created_on=False)

    with sqlite3.connect(launcher_db) as conn:
        conn.executemany(
            "INSERT INTO playsets (id, name, isActive, isRemoved) VALUES (?, ?, ?, ?)",
            [
                ("ps-zulu", "Zulu", 1, 0),
                ("ps-alpha", "Alpha", 1, 0),
            ],
        )
        conn.executemany(
            "INSERT INTO mods (id, dirPath, gameRegistryId, steamId, pdxId) VALUES (?, ?, ?, ?, ?)",
            [
                ("mod-zulu", "mod/zulu", "registry_zulu", "", ""),
                ("mod-alpha", "mod/alpha", "registry_alpha", "", ""),
            ],
        )
        conn.executemany(
            "INSERT INTO playsets_mods (playsetId, modId, enabled, position) VALUES (?, ?, ?, ?)",
            [
                ("ps-zulu", "mod-zulu", 1, "1"),
                ("ps-alpha", "mod-alpha", 1, "1"),
            ],
        )

    resolver = LoadOrderResolver()
    with pytest.warns(RuntimeWarning, match="Multiple active playsets"):
        result = resolver.resolve_enabled_mods(launcher_db)

    assert result.source == "launcher-v2.sqlite"
    assert [entry.mod_id for entry in result.entries] == ["mod-alpha"]
    assert any("Multiple active playsets" in warning for warning in result.warnings)


def test_resolver_returns_enabled_mods_sorted_by_position(tmp_path: Path) -> None:
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_launcher_schema(launcher_db)

    with sqlite3.connect(launcher_db) as conn:
        conn.execute(
            "INSERT INTO playsets (id, name, isActive, isRemoved, createdOn) VALUES (?, ?, ?, ?, ?)",
            ("ps-main", "Main", 1, 0, "2026-01-01T00:00:00Z"),
        )
        conn.executemany(
            "INSERT INTO mods (id, dirPath, gameRegistryId, steamId, pdxId) VALUES (?, ?, ?, ?, ?)",
            [
                ("mod-10", "mod/ten", "registry_ten", "", ""),
                ("mod-2", "mod/two", "registry_two", "", ""),
                ("mod-text", "mod/text", "registry_text", "", ""),
                ("mod-disabled", "mod/disabled", "registry_disabled", "", ""),
            ],
        )
        conn.executemany(
            "INSERT INTO playsets_mods (playsetId, modId, enabled, position) VALUES (?, ?, ?, ?)",
            [
                ("ps-main", "mod-10", 1, "10"),
                ("ps-main", "mod-2", 1, "2"),
                ("ps-main", "mod-text", 1, "z-last"),
                ("ps-main", "mod-disabled", 0, "0"),
            ],
        )

    resolver = LoadOrderResolver()
    result = resolver.resolve_enabled_mods(launcher_db)

    assert [entry.mod_id for entry in result.entries] == ["mod-2", "mod-10", "mod-text"]
    assert [entry.raw_entry for entry in result.entries] == [
        "mod/two",
        "mod/ten",
        "mod/text",
    ]


def test_resolver_fails_fast_when_db_missing(tmp_path: Path) -> None:
    launcher_db = tmp_path / "launcher-v2.sqlite"

    resolver = LoadOrderResolver()
    with pytest.raises(LoadOrderResolutionError) as exc:
        resolver.resolve_enabled_mods(launcher_db)

    assert exc.value.code == "missing_database"
    assert "launcher_db_path" in str(exc.value)


def test_resolver_fails_fast_when_db_corrupt(tmp_path: Path) -> None:
    launcher_db = tmp_path / "launcher-v2.sqlite"
    launcher_db.write_text("not a sqlite database", encoding="utf-8")

    resolver = LoadOrderResolver()
    with pytest.raises(LoadOrderResolutionError) as exc:
        resolver.resolve_enabled_mods(launcher_db)

    assert exc.value.code == "corrupt_database"
    assert "launcher-v2.sqlite" in str(exc.value)


def test_resolver_fails_fast_when_db_locked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher_db = tmp_path / "launcher-v2.sqlite"
    _create_launcher_schema(launcher_db)

    def _locked_connect(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(_resolver_module.sqlite3, "connect", _locked_connect)

    resolver = LoadOrderResolver()
    with pytest.raises(LoadOrderResolutionError) as exc:
        resolver.resolve_enabled_mods(launcher_db)

    assert exc.value.code == "database_locked"
    assert "Close Paradox Launcher" in str(exc.value)
