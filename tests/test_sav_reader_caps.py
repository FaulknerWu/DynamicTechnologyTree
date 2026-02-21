# pyright: reportMissingImports=false

from __future__ import annotations

import pytest
from pydantic import ValidationError

import dtt_core.sav_reader as sav_reader
from dtt_core.clausewitz_parser import Diagnostic
from settings import Settings


def test_sav_reader_caps_defaults_match_settings_defaults() -> None:
    settings = Settings()
    limits = sav_reader.SaveReaderLimits()

    assert settings.save_reader.max_member_uncompressed_size_bytes == 256 * 1024 * 1024
    assert settings.save_reader.max_total_uncompressed_size_bytes == 512 * 1024 * 1024
    assert settings.save_reader.max_parse_diagnostics_per_member == 20

    assert (
        limits.max_member_uncompressed_size_bytes
        == settings.save_reader.max_member_uncompressed_size_bytes
    )
    assert (
        limits.max_total_uncompressed_size_bytes
        == settings.save_reader.max_total_uncompressed_size_bytes
    )
    assert (
        limits.max_parse_diagnostics_per_member
        == settings.save_reader.max_parse_diagnostics_per_member
    )


def test_sav_reader_caps_settings_validation_rejects_total_smaller_than_member() -> (
    None
):
    with pytest.raises(ValidationError) as exc_info:
        Settings.model_validate(
            {
                "schema_version": 1,
                "paths": {},
                "localization": {},
                "display": {},
                "save_reader": {
                    "max_member_uncompressed_size_bytes": 100,
                    "max_total_uncompressed_size_bytes": 99,
                },
            },
            strict=True,
        )

    locations = {tuple(error.get("loc", ())) for error in exc_info.value.errors()}
    assert ("save_reader", "max_total_uncompressed_size_bytes") in locations


def test_sav_reader_caps_format_parse_warnings_respects_limit() -> None:
    diagnostics = [
        Diagnostic(message=f"diag {i}", line=1, col=i + 1, path="test")
        for i in range(30)
    ]

    warnings = sav_reader._format_parse_warnings(
        "meta",
        diagnostics,
        max_diagnostics=20,
    )
    assert len(warnings) == 21
    assert "diag 0" in warnings[0]
    assert "diag 19" in warnings[19]
    assert "and 10 more" in warnings[-1]

    warnings_custom = sav_reader._format_parse_warnings(
        "meta",
        diagnostics,
        max_diagnostics=5,
    )
    assert len(warnings_custom) == 6
    assert "diag 4" in warnings_custom[4]
    assert "and 25 more" in warnings_custom[-1]
