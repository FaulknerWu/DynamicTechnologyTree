# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _build_settings, _create_minimal_launcher_db
from dtt_core.load_order_resolver import LoadOrderResolver
from generator import TechTreeGenerator


def test_manifest_reuse_load_order_resolved_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    call_count = 0
    original = LoadOrderResolver.resolve_enabled_mods

    def _wrapped_resolve_enabled_mods(self, launcher_db_path):
        nonlocal call_count
        call_count += 1
        return original(self, launcher_db_path)

    monkeypatch.setattr(
        LoadOrderResolver, "resolve_enabled_mods", _wrapped_resolve_enabled_mods
    )

    gen = TechTreeGenerator.from_settings(settings)
    gen.scan_all_technology_files()
    gen.scan_all_tech_descriptions()

    assert call_count == 1


def test_manifest_reuse_cache_invalidated_on_new_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    call_count = 0
    original = LoadOrderResolver.resolve_enabled_mods

    def _wrapped_resolve_enabled_mods(self, launcher_db_path):
        nonlocal call_count
        call_count += 1
        return original(self, launcher_db_path)

    monkeypatch.setattr(
        LoadOrderResolver, "resolve_enabled_mods", _wrapped_resolve_enabled_mods
    )

    gen = TechTreeGenerator.from_settings(settings)

    gen.scan_all_technology_files()
    gen.scan_all_tech_descriptions()
    gen.scan_all_technology_files()
    gen.scan_all_tech_descriptions()

    assert call_count == 2
