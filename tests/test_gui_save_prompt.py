# pyright: reportMissingImports=false

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QFileDialog, QInputDialog

import gui.generation_worker as generation_worker_module
import gui.main_window as main_window_module
from dtt_core.prepared_run import AmbiguousPlayerEmpireError
from dtt_core.save_context import SaveContext, SaveEmpireFacts
from gui.main_window import MainWindow
from gui.settings_renderer import PathFieldWidget


def _path_widget(window: MainWindow, field: str) -> PathFieldWidget:
    return cast(
        PathFieldWidget,
        window.settings_panel.settings_renderer.widget_for(f"paths.{field}"),
    )

def _configure_required_paths(window: MainWindow, tmp_path: Path) -> None:
    base_game_dir = tmp_path / "game"
    workshop_dir = tmp_path / "workshop"
    launcher_db = tmp_path / "launcher-v2.sqlite"
    base_game_dir.mkdir(exist_ok=True)
    workshop_dir.mkdir(exist_ok=True)
    launcher_db.write_text("", encoding="utf-8")
    _path_widget(window, "base_game_path").setText(str(base_game_dir))
    _path_widget(window, "mod_folder_path").setText(str(workshop_dir))
    _path_widget(window, "launcher_db_path").setText(str(launcher_db))


def _make_window(tmp_path: Path, qt_app: Any) -> MainWindow:
    settings_path = tmp_path / "settings.json"
    window = MainWindow(config_path=settings_path)
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
        def __init__(self, _settings: Any) -> None:
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


def test_gui_save_prompt_cancel_country_does_not_start_worker(
    tmp_path: Path,
    qt_app: Any,
    message_boxes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: ("", ""))

    class UnexpectedWorker:
        def __init__(self, _settings: Any) -> None:
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


def test_gui_generation_finished_error_reenables_controls_and_shows_critical(
    tmp_path: Path,
    qt_app: Any,
    message_boxes,
) -> None:
    class DummyWorker:
        def __init__(self) -> None:
            self.wait_calls = 0
            self.delete_later_calls = 0
            self._running = False

        def isRunning(self) -> bool:
            return self._running

        def cancel(self) -> None:
            self._running = False

        def wait(self, *_args: Any, **_kwargs: Any) -> bool:
            self.wait_calls += 1
            return True

        def deleteLater(self) -> None:
            self.delete_later_calls += 1

    window = _make_window(tmp_path, qt_app)
    worker = DummyWorker()
    try:
        window._set_generation_controls(True)
        window.progress_bar.setValue(37)
        message_boxes["critical"].clear()
        window.worker = cast(Any, worker)

        window.on_generation_finished(
            generation_worker_module.GenerationOutcome(
                code=generation_worker_module.GenerationOutcomeCode.ERROR,
                message="boom",
            )
        )
        qt_app.processEvents()

        assert window.generate_button.isEnabled()
        assert window.save_button.isEnabled()
        assert window.settings_profile_combo.isEnabled()
        assert window.progress_bar.value() == 37
        assert window.worker is None
        assert worker.wait_calls == 1
        assert worker.delete_later_calls == 1

        assert len(message_boxes["critical"]) == 1
        critical_args, critical_kwargs = message_boxes["critical"][0]
        assert critical_kwargs == {}
        assert critical_args[0] is window
        assert critical_args[1] == window._t("ui_msgbox_title_error")
        assert "boom" in critical_args[2]
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()


def test_gui_generation_finished_cancelled_reenables_controls_and_shows_info(
    tmp_path: Path,
    qt_app: Any,
    message_boxes,
) -> None:
    class DummyWorker:
        def __init__(self) -> None:
            self.wait_calls = 0
            self.delete_later_calls = 0
            self._running = False

        def isRunning(self) -> bool:
            return self._running

        def cancel(self) -> None:
            self._running = False

        def wait(self, *_args: Any, **_kwargs: Any) -> bool:
            self.wait_calls += 1
            return True

        def deleteLater(self) -> None:
            self.delete_later_calls += 1

    window = _make_window(tmp_path, qt_app)
    worker = DummyWorker()
    try:
        window._set_generation_controls(True)
        window.progress_bar.setValue(37)
        message_boxes["information"].clear()
        window.worker = cast(Any, worker)

        window.on_generation_finished(
            generation_worker_module.GenerationOutcome(
                code=generation_worker_module.GenerationOutcomeCode.CANCELLED,
                message="cancelled",
            )
        )
        qt_app.processEvents()

        assert window.generate_button.isEnabled()
        assert window.save_button.isEnabled()
        assert window.settings_profile_combo.isEnabled()
        assert window.progress_bar.value() == 37
        assert window.worker is None
        assert worker.wait_calls == 1
        assert worker.delete_later_calls == 1

        assert len(message_boxes["information"]) == 1
        info_args, info_kwargs = message_boxes["information"][0]
        assert info_kwargs == {}
        assert info_args[0] is window
        assert info_args[1] == window._t("ui_msgbox_title_cancelled")
        assert info_args[2] == window._t("ui_msgbox_body_generation_cancelled")
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

    run_calls: list[tuple[str, int | None]] = []

    def _run_stub(self: Any, *, save_path: str, country_id: int | None) -> bool:
        run_calls.append((save_path, country_id))
        if country_id is None:
            raise AmbiguousPlayerEmpireError(
                save_context=SaveContext(
                    save_path=save_path,
                    player_country_candidates=(7, 42),
                    empires_by_country_id={
                        7: SaveEmpireFacts(country_id=7, country_name="Alpha Union"),
                        42: SaveEmpireFacts(
                            country_id=42,
                            country_name="Beta Directorate",
                        ),
                    },
                ),
                country_candidates=(7, 42),
            )
        return True

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
        assert run_calls == [(save_path, None), (save_path, 42)]
    finally:
        window.close()
        window.deleteLater()
        qt_app.processEvents()
