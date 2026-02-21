# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

import gui as gui_module


def test_gui_runtime_paths_no_ini_fallback_uses_json_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime_cwd = tmp_path / "runtime-cwd"
    runtime_cwd.mkdir()
    (runtime_cwd / "config.ini").write_text("[paths]\n", encoding="utf-8")

    expected_settings_path = tmp_path / "user-config" / "settings.json"
    monkeypatch.chdir(runtime_cwd)
    monkeypatch.setattr(
        gui_module,
        "_default_settings_path",
        lambda: expected_settings_path,
    )
    monkeypatch.setattr(gui_module, "_find_project_root", lambda _start: None)
    monkeypatch.setattr(gui_module.sys, "frozen", False, raising=False)

    paths = gui_module._resolve_runtime_paths()

    assert paths.application_path == runtime_cwd
    assert paths.settings_path == expected_settings_path
    assert paths.settings_path.suffix == ".json"
