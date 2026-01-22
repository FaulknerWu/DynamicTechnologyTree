from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

STEAM_APP_ID = "281990"
GAME_DIR_NAME = "Stellaris"
USER_DATA_SUBPATH = os.path.join("Paradox Interactive", "Stellaris")


@dataclass
class DetectedPaths:
    steam_path: str | None
    game_path: str | None
    workshop_path: str | None
    user_data_path: str | None
    dlc_load_path: str | None
    local_mod_path: str | None


class PathDetector:
    def detect_all(self) -> DetectedPaths:
        steam_path = self.detect_steam_path()
        library_paths = self._steam_library_paths(steam_path)
        game_path = self._detect_game_path_from_libraries(library_paths)
        workshop_path = self._detect_workshop_path_from_libraries(library_paths)
        user_data_path = self.detect_user_data_path()
        dlc_load_path = self._detect_dlc_load_path(user_data_path)
        local_mod_path = self._detect_local_mod_path(user_data_path)
        return DetectedPaths(
            steam_path=steam_path,
            game_path=game_path,
            workshop_path=workshop_path,
            user_data_path=user_data_path,
            dlc_load_path=dlc_load_path,
            local_mod_path=local_mod_path,
        )

    def detect_steam_path(self) -> str | None:
        if os.name == "nt":
            return self._detect_steam_path_windows()
        if sys.platform == "darwin":
            return self._first_existing_path(
                [Path.home() / "Library" / "Application Support" / "Steam"]
            )
        return self._first_existing_path(
            [
                Path.home() / ".local" / "share" / "Steam",
                Path.home() / ".steam" / "steam",
                Path.home() / ".steam" / "root",
                Path.home()
                / ".var"
                / "app"
                / "com.valvesoftware.Steam"
                / ".local"
                / "share"
                / "Steam",
                Path.home() / "snap" / "steam" / "common" / ".steam" / "steam",
                Path.home()
                / "snap"
                / "steam"
                / "common"
                / ".local"
                / "share"
                / "Steam",
            ]
        )

    def detect_game_path(self) -> str | None:
        library_paths = self._steam_library_paths(self.detect_steam_path())
        return self._detect_game_path_from_libraries(library_paths)

    def detect_workshop_path(self) -> str | None:
        library_paths = self._steam_library_paths(self.detect_steam_path())
        return self._detect_workshop_path_from_libraries(library_paths)

    def detect_user_data_path(self) -> str | None:
        candidates = self._user_data_candidates()
        return self._first_existing_path(candidates)

    def detect_dlc_load_path(self) -> str | None:
        return self._detect_dlc_load_path(self.detect_user_data_path())

    def detect_local_mod_path(self) -> str | None:
        return self._detect_local_mod_path(self.detect_user_data_path())

    def _user_data_candidates(self) -> list[Path]:
        home = Path.home()
        if os.name == "nt":
            return [home / "Documents" / USER_DATA_SUBPATH]
        if sys.platform == "darwin":
            return [
                home / "Documents" / USER_DATA_SUBPATH,
                home / "Library" / "Application Support" / USER_DATA_SUBPATH,
            ]
        return [
            home / ".local" / "share" / USER_DATA_SUBPATH,
            home / "Documents" / USER_DATA_SUBPATH,
        ]

    def _detect_dlc_load_path(self, user_data_path: str | None) -> str | None:
        if not user_data_path:
            return None
        candidate = os.path.join(user_data_path, "dlc_load.json")
        return candidate if os.path.exists(candidate) else None

    def _detect_local_mod_path(self, user_data_path: str | None) -> str | None:
        if not user_data_path:
            return None
        candidate = os.path.join(user_data_path, "mod")
        return candidate if os.path.exists(candidate) else None

    def _detect_game_path_from_libraries(self, library_paths: list[str]) -> str | None:
        for library_path in library_paths:
            candidate = os.path.join(library_path, "steamapps", "common", GAME_DIR_NAME)
            if os.path.exists(candidate):
                return candidate
        return None

    def _detect_workshop_path_from_libraries(
        self, library_paths: list[str]
    ) -> str | None:
        for library_path in library_paths:
            candidate = os.path.join(
                library_path, "steamapps", "workshop", "content", STEAM_APP_ID
            )
            if os.path.exists(candidate):
                return candidate
        return None

    def _steam_library_paths(self, steam_path: str | None) -> list[str]:
        paths: list[str] = []
        seen: set[str] = set()

        def add_path(candidate: str | None) -> None:
            if candidate and candidate not in seen and os.path.exists(candidate):
                paths.append(candidate)
                seen.add(candidate)

        if not steam_path:
            return paths

        add_path(steam_path)
        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        for path in self._parse_library_folders(vdf_path):
            add_path(path)
        return paths

    def _parse_library_folders(self, vdf_path: str) -> list[str]:
        if not os.path.exists(vdf_path):
            return []
        try:
            text = Path(vdf_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
        matches = re.findall(r'"path"\s*"([^"]+)"', text, flags=re.IGNORECASE)
        paths = []
        for raw in matches:
            cleaned = raw.replace("\\\\", "\\").strip()
            if cleaned:
                paths.append(os.path.normpath(cleaned))
        return paths

    def _detect_steam_path_windows(self) -> str | None:
        if os.name != "nt":
            return None
        try:
            import winreg
        except ImportError:
            return None
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\Valve\Steam",
            ) as key:
                value, _value_type = winreg.QueryValueEx(key, "InstallPath")
            candidate = os.path.normpath(value)
            return candidate if os.path.exists(candidate) else None
        except OSError:
            return None

    def _first_existing_path(self, candidates: list[Path]) -> str | None:
        for candidate in candidates:
            path_str = os.path.normpath(os.path.expanduser(str(candidate)))
            if os.path.exists(path_str):
                return path_str
        return None
