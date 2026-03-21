from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

_settings = importlib.import_module("settings")
_store = importlib.import_module("settings_store")

Settings = _settings.Settings
SETTINGS_SCHEMA_VERSION = _settings.SETTINGS_SCHEMA_VERSION
SettingsStoreError = _store.SettingsStoreError
load_settings = _store.load_settings
save_settings = _store.save_settings


def test_settings_store_roundtrip(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    original = Settings.model_validate(
        {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "paths": {
                "base_game_path": "/tmp/base",
                "mod_folder_path": "/tmp/mods",
                "launcher_db_path": "/tmp/launcher-v2.sqlite",
                "local_mod_folder_path": "/tmp/local-mods",
            },
            "localization": {"target_language_code": "english"},
            "display": {
                "max_children_per_node": 8,
                "max_tree_depth": 3,
                "max_display_nodes": 42,
            },
        },
        strict=True,
    )

    save_settings(settings_path, original)
    loaded = load_settings(settings_path)

    assert loaded == original
    assert json.loads(settings_path.read_text(encoding="utf-8")) == original.model_dump(
        mode="json"
    )
    assert not [path for path in tmp_path.iterdir() if path.name.endswith(".tmp")]


def test_settings_store_invalid_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{", encoding="utf-8")

    with pytest.raises(SettingsStoreError) as exc_info:
        load_settings(settings_path)

    error = exc_info.value
    assert error.kind == "invalid_json"
    assert error.line == 1
    assert error.column == 2
    assert error.pydantic_errors is None


def test_settings_store_schema_invalid_reports_precise_path(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": SETTINGS_SCHEMA_VERSION,
                "paths": {},
                "localization": {},
                "display": {"unknown_display": 1},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsStoreError) as exc_info:
        load_settings(settings_path)

    error = exc_info.value
    assert error.kind == "extra_forbidden"
    assert error.path == ("display", "unknown_display")
    assert error.pydantic_errors is not None
    assert ("display", "unknown_display") in {
        tuple(item["loc"]) for item in error.pydantic_errors
    }


def test_settings_store_schema_version_missing_fails_loudly(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "paths": {},
                "localization": {},
                "display": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsStoreError) as exc_info:
        load_settings(settings_path)

    error = exc_info.value
    assert error.kind == "schema_version_missing"
    assert error.path == ("schema_version",)


def test_settings_store_unsupported_schema_version_fails_loudly(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    unsupported_schema_version = SETTINGS_SCHEMA_VERSION + 1
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": unsupported_schema_version,
                "paths": {},
                "localization": {},
                "display": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsStoreError) as exc_info:
        load_settings(settings_path)

    error = exc_info.value
    assert error.kind == "unsupported_schema_version"
    assert error.path == ("schema_version",)


def test_settings_store_rejects_type_coercion(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": SETTINGS_SCHEMA_VERSION,
                "paths": {},
                "localization": {},
                "display": {"max_tree_depth": "4"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettingsStoreError) as exc_info:
        load_settings(settings_path)

    error = exc_info.value
    assert error.path == ("display", "max_tree_depth")
    assert error.pydantic_errors is not None
    assert ("display", "max_tree_depth") in {
        tuple(item["loc"]) for item in error.pydantic_errors
    }
