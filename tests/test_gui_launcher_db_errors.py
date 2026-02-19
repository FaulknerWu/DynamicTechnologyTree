# pyright: reportMissingImports=false

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.generation_worker import (
    GenerationOutcome,
    GenerationOutcomeCode,
    GenerationWorker,
)

import dtt_core.load_order_resolver as load_order_resolver_module


def _write_config(
    path: Path,
    *,
    base_game: Path,
    workshop: Path,
    launcher_db: Path,
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


def _run_worker(config_path: Path, save_path: Path) -> GenerationOutcome:
    worker = GenerationWorker(str(config_path))
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
    cfg = tmp_path / "config.ini"
    save_path = _write_regular_save(tmp_path / "missing-db.sav")
    missing_db = tmp_path / "missing-launcher-v2.sqlite"

    _write_config(
        cfg,
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=missing_db,
    )

    monkeypatch.chdir(tmp_path)
    outcome = _run_worker(cfg, save_path)

    assert isinstance(outcome, GenerationOutcome)
    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "Launcher DB not found" in outcome.message


def test_generation_worker_launcher_db_corrupt_surfaces_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    cfg = tmp_path / "config.ini"
    save_path = _write_regular_save(tmp_path / "corrupt-db.sav")
    launcher_db = tmp_path / "launcher-v2.sqlite"
    launcher_db.write_text("not a sqlite database", encoding="utf-8")

    _write_config(
        cfg,
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=launcher_db,
    )

    monkeypatch.chdir(tmp_path)
    outcome = _run_worker(cfg, save_path)

    assert isinstance(outcome, GenerationOutcome)
    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "corrupt" in outcome.message.casefold()


def test_generation_worker_launcher_db_locked_surfaces_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    cfg = tmp_path / "config.ini"
    save_path = _write_regular_save(tmp_path / "locked-db.sav")
    launcher_db = tmp_path / "launcher-v2.sqlite"
    launcher_db.write_bytes(b"")

    _write_config(
        cfg,
        base_game=fixture_root / "stellaris",
        workshop=fixture_root / "workshop",
        launcher_db=launcher_db,
    )

    def _locked_connect(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(load_order_resolver_module.sqlite3, "connect", _locked_connect)

    monkeypatch.chdir(tmp_path)
    outcome = _run_worker(cfg, save_path)

    assert isinstance(outcome, GenerationOutcome)
    assert outcome.code == GenerationOutcomeCode.ERROR
    assert "Close Paradox Launcher" in outcome.message
