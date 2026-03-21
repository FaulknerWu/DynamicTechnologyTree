from __future__ import annotations

"""集中管理 core typed error_code 到本地化 key 的映射（SSOT）。"""

_ERROR_CODE_TO_LOCALIZATION_KEY: dict[str, str] = {
    "technology_swap_collision": "ui_error_technology_swap_collision",
    "missing_database_path": "ui_error_launcher_db_missing_database_path",
    "empty_database_path": "ui_error_launcher_db_empty_database_path",
    "missing_database": "ui_error_launcher_db_missing_database",
    "database_not_file": "ui_error_launcher_db_not_a_file",
    "database_locked": "ui_error_launcher_db_locked",
    "open_failed": "ui_error_launcher_db_open_failed",
    "read_failed": "ui_error_launcher_db_read_failed",
    "corrupt_database": "ui_error_launcher_db_corrupt",
    "database_error": "ui_error_launcher_db_query_failed",
    "schema_playsets_missing": "ui_error_launcher_db_schema_missing_table",
    "schema_playsets_mods_missing": "ui_error_launcher_db_schema_missing_table",
    "schema_mods_missing": "ui_error_launcher_db_schema_missing_table",
    "schema_playsets_columns": "ui_error_launcher_db_schema_missing_columns",
    "schema_playsets_mods_columns": "ui_error_launcher_db_schema_missing_columns",
    "schema_mods_columns": "ui_error_launcher_db_schema_missing_columns",
    "no_active_playset": "ui_error_launcher_db_no_active_playset",
}


def localization_key_for_error_code(error_code: str) -> str | None:
    code = str(error_code).strip()
    if not code:
        return None
    return _ERROR_CODE_TO_LOCALIZATION_KEY.get(code)


__all__ = ["localization_key_for_error_code"]

