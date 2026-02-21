# pyright: reportMissingImports=false

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import gui as gui_module


def test_gui_no_chdir_startup_keeps_process_cwd_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_cwd = tmp_path / "runtime-cwd"
    runtime_cwd.mkdir(parents=True)
    monkeypatch.chdir(runtime_cwd)
    starting_cwd = os.getcwd()

    application_root = tmp_path / "application-root"
    application_root.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(
        gui_module,
        "_resolve_runtime_paths",
        lambda: gui_module.RuntimePaths(
            application_path=application_root,
            settings_path=settings_path,
        ),
    )

    captured: dict[str, Any] = {"show_called": False}

    class DummyWindow:
        def __init__(
            self,
            config_path: str | os.PathLike[str] | None = None,
            application_path: str | os.PathLike[str] | None = None,
        ) -> None:
            captured["config_path"] = Path(config_path) if config_path else None
            captured["application_path"] = (
                Path(application_path) if application_path else None
            )

        def show(self) -> None:
            captured["show_called"] = True

    class DummyApplication:
        def __init__(self, _argv: list[str]) -> None:
            return

        def exec(self) -> int:
            raise AssertionError("QApplication.exec must be patched by test")

    monkeypatch.setattr(DummyApplication, "exec", lambda _self: 0)
    monkeypatch.setattr(gui_module, "QApplication", DummyApplication)
    monkeypatch.setattr(gui_module, "MainWindow", DummyWindow)

    import gui.fonts as fonts_module

    monkeypatch.setattr(fonts_module, "load_fonts", lambda: False)
    monkeypatch.setattr(fonts_module, "set_default_font", lambda _app: None)

    def _forbid_chdir(_target: str) -> None:
        raise AssertionError("gui.main must not call os.chdir")

    monkeypatch.setattr(os, "chdir", _forbid_chdir)

    exit_code = gui_module.main()

    assert exit_code == 0
    assert os.getcwd() == starting_cwd
    assert captured["show_called"] is True
    assert captured["config_path"] == settings_path
    assert captured["application_path"] == application_root
