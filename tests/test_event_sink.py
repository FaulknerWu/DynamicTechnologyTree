# pyright: reportMissingImports=false

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
import zipfile

import pytest

from dtt_core.events import (
    EventKind,
    EventSink,
    GenerationEvent,
    NullEventSink,
    StageId,
)
from dtt_core.stdout_event_sink import StdoutEventSink
from generator import TechTreeGenerator


class RecordingEventSink:
    def __init__(self) -> None:
        self.events: list[GenerationEvent] = []

    def emit(self, event: GenerationEvent) -> None:
        self.events.append(event)


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


def _write_save(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta", b'name = "Event Sink Save"\n')
        archive.writestr(
            "gamestate",
            "\n".join(
                [
                    "player = {",
                    "  0 = { country = 7 }",
                    "}",
                    "country = {",
                    "  7 = {",
                    '    name = "Event Sink Empire"',
                    "    authority = auth_democratic",
                    "  }",
                    "}",
                ]
            ).encode("utf-8"),
        )
    return path


def test_stage_id_values_are_stable_machine_ids() -> None:
    assert tuple(stage.value for stage in StageId) == (
        "SAVE_PARSE",
        "LOAD_ORDER",
        "INGEST_TECH",
        "INGEST_L10N",
        "RELATIONS",
        "CYCLES",
        "RENDER",
        "WRITE_OUTPUT",
        "DONE",
    )


def test_event_kind_values_are_stable_machine_ids() -> None:
    assert tuple(kind.value for kind in EventKind) == (
        "progress",
        "log",
        "warning",
        "error",
        "artifact",
    )


def test_generation_event_is_immutable() -> None:
    event = GenerationEvent(
        stage_id=StageId.SAVE_PARSE,
        kind=EventKind.PROGRESS,
        message="Parsing save",
        progress=10,
        details=(("file", "example.sav"),),
    )

    with pytest.raises(FrozenInstanceError):
        event.message = "mutated"  # type: ignore[misc]


def test_null_event_sink_matches_protocol_and_accepts_events() -> None:
    sink = NullEventSink()
    assert isinstance(sink, EventSink)

    sink.emit(
        GenerationEvent(
            stage_id=StageId.DONE,
            kind=EventKind.LOG,
            message="Generation complete",
        )
    )


def test_event_module_import_does_not_import_pyqt6() -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_dir)
        if not existing_pythonpath
        else f"{src_dir}{os.pathsep}{existing_pythonpath}"
    )

    script = "\n".join(
        [
            "import importlib",
            "import json",
            "import sys",
            "importlib.import_module('dtt_core.events')",
            "pyqt_modules = sorted(name for name in sys.modules if name == 'PyQt6' or name.startswith('PyQt6.'))",
            "print(json.dumps(pyqt_modules))",
            "raise SystemExit(1 if pyqt_modules else 0)",
        ]
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, (
        "Expected dtt_core.events import to be Qt-free. "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )


def test_stdout_event_sink_prints_non_empty_messages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sink = StdoutEventSink()

    sink.emit(
        GenerationEvent(
            stage_id=StageId.RENDER,
            kind=EventKind.LOG,
            message="rendered",
        )
    )
    sink.emit(
        GenerationEvent(
            stage_id=StageId.RENDER,
            kind=EventKind.LOG,
            message="",
        )
    )

    assert capsys.readouterr().out == "rendered\n"


def test_run_generation_process_emits_typed_done_event(
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
    save_path = _write_save(tmp_path / "event-sink.sav")

    monkeypatch.chdir(tmp_path)
    generator = TechTreeGenerator(str(cfg))
    monkeypatch.setattr(generator._config_loader, "l", lambda key, **kwargs: f"@@{key}")

    sink = RecordingEventSink()
    generator.run_generation_process(save_path=save_path, event_sink=sink)

    done_events = [
        event
        for event in sink.events
        if event.stage_id == StageId.DONE and event.kind == EventKind.PROGRESS
    ]
    assert done_events
    assert done_events[-1].progress == 100
    assert done_events[-1].message == "@@msg_generation_done"
    assert sink.events[-1].stage_id == StageId.DONE
