# pyright: reportMissingImports=false

from __future__ import annotations

import importlib
from pathlib import Path

_MODULE = importlib.import_module("dtt_core.localisation_parser")

merge_localisation_file_stream = _MODULE.merge_localisation_file_stream
parse_localisation_file = _MODULE.parse_localisation_file


def _write_yml(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_parse_file_with_utf8_bom_reads_header_and_single_key(tmp_path: Path) -> None:
    yml = _write_yml(
        tmp_path / "localisation" / "base_l_english.yml",
        b'\xef\xbb\xbfl_english:\ntech_one_desc:0 "Hello"\n',
    )

    parsed = parse_localisation_file(yml, expected_language="english")

    assert parsed.language == "l_english"
    assert parsed.entries == {"tech_one_desc": "Hello"}
    assert parsed.diagnostics == ()


def test_merge_duplicate_keys_is_last_wins_per_stream_order(tmp_path: Path) -> None:
    first = _write_yml(
        tmp_path / "localisation" / "00_base_l_english.yml",
        (
            b"l_english:\n"
            b'tech_a_desc:0 "from first"\n'
            b'tech_path_desc:0 "A \\"quoted\\" path \\\\mods\\\\x"\n'
        ),
    )
    second = _write_yml(
        tmp_path / "localisation" / "01_patch_l_english.yml",
        b'l_english:\ntech_a_desc:0 "from second"\n',
    )

    merged = merge_localisation_file_stream(
        [first, second], expected_language="english"
    )

    assert merged.entries["tech_a_desc"] == "from second"
    assert merged.entries["tech_path_desc"] == 'A "quoted" path \\mods\\x'
    assert merged.diagnostics == ()


def test_merge_enforces_replace_late_phase_even_if_stream_order_is_wrong(
    tmp_path: Path,
) -> None:
    replace_file = _write_yml(
        tmp_path / "localisation" / "replace" / "99_replace_l_english.yml",
        b'l_english:\ntech_a_desc:0 "replace value"\n',
    )
    base_file = _write_yml(
        tmp_path / "localisation" / "base_l_english.yml",
        b'l_english:\ntech_a_desc:0 "base value"\n',
    )

    merged = merge_localisation_file_stream(
        [replace_file, base_file],
        expected_language="english",
    )

    assert merged.entries["tech_a_desc"] == "replace value"
    assert merged.ordered_files == (base_file, replace_file)


def test_invalid_bytes_and_bad_lines_are_tolerated_with_diagnostics(
    tmp_path: Path,
) -> None:
    yml = _write_yml(
        tmp_path / "localisation" / "broken_l_english.yml",
        (
            b"l_english:\n"
            b'tech_ok_desc:0 "prefix \x80suffix"\n'
            b'bad_desc:0 "unterminated\n'
            b'tech_after_desc:0 "after"\n'
        ),
    )

    parsed = parse_localisation_file(yml, expected_language="english")

    assert parsed.entries["tech_ok_desc"] == "prefix \u20acsuffix"
    assert parsed.entries["tech_after_desc"] == "after"
    assert "bad_desc" not in parsed.entries
    messages = [diag.message for diag in parsed.diagnostics]
    assert any("fallback encoding cp1252" in message for message in messages)
    assert any("unterminated quoted value" in message for message in messages)
