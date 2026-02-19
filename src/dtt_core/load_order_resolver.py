from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any, Optional
import warnings as py_warnings


@dataclass(frozen=True)
class ResolvedModEntry:
    raw_entry: str
    mod_id: str = ""
    dir_path: str = ""
    game_registry_id: str = ""
    steam_id: str = ""
    pdx_id: str = ""


@dataclass
class LoadOrderResolution:
    source: str
    entries: list[ResolvedModEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    database_path: Optional[Path] = None
    migration_names: list[str] = field(default_factory=list)

    @property
    def enabled_mods(self) -> list[str]:
        return [entry.raw_entry for entry in self.entries]


class LoadOrderResolutionError(RuntimeError):
    def __init__(self, *, code: str, database_path: Path, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.database_path = database_path


class LoadOrderResolver:
    def resolve_enabled_mods(
        self,
        launcher_db_path: str | Path | None,
    ) -> LoadOrderResolution:
        db_path = self._normalize_database_path(launcher_db_path)
        if not db_path.exists():
            raise LoadOrderResolutionError(
                code="missing_database",
                database_path=db_path,
                message=(
                    f"Launcher DB not found at {db_path}. "
                    "Set [paths] launcher_db_path to launcher-v2.sqlite."
                ),
            )
        if not db_path.is_file():
            raise LoadOrderResolutionError(
                code="database_not_file",
                database_path=db_path,
                message=(
                    f"Launcher DB path is not a file: {db_path}. "
                    "Set [paths] launcher_db_path to launcher-v2.sqlite."
                ),
            )

        warnings: list[str] = []
        conn = self._open_read_only_connection(db_path)
        conn.row_factory = sqlite3.Row
        try:
            migration_names = self._read_migration_names(conn, warnings)
            playset_columns = self._table_columns(conn, "playsets")
            playset_mod_columns = self._table_columns(conn, "playsets_mods")
            mod_columns = self._table_columns(conn, "mods")

            active_playset_id = self._select_active_playset_id(
                conn,
                playset_columns,
                warnings,
                db_path,
            )

            entries = self._read_playset_mod_entries(
                conn,
                active_playset_id,
                playset_mod_columns,
                mod_columns,
                warnings,
                db_path,
            )

            return LoadOrderResolution(
                source=db_path.name,
                entries=entries,
                warnings=warnings,
                database_path=db_path,
                migration_names=migration_names,
            )
        except sqlite3.OperationalError as exc:
            raise self._map_operational_error(db_path, exc) from exc
        except sqlite3.DatabaseError as exc:
            raise self._map_database_error(db_path, exc) from exc
        finally:
            conn.close()

    def _normalize_database_path(self, launcher_db_path: str | Path | None) -> Path:
        if launcher_db_path is None:
            raise LoadOrderResolutionError(
                code="missing_database_path",
                database_path=Path("<unset>"),
                message=(
                    "Missing [paths] launcher_db_path in config. "
                    "Set it to the launcher-v2.sqlite file path."
                ),
            )

        path_text = str(launcher_db_path).strip()
        if not path_text:
            raise LoadOrderResolutionError(
                code="empty_database_path",
                database_path=Path("<unset>"),
                message=(
                    "[paths] launcher_db_path is empty. "
                    "Set it to the launcher-v2.sqlite file path."
                ),
            )
        return Path(path_text).expanduser()

    def _open_read_only_connection(self, db_path: Path) -> sqlite3.Connection:
        try:
            return sqlite3.connect(
                f"file:{db_path.as_posix()}?mode=ro",
                uri=True,
            )
        except sqlite3.OperationalError as exc:
            raise self._map_operational_error(db_path, exc) from exc
        except sqlite3.DatabaseError as exc:
            raise self._map_database_error(db_path, exc) from exc

    def _map_operational_error(
        self,
        db_path: Path,
        exc: sqlite3.OperationalError,
    ) -> LoadOrderResolutionError:
        text = str(exc).strip()
        lowered = text.casefold()

        if "locked" in lowered:
            return LoadOrderResolutionError(
                code="database_locked",
                database_path=db_path,
                message=(
                    f"Launcher DB is locked at {db_path}: {text}. "
                    "Close Paradox Launcher or wait for it to finish writing, then retry."
                ),
            )
        if "unable to open database file" in lowered:
            return LoadOrderResolutionError(
                code="open_failed",
                database_path=db_path,
                message=(
                    f"Failed to open launcher DB at {db_path}: {text}. "
                    "Check file permissions and verify launcher_db_path points to launcher-v2.sqlite."
                ),
            )

        return LoadOrderResolutionError(
            code="read_failed",
            database_path=db_path,
            message=(
                f"Failed to read launcher DB at {db_path}: {text}. "
                "Verify the launcher-v2.sqlite file is readable."
            ),
        )

    def _map_database_error(
        self,
        db_path: Path,
        exc: sqlite3.DatabaseError,
    ) -> LoadOrderResolutionError:
        text = str(exc).strip()
        lowered = text.casefold()

        if "file is not a database" in lowered or "malformed" in lowered:
            return LoadOrderResolutionError(
                code="corrupt_database",
                database_path=db_path,
                message=(
                    f"Launcher DB at {db_path} is corrupt: {text}. "
                    "Point launcher_db_path to a valid launcher-v2.sqlite file."
                ),
            )

        return LoadOrderResolutionError(
            code="database_error",
            database_path=db_path,
            message=(
                f"Launcher DB query failed at {db_path}: {text}. "
                "Verify launcher-v2.sqlite is valid and not being modified."
            ),
        )

    def _read_migration_names(
        self,
        conn: sqlite3.Connection,
        warnings: list[str],
    ) -> list[str]:
        migration_columns = self._table_columns(conn, "knex_migrations")
        if not migration_columns:
            return []

        name_column = self._pick_column(migration_columns, "name")
        if name_column is None:
            warnings.append("knex_migrations table exists but has no name column.")
            return []
        id_column = self._pick_column(migration_columns, "id")

        order_clause = (
            self._quote_identifier(id_column)
            if id_column
            else self._quote_identifier(name_column)
        )
        sql = (
            f"SELECT {self._quote_identifier(name_column)} AS migration_name "
            f"FROM {self._quote_identifier('knex_migrations')} "
            f"ORDER BY {order_clause}"
        )
        rows = conn.execute(sql).fetchall()
        return [
            self._safe_str(row["migration_name"])
            for row in rows
            if row["migration_name"] is not None
        ]

    def _select_active_playset_id(
        self,
        conn: sqlite3.Connection,
        playset_columns: dict[str, str],
        warnings: list[str],
        db_path: Path,
    ) -> str:
        if not playset_columns:
            raise LoadOrderResolutionError(
                code="schema_playsets_missing",
                database_path=db_path,
                message=(
                    "Launcher DB schema drift: missing playsets table. "
                    "Verify launcher-v2.sqlite matches current launcher format."
                ),
            )

        playset_id_column = self._pick_column(
            playset_columns, "id", "playsetId", "playset_id"
        )
        is_active_column = self._pick_column(playset_columns, "isActive", "is_active")
        if playset_id_column is None or is_active_column is None:
            raise LoadOrderResolutionError(
                code="schema_playsets_columns",
                database_path=db_path,
                message=(
                    "Launcher DB schema drift: playsets table missing id/isActive columns. "
                    "Verify launcher-v2.sqlite matches current launcher format."
                ),
            )

        name_column = self._pick_column(playset_columns, "name", "displayName")
        created_on_column = self._pick_column(
            playset_columns, "createdOn", "created_on"
        )
        is_removed_column = self._pick_column(
            playset_columns, "isRemoved", "is_removed"
        )

        select_parts = [f"{self._quote_identifier(playset_id_column)} AS playset_id"]
        if name_column is None:
            select_parts.append("'' AS playset_name")
        else:
            select_parts.append(
                f"{self._quote_identifier(name_column)} AS playset_name"
            )
        if created_on_column is None:
            select_parts.append("NULL AS created_on")
        else:
            select_parts.append(
                f"{self._quote_identifier(created_on_column)} AS created_on"
            )

        sql = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM {self._quote_identifier('playsets')} "
            f"WHERE {self._quote_identifier(is_active_column)} = 1"
        )
        if is_removed_column is not None:
            sql += f" AND COALESCE({self._quote_identifier(is_removed_column)}, 0) = 0"

        rows = conn.execute(sql).fetchall()
        if not rows:
            raise LoadOrderResolutionError(
                code="no_active_playset",
                database_path=db_path,
                message=(
                    "No active playset found in launcher DB. "
                    "Open Paradox Launcher, select an active playset, and retry."
                ),
            )
        if len(rows) == 1:
            return self._safe_str(rows[0]["playset_id"])

        message = f"Multiple active playsets detected ({len(rows)}); selected deterministically."
        warnings.append(message)
        py_warnings.warn(message, RuntimeWarning, stacklevel=2)

        if created_on_column is not None:
            created_keys = [self._created_sort_key(row["created_on"]) for row in rows]
            latest_key = max(created_keys)
            candidates = [
                row
                for row in rows
                if self._created_sort_key(row["created_on"]) == latest_key
            ]
        else:
            candidates = list(rows)

        chosen = min(
            candidates,
            key=lambda row: (
                self._safe_str(row["playset_name"]).casefold(),
                self._safe_str(row["playset_id"]),
            ),
        )
        return self._safe_str(chosen["playset_id"])

    def _read_playset_mod_entries(
        self,
        conn: sqlite3.Connection,
        playset_id: str,
        playset_mod_columns: dict[str, str],
        mod_columns: dict[str, str],
        warnings: list[str],
        db_path: Path,
    ) -> list[ResolvedModEntry]:
        if not playset_mod_columns:
            raise LoadOrderResolutionError(
                code="schema_playsets_mods_missing",
                database_path=db_path,
                message=(
                    "Launcher DB schema drift: missing playsets_mods table. "
                    "Verify launcher-v2.sqlite matches current launcher format."
                ),
            )
        if not mod_columns:
            raise LoadOrderResolutionError(
                code="schema_mods_missing",
                database_path=db_path,
                message=(
                    "Launcher DB schema drift: missing mods table. "
                    "Verify launcher-v2.sqlite matches current launcher format."
                ),
            )

        pm_playset_id_column = self._pick_column(
            playset_mod_columns, "playsetId", "playset_id"
        )
        pm_mod_id_column = self._pick_column(playset_mod_columns, "modId", "mod_id")
        pm_enabled_column = self._pick_column(
            playset_mod_columns, "enabled", "isEnabled", "is_enabled"
        )
        pm_position_column = self._pick_column(
            playset_mod_columns, "position", "loadOrder", "load_order"
        )
        mods_id_column = self._pick_column(mod_columns, "id", "modId", "mod_id")

        if pm_playset_id_column is None or pm_mod_id_column is None:
            raise LoadOrderResolutionError(
                code="schema_playsets_mods_columns",
                database_path=db_path,
                message=(
                    "Launcher DB schema drift: playsets_mods table missing playsetId/modId columns. "
                    "Verify launcher-v2.sqlite matches current launcher format."
                ),
            )
        if mods_id_column is None:
            raise LoadOrderResolutionError(
                code="schema_mods_columns",
                database_path=db_path,
                message=(
                    "Launcher DB schema drift: mods table missing id column. "
                    "Verify launcher-v2.sqlite matches current launcher format."
                ),
            )

        mods_dir_path_column = self._pick_column(mod_columns, "dirPath", "dir_path")
        mods_game_registry_column = self._pick_column(
            mod_columns,
            "gameRegistryId",
            "game_registry_id",
        )
        mods_steam_column = self._pick_column(mod_columns, "steamId", "steam_id")
        mods_pdx_column = self._pick_column(mod_columns, "pdxId", "pdx_id")

        select_parts = [
            f"pm.{self._quote_identifier(pm_mod_id_column)} AS mod_id",
            "NULL AS enabled_value",
            "NULL AS position_value",
            "'' AS dir_path",
            "'' AS game_registry_id",
            "'' AS steam_id",
            "'' AS pdx_id",
        ]
        if pm_enabled_column is not None:
            select_parts[1] = (
                f"pm.{self._quote_identifier(pm_enabled_column)} AS enabled_value"
            )
        if pm_position_column is not None:
            select_parts[2] = (
                f"pm.{self._quote_identifier(pm_position_column)} AS position_value"
            )
        if mods_dir_path_column is not None:
            select_parts[3] = (
                f"m.{self._quote_identifier(mods_dir_path_column)} AS dir_path"
            )
        if mods_game_registry_column is not None:
            select_parts[4] = (
                f"m.{self._quote_identifier(mods_game_registry_column)} AS game_registry_id"
            )
        if mods_steam_column is not None:
            select_parts[5] = (
                f"m.{self._quote_identifier(mods_steam_column)} AS steam_id"
            )
        if mods_pdx_column is not None:
            select_parts[6] = f"m.{self._quote_identifier(mods_pdx_column)} AS pdx_id"

        sql = (
            f"SELECT {', '.join(select_parts)} "
            f"FROM {self._quote_identifier('playsets_mods')} pm "
            f"LEFT JOIN {self._quote_identifier('mods')} m "
            f"ON pm.{self._quote_identifier(pm_mod_id_column)} = m.{self._quote_identifier(mods_id_column)} "
            f"WHERE pm.{self._quote_identifier(pm_playset_id_column)} = ?"
        )

        rows = conn.execute(sql, (playset_id,)).fetchall()
        if pm_enabled_column is not None:
            rows = [row for row in rows if self._is_enabled_value(row["enabled_value"])]

        sorted_rows = sorted(
            rows,
            key=lambda row: (
                self._position_sort_key(row["position_value"]),
                self._safe_str(row["mod_id"]),
            ),
        )

        entries: list[ResolvedModEntry] = []
        for row in sorted_rows:
            mod_id = self._safe_str(row["mod_id"])
            dir_path = self._safe_str(row["dir_path"])
            game_registry_id = self._safe_str(row["game_registry_id"])
            steam_id = self._safe_str(row["steam_id"])
            pdx_id = self._safe_str(row["pdx_id"])
            raw_entry = dir_path or game_registry_id or steam_id or pdx_id or mod_id
            entries.append(
                ResolvedModEntry(
                    raw_entry=raw_entry,
                    mod_id=mod_id,
                    dir_path=dir_path,
                    game_registry_id=game_registry_id,
                    steam_id=steam_id,
                    pdx_id=pdx_id,
                )
            )
        return entries

    def _table_columns(
        self, conn: sqlite3.Connection, table_name: str
    ) -> dict[str, str]:
        sql = f"PRAGMA table_info({self._quote_identifier(table_name)})"
        rows = conn.execute(sql).fetchall()
        columns: dict[str, str] = {}
        for row in rows:
            name = self._safe_str(row["name"])
            if name:
                columns[name.lower()] = name
        return columns

    def _pick_column(self, columns: dict[str, str], *candidates: str) -> Optional[str]:
        for candidate in candidates:
            selected = columns.get(candidate.lower())
            if selected is not None:
                return selected
        return None

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    @staticmethod
    def _safe_str(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _is_enabled_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return int(value) != 0
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _position_sort_key(value: Any) -> tuple[int, int, str]:
        if value is None:
            return (2, 0, "")
        if isinstance(value, bool):
            return (0, int(value), str(int(value)))
        if isinstance(value, int):
            return (0, value, str(value))
        if isinstance(value, float):
            numeric = int(value)
            return (0, numeric, str(numeric))
        text = str(value).strip()
        if text and (text.isdigit() or (text[0] == "-" and text[1:].isdigit())):
            return (0, int(text), text)
        if text:
            return (1, 0, text.casefold())
        return (2, 0, "")

    @staticmethod
    def _created_sort_key(value: Any) -> tuple[int, float, str]:
        if value is None:
            return (0, 0.0, "")
        if isinstance(value, bool):
            return (2, float(int(value)), "")
        if isinstance(value, (int, float)):
            return (2, float(value), "")

        text = str(value).strip()
        if not text:
            return (0, 0.0, "")
        if text.isdigit() or (text[0] == "-" and text[1:].isdigit()):
            return (2, float(int(text)), "")
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return (3, parsed.timestamp(), "")
        except ValueError:
            return (1, 0.0, text.casefold())
