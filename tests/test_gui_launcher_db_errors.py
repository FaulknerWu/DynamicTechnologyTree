# pyright: reportMissingImports=false

from __future__ import annotations

import os
import sqlite3
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import dtt_core.load_order_resolver as load_order_resolver_module
from conftest import _build_settings
from gui.generation_worker import (
    GenerationOutcome,
    GenerationOutcomeCode,
    GenerationWorker,
)
from settings import Settings

def _write_regular_save(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta", b'name = "Launcher DB Test Save"\n')
        archive.writestr(
            "gamestate",
            "\n".join(
                [
                    "player = {",
                    "  0 = { country = 7 }",
                    "}",
                    "country = {",
                    "  7 = {",
                    '    name = "Launcher DB Test Empire"',
                    "    authority = auth_democratic",
                    "  }",
                    "}",
                ]
            ).encode("utf-8"),
        )
    return path


def _run_worker(settings: Settings, save_path: Path) -> GenerationOutcome:
    worker = GenerationWorker(settings)
    worker.save_path = str(save_path)

    outcomes: list[object] = []
    worker.finished.connect(outcomes.append)
    worker.run()

    assert outcomes, "expected GenerationWorker to emit finished"
    outcome = outcomes[-1]
    assert isinstance(outcome, GenerationOutcome)
    return outcome


def test_generation_worker_launcher_db_missing_surfaces_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    save_path = _write_regular_save(tmp_path / "missing-db.sav")
    missing_db = tmp_path / "missing-launcher-v2.sqlite"

    settings = _build_settings(
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=missing_db,
    )

    monkeypatch.chdir(tmp_path)
    outcome = _run_worker(settings, save_path)

    assert isinstance(outcome, GenerationOutcome)
    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "Launcher DB not found" in outcome.message


def test_generation_worker_launcher_db_corrupt_surfaces_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    save_path = _write_regular_save(tmp_path / "corrupt-db.sav")
    launcher_db = tmp_path / "launcher-v2.sqlite"
    launcher_db.write_text("not a sqlite database", encoding="utf-8")

    settings = _build_settings(
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=launcher_db,
    )

    monkeypatch.chdir(tmp_path)
    outcome = _run_worker(settings, save_path)

    assert isinstance(outcome, GenerationOutcome)
    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "corrupt" in outcome.message.casefold()


def test_generation_worker_launcher_db_locked_surfaces_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    save_path = _write_regular_save(tmp_path / "locked-db.sav")
    launcher_db = tmp_path / "launcher-v2.sqlite"
    launcher_db.write_bytes(b"")

    settings = _build_settings(
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=launcher_db,
    )

    def _locked_connect(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(load_order_resolver_module.sqlite3, "connect", _locked_connect)

    monkeypatch.chdir(tmp_path)
    outcome = _run_worker(settings, save_path)

    assert isinstance(outcome, GenerationOutcome)
    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "Close Paradox Launcher" in outcome.message
