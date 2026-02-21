from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_MODULE_NAME = ".".join(("dtt_core", "file_decode"))
_decode_module = importlib.import_module(_MODULE_NAME)
format_decode_warning = _decode_module.format_decode_warning
read_text_with_diagnostics = _decode_module.read_text_with_diagnostics


def test_file_decode_utf8_sig_strips_bom(tmp_path: Path) -> None:
    target = tmp_path / "with_bom.txt"
    target.write_bytes(b"\xef\xbb\xbftechnology")

    decoded = read_text_with_diagnostics(target)

    assert decoded.text == "technology"
    assert decoded.diagnostics.encoding_used == "utf-8-sig"
    assert decoded.diagnostics.has_warning is False


def test_file_decode_invalid_utf8_uses_fallback_and_records_diagnostics(
    tmp_path: Path,
) -> None:
    target = tmp_path / "invalid_utf8.txt"
    payload = b"prefix\x80suffix"
    target.write_bytes(payload)

    decoded = read_text_with_diagnostics(target)

    assert decoded.text == "prefix\u20acsuffix"
    assert decoded.text != "prefixsuffix"
    assert decoded.diagnostics.encoding_used == "cp1252"
    assert decoded.diagnostics.used_fallback_encoding is True
    assert decoded.diagnostics.used_replacement is False
    assert decoded.diagnostics.has_warning is True
    assert len(decoded.diagnostics.failed_attempts) == 2
    assert "utf-8-sig:" in decoded.diagnostics.failed_attempts[0]
    assert "utf-8:" in decoded.diagnostics.failed_attempts[1]
    assert "fallback encoding cp1252" in format_decode_warning(decoded.diagnostics)


def test_file_decode_invalid_utf8_can_replace_when_fallbacks_disabled(
    tmp_path: Path,
) -> None:
    target = tmp_path / "replace_utf8.txt"
    target.write_bytes(b"alpha\xffbeta")

    decoded = read_text_with_diagnostics(target, fallback_encodings=())

    assert decoded.text == "alpha\ufffdbeta"
    assert decoded.diagnostics.used_fallback_encoding is False
    assert decoded.diagnostics.used_replacement is True
    assert decoded.diagnostics.has_warning is True


def test_file_decode_custom_order_prefers_first_successful_fallback(
    tmp_path: Path,
) -> None:
    target = tmp_path / "custom_order.txt"
    target.write_bytes(b"prefix\x80suffix")

    decoded = read_text_with_diagnostics(
        target,
        fallback_encodings=("latin-1", "cp1252"),
    )

    assert decoded.text == "prefix\u0080suffix"
    assert decoded.diagnostics.encoding_used == "latin-1"
    assert decoded.diagnostics.used_fallback_encoding is True
    assert decoded.diagnostics.failed_attempts[0].startswith("utf-8-sig:")
    assert decoded.diagnostics.failed_attempts[1].startswith("utf-8:")


def test_file_decode_strict_mode_raises_when_all_attempts_fail(tmp_path: Path) -> None:
    target = tmp_path / "strict_failure.txt"
    target.write_bytes(b"alpha\xffbeta")

    with pytest.raises(UnicodeDecodeError):
        read_text_with_diagnostics(
            target,
            fallback_encodings=(),
            on_failure="strict",
        )
