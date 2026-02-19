# pyright: reportMissingImports=false

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

import gui.generation_worker as generation_worker_module
import gui.main_window as main_window_module
from dtt_core.save_context import SaveContext, SaveEmpireFacts
from gui.main_window import MainWindow


@pytest.fixture(scope="session")
def qt_app() -> Any:
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
    calls: dict[str, list[tuple[tuple[Any, ...], dict[str, Any]]]] = {
        "warning": [],
        "critical": [],
        "information": [],
    }

    def _stub(kind: str) -> Callable[..., Any]:
        def _impl(*args: Any, **kwargs: Any) -> Any:
            calls[kind].append((args, kwargs))
            return QMessageBox.StandardButton.Ok

        return _impl

    monkeypatch.setattr(QMessageBox, "warning", _stub("warning"))
    monkeypatch.setattr(QMessageBox, "critical", _stub("critical"))
    monkeypatch.setattr(QMessageBox, "information", _stub("information"))
    return calls


def _configure_required_paths(window: MainWindow, tmp_path: Path) -> None:
    base_game_dir = tmp_path / "game"
    workshop_dir = tmp_path / "workshop"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    base_game_dir.mkdir(exist_ok=True)
    workshop_dir.mkdir(exist_ok=True)
    launcher_db.write_text("", encoding="utf-8")
    window.config_editor.base_game_path_input.setText(str(base_game_dir))
    window.config_editor.mod_folder_path_input.setText(str(workshop_dir))
    window.config_editor.launcher_db_path_input.setText(str(launcher_db))


def _make_window(tmp_path: Path, qt_app: Any) -> MainWindow:
    cfg_path = tmp_path / "config.ini"
    window = MainWindow(config_path=cfg_path)
    window.show()
    qt_app.processEvents()
    _configure_required_paths(window, tmp_path)
    qt_app.processEvents()
    return window


class _Signal:
    def __init__(self) -> None:
        self._slots: list[Callable[..., Any]] = []

    def connect(self, slot: Callable[..., Any]) -> None:
        self._slots.append(slot)

    def emit(self, *args: Any, **kwargs: Any) -> None:
        for slot in list(self._slots):
            slot(*args, **kwargs)


def test_generate_prompts_for_save_on_every_run(
    tmp_path: Path,
    qt_app: Any,
    message_boxes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_path = str(tmp_path / "chosen.sav")
    dialog_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def _stub_save_dialog(*args: Any, **kwargs: Any) -> tuple[str, str]:
        dialog_calls.append((args, kwargs))
        return save_path, "Stellaris Save Files (*.sav)"

    monkeypatch.setattr(QFileDialog, "getOpenFileName", _stub_save_dialog)

    created_workers: list[Any] = []

    class DummyWorker:
        def __init__(self, _config_path: str) -> None:
            self.log_message = _Signal()
            self.progress = _Signal()
            self.finished = _Signal()
            self._running = False
            created_workers.append(self)

        def start(self) -> None:
            self._running = True
            self.finished.emit(
                generation_worker_module.GenerationOutcome(
                    code=generation_worker_module.GenerationOutcomeCode.SUCCESS,
                )
            )
            self._running = False

        def isRunning(self) -> bool:
            return self._running

        def cancel(self) -> None:
            self._running = False

        def wait(self, *_args: Any, **_kwargs: Any) -> bool:
            self._running = False
            return True

        def deleteLater(self) -> None:
            return

    monkeypatch.setattr(main_window_module, "GenerationWorker", DummyWorker)

    window = _make_window(tmp_path, qt_app)
    try:
        window.on_generate_clicked()
        qt_app.processEvents()

        window.on_generate_clicked()
        qt_app.processEvents()

        assert len(dialog_calls) == 2
        assert len(created_workers) == 2
        assert [worker.save_path for worker in created_workers] == [
            save_path,
            save_path,
        ]
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_generate_cancelled_save_dialog_does_not_start_worker(
    tmp_path: Path,
    qt_app: Any,
    message_boxes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: ("", ""))

    class UnexpectedWorker:
        def __init__(self, _config_path: str) -> None:
            raise AssertionError(
                "worker should not be created when save selection is cancelled"
            )

    monkeypatch.setattr(main_window_module, "GenerationWorker", UnexpectedWorker)

    window = _make_window(tmp_path, qt_app)
    try:
        window.on_generate_clicked()
        qt_app.processEvents()

        assert window.worker is None
        assert window.generate_button.isEnabled()
        assert window.save_button.isEnabled()
        assert not message_boxes["critical"]
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_ambiguous_save_shows_empire_chooser_and_passes_selected_country_id(
    tmp_path: Path,
    qt_app: Any,
    message_boxes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_path = str(tmp_path / "ambiguous.sav")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *_a, **_k: (save_path, "")
    )

    chooser_calls: list[tuple[str, str, list[str]]] = []

    def _stub_empire_chooser(
        _parent: Any,
        title: str,
        label: str,
        items: list[str],
        _current: int,
        _editable: bool,
    ) -> tuple[str, bool]:
        chooser_calls.append((title, label, list(items)))
        assert list(items) == ["7 - Alpha Union", "42 - Beta Directorate"]
        return "42 - Beta Directorate", True

    monkeypatch.setattr(QInputDialog, "getItem", _stub_empire_chooser)

    def _inspect_stub(self: Any, inspected_path: str) -> SaveContext:
        return SaveContext(
            save_path=inspected_path,
            player_country_candidates=(7, 42),
            empires_by_country_id={
                7: SaveEmpireFacts(country_id=7, country_name="Alpha Union"),
                42: SaveEmpireFacts(country_id=42, country_name="Beta Directorate"),
            },
        )

    run_calls: list[tuple[str, int | None]] = []

    def _run_stub(self: Any, *, save_path: str, country_id: int | None) -> bool:
        run_calls.append((save_path, country_id))
        return True

    monkeypatch.setattr(
        generation_worker_module.GenerationWorker,
        "_inspect_save_context",
        _inspect_stub,
    )
    monkeypatch.setattr(
        generation_worker_module.GenerationWorker,
        "_run_generator",
        _run_stub,
    )
    monkeypatch.setattr(
        generation_worker_module.GenerationWorker,
        "start",
        lambda self: self.run(),
    )
    monkeypatch.setattr(
        generation_worker_module.GenerationWorker,
        "wait",
        lambda self, *_a, **_k: True,
    )
    monkeypatch.setattr(
        generation_worker_module.GenerationWorker,
        "deleteLater",
        lambda self: None,
    )

    window = _make_window(tmp_path, qt_app)
    try:
        window.on_generate_clicked()
        qt_app.processEvents()

        assert len(chooser_calls) == 1
        assert run_calls == [(save_path, 42)]
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()
