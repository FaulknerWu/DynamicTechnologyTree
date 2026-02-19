# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

import dtt_core.sav_reader as sav_reader
from dtt_core.save_context import SaveParseReport


def _payload_bytes(payload: str | bytes) -> bytes:
    if isinstance(payload, bytes):
        return payload
    return payload.encode("utf-8")


def _write_sav(
    path: Path,
    *,
    meta: str | bytes | None,
    gamestate: str | bytes | None,
    extras: dict[str, str | bytes] | None = None,
) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if meta is not None:
            archive.writestr("meta", _payload_bytes(meta))
        if gamestate is not None:
            archive.writestr("gamestate", _payload_bytes(gamestate))
        for name, payload in (extras or {}).items():
            archive.writestr(name, _payload_bytes(payload))
    return path


def test_load_save_context_valid_zip_extracts_deterministic_context(
    tmp_path: Path,
) -> None:
    meta = 'name = "Campaign 01"\ndlcs = { "Utopia" "Leviathans" }\n'
    gamestate = "\n".join(
        [
            "player = {",
            "  1 = { country = 42 }",
            "  0 = { country = 7 }",
            "}",
            "country = {",
            "  42 = {",
            '    name = "Beta Directorate"',
            "    authority = auth_machine_intelligence",
            "    ethics = { ethic_gestalt_consciousness }",
            "    civics = { civic_machine_terminator civic_machine_servitor }",
            "    origin = origin_resource_consolidation",
            "    ascension_perks = { ap_synthetic_age ap_machine_worlds }",
            "    country_flags = { relic_hunter=yes machine_flag=yes }",
            "  }",
            "  7 = {",
            '    name = "Alpha Union"',
            "    authority = auth_democratic",
            "    ethics = { ethic_fanatic_materialist ethic_xenophile }",
            "    civics = { civic_meritocracy civic_technocracy }",
            "    origin = origin_prosperous_unification",
            "    ascension_perks = { ap_interstellar_dominion }",
            "    flags = { precursor_chain=yes }",
            "  }",
            "}",
            'dlc004 = "Galactic Paragons"',
        ]
    )

    save_path = _write_sav(
        tmp_path / "valid.sav",
        meta=meta,
        gamestate=gamestate,
    )
    context = sav_reader.load_save_context(save_path)

    assert context.save_name == "Campaign 01"
    assert context.player_country_candidates == (7, 42)
    assert context.player_country_id == 7
    assert context.sorted_country_ids() == (7, 42)
    assert tuple(context.empires_by_country_id) == (7, 42)
    assert context.dlcs == frozenset({"Utopia", "Leviathans", "Galactic Paragons"})

    alpha = context.empires_by_country_id[7]
    assert alpha.country_name == "Alpha Union"
    assert alpha.authority == "auth_democratic"
    assert tuple(alpha.ethics or ()) == (
        "ethic_fanatic_materialist",
        "ethic_xenophile",
    )
    assert alpha.is_regular_empire is True

    beta = context.empires_by_country_id[42]
    assert beta.authority == "auth_machine_intelligence"
    assert beta.is_machine_empire is True
    assert beta.is_gestalt is True

    assert isinstance(context.report, SaveParseReport)
    assert context.report is not None
    assert context.report.member_encodings["meta"] == "utf-8-sig"
    assert context.report.member_encodings["gamestate"] == "utf-8-sig"
    assert context.report.member_uncompressed_sizes["meta"] > 0
    assert context.report.member_uncompressed_sizes["gamestate"] > 0
    assert context.report.member_compressed_sizes["meta"] >= 0
    assert context.report.member_compressed_sizes["gamestate"] >= 0
    assert any(
        "Multiple player country candidates found" in warning
        for warning in context.report.warnings
    )


