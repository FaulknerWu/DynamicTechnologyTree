from __future__ import annotations

import os
import sqlite3
import sys
import zipfile
from pathlib import Path
from typing import Any

# Allow `import generator` etc without requiring an editable install.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))
sys.modules.setdefault("conftest", sys.modules[__name__])

import pytest  # noqa: E402

from settings import LocalizationSettings, PathsSettings, Settings  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qt_app() -> Any:
    from PyQt6.QtWidgets import QApplication

    app: Any = QApplication.instance()
    if app is None:
        app = QApplication([])
    try:
        app.setQuitOnLastWindowClosed(False)
    except Exception:
        pass
    return app


@pytest.fixture()
def message_boxes(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[tuple[tuple[Any, ...], dict[str, Any]]]]:
    from PyQt6.QtWidgets import QMessageBox

    calls: dict[str, list[tuple[tuple[Any, ...], dict[str, Any]]]] = {
        "warning": [],
        "critical": [],
        "information": [],
    }

    def _stub(kind: str):
        def _impl(*args: Any, **kwargs: Any) -> Any:
            calls[kind].append((args, kwargs))
            return QMessageBox.StandardButton.Ok

        return _impl

    monkeypatch.setattr(QMessageBox, "warning", _stub("warning"))
    monkeypatch.setattr(QMessageBox, "critical", _stub("critical"))
    monkeypatch.setattr(QMessageBox, "information", _stub("information"))
    return calls


def _create_minimal_launcher_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript("""
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
            """)
        conn.execute(
            "INSERT INTO knex_migrations (id, name) VALUES (?, ?)",
            (1, "20250101000000_initial"),
        )
        conn.execute(
            "INSERT INTO playsets (id, name, isActive, isRemoved, createdOn) VALUES (?, ?, ?, ?, ?)",
            ("ps-vanilla", "Vanilla", 1, 0, "2026-01-01T00:00:00Z"),
        )


def _build_settings(
    *,
    base_game: Path,
    workshop: Path,
    launcher_db: Path,
    language: str = "english",
) -> Settings:
    return Settings(
        paths=PathsSettings(
            base_game_path=str(base_game),
            mod_folder_path=str(workshop),
            local_mod_folder_path="",
            launcher_db_path=str(launcher_db),
        ),
        localization=LocalizationSettings(target_language_code=language),
    )


def _write_sav(
    path: Path,
    *,
    meta: str | bytes | None,
    gamestate: str | bytes | None,
    extras: dict[str, str | bytes] | None = None,
) -> Path:
    def _payload_bytes(payload: str | bytes) -> bytes:
        if isinstance(payload, bytes):
            return payload
        return payload.encode("utf-8")

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if meta is not None:
            archive.writestr("meta", _payload_bytes(meta))
        if gamestate is not None:
            archive.writestr("gamestate", _payload_bytes(gamestate))
        for name, payload in (extras or {}).items():
            archive.writestr(name, _payload_bytes(payload))
    return path
