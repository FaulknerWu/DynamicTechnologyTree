from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

from settings import Settings

CURRENT_SCHEMA_VERSION = Settings().schema_version
SUPPORTED_SCHEMA_VERSIONS = frozenset({CURRENT_SCHEMA_VERSION})

ErrorPath = tuple[str | int, ...]


class SettingsStoreError(Exception):
    def __init__(
        self,
        message: str,
        *,
        kind: str,
        path: ErrorPath | None = None,
        pydantic_errors: list[dict[str, Any]] | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.path = path
        self.pydantic_errors = pydantic_errors
        self.line = line
        self.column = column

    def to_dict(self) -> dict[str, Any]:
        details: dict[str, Any] = {"kind": self.kind}
        if self.path is not None:
            details["path"] = list(self.path)
        if self.pydantic_errors is not None:
            details["pydantic_errors"] = self.pydantic_errors
        if self.line is not None:
            details["line"] = self.line
        if self.column is not None:
            details["column"] = self.column
        return {"message": self.message, "details": details}


def load_settings(path: str | Path) -> Settings:
    settings_path = Path(path)

    try:
        raw_text = settings_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SettingsStoreError(
            f"Could not read settings file: {settings_path}",
            kind="io_read_error",
        ) from exc

    payload = _parse_json_payload(raw_text)
    _require_schema_version(payload)

    try:
        settings = Settings.model_validate(payload, strict=True)
    except ValidationError as exc:
        raise _build_validation_error(exc) from exc

    if settings.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SettingsStoreError(
            (
                "Unsupported settings schema_version "
                f"{settings.schema_version}; expected one of "
                f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            ),
            kind="unsupported_schema_version",
            path=("schema_version",),
        )

    return settings


def save_settings(path: str | Path, settings: Settings) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    payload_json = settings.model_dump_json(indent=2)
    if not payload_json.endswith("\n"):
        payload_json += "\n"

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=settings_path.parent,
            prefix=f".{settings_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload_json)
            handle.flush()
            temp_path = Path(handle.name)
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass

        if temp_path is None:
            raise SettingsStoreError(
                "Could not write settings file due to missing temp path",
                kind="io_write_error",
            )

        os.replace(temp_path, settings_path)
    except OSError as exc:
        raise SettingsStoreError(
            f"Could not write settings file: {settings_path}",
            kind="io_write_error",
        ) from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _parse_json_payload(raw_text: str) -> Any:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SettingsStoreError(
            "Settings file is not valid JSON",
            kind="invalid_json",
            line=exc.lineno,
            column=exc.colno,
        ) from exc


def _require_schema_version(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise SettingsStoreError(
            "Settings JSON root must be an object",
            kind="invalid_root_type",
        )

    if "schema_version" not in payload:
        raise SettingsStoreError(
            "Settings file must include schema_version",
            kind="schema_version_missing",
            path=("schema_version",),
        )


def _build_validation_error(exc: ValidationError) -> SettingsStoreError:
    pydantic_errors = _normalize_pydantic_errors(exc)
    first_error = pydantic_errors[0] if pydantic_errors else None
    first_path: ErrorPath | None = None
    first_kind = "validation_error"
    message = "Settings file contains invalid values"

    if first_error is not None:
        first_loc = first_error.get("loc", ())
        if isinstance(first_loc, tuple) and first_loc:
            first_path = first_loc
        first_type = first_error.get("type")
        if isinstance(first_type, str) and first_type:
            first_kind = first_type
        first_msg = first_error.get("msg")
        if isinstance(first_msg, str) and first_msg.strip():
            message = f"{message}: {first_msg.strip()}"

    return SettingsStoreError(
        message,
        kind=first_kind,
        path=first_path,
        pydantic_errors=pydantic_errors,
    )


def _normalize_pydantic_errors(exc: ValidationError) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for error in exc.errors(include_url=False):
        entry: dict[str, Any] = {
            "type": str(error.get("type", "validation_error")),
            "loc": tuple(error.get("loc", ())),
            "msg": str(error.get("msg", "")),
        }
        if "ctx" in error:
            entry["ctx"] = error["ctx"]
        normalized.append(entry)
    return normalized


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "SettingsStoreError",
    "load_settings",
    "save_settings",
]