@pytest.mark.parametrize(
    "missing_member, meta_payload, gamestate_payload",
    [
        ("meta", None, "player = { 0 = { country = 1 } }\ncountry = { 1 = { } }\n"),
        ("gamestate", 'name = "Only Meta"\n', None),
    ],
)
def test_load_save_context_missing_required_members_raises_clear_error(
    tmp_path: Path,
    missing_member: str,
    meta_payload: str | None,
    gamestate_payload: str | None,
) -> None:
    save_path = _write_sav(
        tmp_path / f"missing_{missing_member}.sav",
        meta=meta_payload,
        gamestate=gamestate_payload,
    )

    with pytest.raises(sav_reader.SaveReaderError) as exc:
        sav_reader.load_save_context(save_path)

    message = str(exc.value)
    assert "missing required member" in message
    assert missing_member in message


def test_load_save_context_invalid_zip_raises_clear_error(tmp_path: Path) -> None:
    save_path = tmp_path / "invalid.sav"
    save_path.write_bytes(b"not a zip")

    with pytest.raises(sav_reader.SaveReaderError) as exc:
        sav_reader.load_save_context(save_path)

    assert "valid ZIP archive" in str(exc.value)


def test_load_save_context_rejects_binary_or_ironman_payload(tmp_path: Path) -> None:
    save_path = _write_sav(
        tmp_path / "binary.sav",
        meta='name = "Binary"\n',
        gamestate=b"SAV2bin\x00\x01\x02",
    )

    with pytest.raises(sav_reader.SaveReaderError) as exc:
        sav_reader.load_save_context(save_path)

    assert "Binary or ironman saves are not supported" in str(exc.value)


def test_load_save_context_rejects_member_larger_than_safety_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sav_reader, "MAX_MEMBER_UNCOMPRESSED_SIZE", 48)
    monkeypatch.setattr(sav_reader, "MAX_TOTAL_UNCOMPRESSED_SIZE", 2048)

    oversized_meta = 'name = "x"\npadding = "' + ("a" * 128) + '"\n'
    save_path = _write_sav(
        tmp_path / "oversized-member.sav",
        meta=oversized_meta,
        gamestate="player = { 0 = { country = 1 } }\ncountry = { 1 = { } }\n",
    )

    with pytest.raises(sav_reader.SaveReaderError) as exc:
        sav_reader.load_save_context(save_path)

    assert "safe per-member limit" in str(exc.value)


def test_load_save_context_rejects_total_uncompressed_size_larger_than_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sav_reader, "MAX_MEMBER_UNCOMPRESSED_SIZE", 4096)
    monkeypatch.setattr(sav_reader, "MAX_TOTAL_UNCOMPRESSED_SIZE", 96)

    meta = 'name = "Too Large"\npad = "' + ("b" * 80) + '"\n'
    gamestate = (
        "player = { 0 = { country = 1 } }\n"
        'country = { 1 = { name = "A" } }\n'
        'trail = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"\n'
    )
    save_path = _write_sav(
        tmp_path / "oversized-total.sav",
        meta=meta,
        gamestate=gamestate,
    )

    with pytest.raises(sav_reader.SaveReaderError) as exc:
        sav_reader.load_save_context(save_path)

    assert "safe total limit" in str(exc.value)


def test_load_save_context_report_records_fallback_encoding_and_warning(
    tmp_path: Path,
) -> None:
    meta = b'name = "Euro Save \x80"\ndlcs = { "Utopia" }\n'
    gamestate = b"\n".join(
        [
            b"player = { 0 = { country = 1 } }",
            b"country = {",
            b"  1 = {",
            b'    name = "Empire \x80"',
            b"    authority = auth_democratic",
            b"  }",
            b"}",
        ]
    )

    save_path = _write_sav(
        tmp_path / "fallback-encoding.sav",
        meta=meta,
        gamestate=gamestate,
    )
    context = sav_reader.load_save_context(save_path)

    assert context.report is not None
    assert context.report.member_encodings["meta"] == "cp1252"
    assert context.report.member_encodings["gamestate"] == "cp1252"
    assert any(
        "fallback encoding cp1252" in warning for warning in context.report.warnings
    )
