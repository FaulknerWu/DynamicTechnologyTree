# pyright: reportMissingImports=false

from __future__ import annotations

import os
import warnings
from pathlib import Path

import pytest

import gui.path_detector as path_detector_module
from gui.path_detector import PathDetector
from settings import Settings


def test_detect_steam_path_windows_branch_uses_windows_detector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector = PathDetector()
    expected = r"C:\\Steam"

    monkeypatch.setattr(path_detector_module.os, "name", "nt")
    monkeypatch.setattr(detector, "_detect_steam_path_windows", lambda: expected)

    assert detector.detect_steam_path() == expected


def test_detect_all_aggregates_detected_paths_from_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    steam_root = tmp_path / "Steam"
    library_root = tmp_path / "LibraryTwo"
    user_data_root = tmp_path / "user-data"
    settings = Settings()

    (steam_root / "steamapps").mkdir(parents=True)
    (library_root / "steamapps" / "common" / settings.paths.game_directory_name).mkdir(
        parents=True
    )
    (
        library_root
        / "steamapps"
        / "workshop"
        / "content"
        / settings.paths.steam_app_id
    ).mkdir(parents=True)
    user_data_root.mkdir(parents=True)
    (user_data_root / settings.paths.launcher_db_filename).write_bytes(b"sqlite")
    (user_data_root / settings.paths.local_mod_directory_name).mkdir()

    vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
    escaped_library_path = str(library_root).replace("\\", "\\\\")
    vdf_path.write_text(
        "\n".join(
            [
                '"libraryfolders"',
                "{",
                '  "1"',
                "  {",
                f'    "path" "{escaped_library_path}"',
                "  }",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    detector = PathDetector(settings)
    monkeypatch.setattr(detector, "detect_steam_path", lambda: str(steam_root))
    monkeypatch.setattr(detector, "_user_data_candidates", lambda: [user_data_root])

    detected = detector.detect_all()

    assert detected.steam_path == str(steam_root)
    assert detected.game_path == os.path.join(
        str(library_root),
        "steamapps",
        "common",
        settings.paths.game_directory_name,
    )
    assert detected.workshop_path == os.path.join(
        str(library_root),
        "steamapps",
        "workshop",
        "content",
        settings.paths.steam_app_id,
    )
    assert detected.user_data_path == os.path.normpath(str(user_data_root))
    assert detected.launcher_db_path == os.path.join(
        str(user_data_root), settings.paths.launcher_db_filename
    )
    assert detected.local_mod_path == os.path.join(
        str(user_data_root),
        settings.paths.local_mod_directory_name,
    )


def test_path_detector_custom_app_id_affects_workshop_path(tmp_path: Path) -> None:
    library_root = tmp_path / "LibraryThree"

    custom_settings = Settings()
    custom_settings.paths.steam_app_id = "999001"
    default_settings = Settings()
    assert custom_settings.paths.steam_app_id != default_settings.paths.steam_app_id

    (
        library_root
        / "steamapps"
        / "workshop"
        / "content"
        / custom_settings.paths.steam_app_id
    ).mkdir(parents=True)

    custom_detector = PathDetector(custom_settings)
    default_detector = PathDetector(default_settings)

    assert (
        default_detector._detect_workshop_path_from_libraries([str(library_root)])
        is None
    )
    assert custom_detector._detect_workshop_path_from_libraries(
        [str(library_root)]
    ) == os.path.join(
        str(library_root),
        "steamapps",
        "workshop",
        "content",
        custom_settings.paths.steam_app_id,
    )


def test_path_detector_missing_metadata_returns_none_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector = PathDetector()
    missing_user_data = tmp_path / "missing-user-data"

    monkeypatch.setattr(path_detector_module.os, "name", "nt")
    monkeypatch.setattr(detector, "_detect_steam_path_windows", lambda: None)
    monkeypatch.setattr(detector, "_user_data_candidates", lambda: [missing_user_data])

    detected = detector.detect_all()

    assert detected.steam_path is None
    assert detected.game_path is None
    assert detected.workshop_path is None
    assert detected.user_data_path is None
    assert detected.launcher_db_path is None
    assert detected.local_mod_path is None


def test_parse_library_folders_missing_vdf_returns_empty_list(tmp_path: Path) -> None:
    detector = PathDetector()
    missing_vdf = tmp_path / "steamapps" / "libraryfolders.vdf"

    assert detector._parse_library_folders(str(missing_vdf)) == []


def test_parse_library_folders_os_error_returns_empty_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector = PathDetector()
    vdf_path = tmp_path / "libraryfolders.vdf"
    vdf_path.write_text('"libraryfolders" {}', encoding="utf-8")

    def _raise_os_error(_path: Path, *args, **kwargs):
        raise OSError("read failed")

    monkeypatch.setattr(
        path_detector_module, "read_text_with_diagnostics", _raise_os_error
    )

    assert detector._parse_library_folders(str(vdf_path)) == []


def test_parse_library_folders_decode_warning_emits_runtime_warning(
    tmp_path: Path,
) -> None:
    detector = PathDetector()
    library_root = tmp_path / "LibraryFallback"
    vdf_path = tmp_path / "libraryfolders.vdf"

    vdf_payload = (
        b'"libraryfolders"\n{\n'
        b'  "1"\n  {\n'
        b'    "path" "' + str(library_root).encode("utf-8") + b'"\n'
        b"  }\n"
        b"}\n"
        b"\x80"
    )
    vdf_path.write_bytes(vdf_payload)

    with pytest.warns(RuntimeWarning, match="fallback encoding cp1252"):
        paths = detector._parse_library_folders(str(vdf_path))

    assert paths == [os.path.normpath(str(library_root))]


def test_parse_library_folders_malformed_vdf_returns_empty_without_warning(
    tmp_path: Path,
) -> None:
    detector = PathDetector()
    vdf_path = tmp_path / "libraryfolders.vdf"
    vdf_path.write_text(
        '"libraryfolders" { "1" { "label" "no path" } }', encoding="utf-8"
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        paths = detector._parse_library_folders(str(vdf_path))

    runtime_warnings = [
        warning for warning in caught if issubclass(warning.category, RuntimeWarning)
    ]
    assert paths == []
    assert runtime_warnings == []
