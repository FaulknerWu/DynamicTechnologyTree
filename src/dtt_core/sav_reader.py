from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import zipfile

from dtt_core.clausewitz_parser import (
    Assignment,
    Atom,
    Block,
    ClausewitzNode,
    Diagnostic,
    parse,
)
from dtt_core.file_decode import (
    DEFAULT_FALLBACK_ENCODINGS,
    PREFERRED_ENCODINGS,
    DecodeDiagnostics,
    format_decode_warning,
)
from dtt_core.save_context import SaveContext, SaveEmpireFacts, SaveParseReport

REQUIRED_SAVE_MEMBERS: tuple[str, str] = ("meta", "gamestate")

# Guardrails against decompression bombs. A Stellaris save should be two text
# members, so a quarter/half-gig cap is generous while still blocking abuse.
MAX_MEMBER_UNCOMPRESSED_SIZE = 256 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_SIZE = 512 * 1024 * 1024

_TRUTHY_LITERALS = frozenset({"yes", "true", "1", "on"})
_FALSY_LITERALS = frozenset({"no", "false", "0", "off"})
_BOOLEAN_LITERALS = _TRUTHY_LITERALS | _FALSY_LITERALS
_DLC_KEY_NAMES = frozenset({"dlc", "dlcs"})


class SaveReaderError(ValueError):
    pass


@dataclass(frozen=True)
class _DecodedMember:
    text: str
    diagnostics: DecodeDiagnostics


def load_save_context(save_path: Path | str) -> SaveContext:
    archive_path = Path(save_path)
    raw_members, member_sizes, compressed_sizes = _read_archive_members(archive_path)

    decoded_members: dict[str, _DecodedMember] = {}
    warnings: list[str] = []
    for member_name in REQUIRED_SAVE_MEMBERS:
        raw_bytes = raw_members[member_name]
        if _looks_like_binary_payload(raw_bytes):
            raise SaveReaderError(
                "Binary or ironman saves are not supported. "
                "Please use a non-ironman text save."
            )

        decoded = _decode_member_bytes(
            raw_bytes,
            archive_path=archive_path,
            member_name=member_name,
        )
        decoded_members[member_name] = decoded
        if decoded.diagnostics.has_warning:
            warnings.append(
                f"{member_name}: {format_decode_warning(decoded.diagnostics)}"
            )

    meta_parse = parse(decoded_members["meta"].text, path=f"{archive_path}::meta")
    gamestate_parse = parse(
        decoded_members["gamestate"].text,
        path=f"{archive_path}::gamestate",
    )

    warnings.extend(_format_parse_warnings("meta", meta_parse.diagnostics))
    warnings.extend(_format_parse_warnings("gamestate", gamestate_parse.diagnostics))

    player_country_candidates = _extract_player_country_candidates(gamestate_parse.root)
    player_country_id = (
        player_country_candidates[0] if player_country_candidates else None
    )
    if len(player_country_candidates) > 1:
        warnings.append(
            "Multiple player country candidates found; using the smallest "
            f"country_id ({player_country_id})."
        )

    dlc_tokens = _extract_dlc_tokens(meta_parse.root, gamestate_parse.root)
    empires_by_country_id = _extract_empires_by_country(
        gamestate_parse.root,
        dlc_tokens=dlc_tokens,
    )
    save_name = _extract_save_name(meta_parse.root)

    report = SaveParseReport(
        member_uncompressed_sizes=member_sizes,
        member_compressed_sizes=compressed_sizes,
        member_encodings={
            member_name: decoded_members[member_name].diagnostics.encoding_used
            for member_name in REQUIRED_SAVE_MEMBERS
        },
        warnings=tuple(warnings),
    )

    return SaveContext(
        save_path=str(archive_path),
        empires_by_country_id=empires_by_country_id,
        player_country_id=player_country_id,
        player_country_candidates=player_country_candidates,
        save_name=save_name,
        dlcs=frozenset(dlc_tokens),
        report=report,
    )


def _read_archive_members(
    archive_path: Path,
) -> tuple[dict[str, bytes], dict[str, int], dict[str, int]]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            member_sizes, compressed_sizes = _validate_zip_safety(archive, archive_path)
            raw_members = _read_required_members(archive, archive_path)
            return raw_members, member_sizes, compressed_sizes
    except zipfile.BadZipFile as exc:
        raise SaveReaderError(
            f"Invalid save archive '{archive_path}': file is not a valid ZIP archive."
        ) from exc


def _validate_zip_safety(
    archive: zipfile.ZipFile,
    archive_path: Path,
) -> tuple[dict[str, int], dict[str, int]]:
    member_sizes: dict[str, int] = {}
    compressed_sizes: dict[str, int] = {}
    total_uncompressed = 0

    infos = sorted(archive.infolist(), key=lambda info: info.filename.casefold())
    for info in infos:
        member_sizes[info.filename] = info.file_size
        compressed_sizes[info.filename] = info.compress_size

        if info.file_size > MAX_MEMBER_UNCOMPRESSED_SIZE:
            raise SaveReaderError(
                "Refusing to open untrusted save archive: member "
                f"'{info.filename}' uncompressed size ({info.file_size} bytes) "
                "exceeds safe per-member limit "
                f"({MAX_MEMBER_UNCOMPRESSED_SIZE} bytes)."
            )

        total_uncompressed += info.file_size
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_SIZE:
            raise SaveReaderError(
                "Refusing to open untrusted save archive: total uncompressed size "
                f"({total_uncompressed} bytes) exceeds safe total limit "
                f"({MAX_TOTAL_UNCOMPRESSED_SIZE} bytes)."
            )

    return member_sizes, compressed_sizes


def _read_required_members(
    archive: zipfile.ZipFile,
    archive_path: Path,
) -> dict[str, bytes]:
    raw_members: dict[str, bytes] = {}
    available_members = {info.filename for info in archive.infolist()}

    for member_name in REQUIRED_SAVE_MEMBERS:
        if member_name not in available_members:
            raise SaveReaderError(
                f"Save archive '{archive_path}' is missing required member "
                f"'{member_name}'. Expected both 'meta' and 'gamestate'."
            )
        raw_members[member_name] = archive.read(member_name)

    return raw_members


def _decode_member_bytes(
    raw_bytes: bytes,
    *,
    archive_path: Path,
    member_name: str,
    replacement_encoding: str = "utf-8",
) -> _DecodedMember:
    ordered_encodings = _ordered_unique_encodings(
        (*PREFERRED_ENCODINGS, *DEFAULT_FALLBACK_ENCODINGS)
    )
    failed_attempts: list[str] = []
    diagnostics_path = Path(f"{archive_path}::{member_name}")

    for encoding in ordered_encodings:
        try:
            text = raw_bytes.decode(encoding)
            diagnostics = DecodeDiagnostics(
                path=diagnostics_path,
                encoding_used=encoding,
                attempted_encodings=ordered_encodings,
                failed_attempts=tuple(failed_attempts),
                used_fallback_encoding=encoding not in PREFERRED_ENCODINGS,
                used_replacement=False,
            )
            return _DecodedMember(text=text, diagnostics=diagnostics)
        except UnicodeDecodeError as exc:
            failed_attempts.append(f"{encoding}: {exc.reason} at byte {exc.start}")
        except LookupError as exc:
            failed_attempts.append(f"{encoding}: unknown encoding ({exc})")

    text = raw_bytes.decode(replacement_encoding, errors="replace")
    failed_attempts.append(f"{replacement_encoding}: replacement characters inserted")
    diagnostics = DecodeDiagnostics(
        path=diagnostics_path,
        encoding_used=replacement_encoding,
        attempted_encodings=ordered_encodings,
        failed_attempts=tuple(failed_attempts),
        used_fallback_encoding=False,
        used_replacement=True,
    )
    return _DecodedMember(text=text, diagnostics=diagnostics)


def _looks_like_binary_payload(raw_bytes: bytes) -> bool:
    if not raw_bytes:
        return False

    prefix = raw_bytes[:128]
    if b"\x00" in prefix:
        return True

    trimmed = prefix.lstrip().lower()
    if trimmed.startswith(b"bin"):
        return True

    if len(trimmed) >= 7 and trimmed[:4].startswith(b"sav") and trimmed[4:7] == b"bin":
        return True

    return False


def _format_parse_warnings(
    member_name: str, diagnostics: list[Diagnostic]
) -> list[str]:
    warnings: list[str] = []
    for diagnostic in diagnostics[:20]:
        warnings.append(f"{member_name}: parse diagnostic: {diagnostic.format()}")
    if len(diagnostics) > 20:
        warnings.append(
            f"{member_name}: parse diagnostic: and {len(diagnostics) - 20} more"
        )
    return warnings


def _extract_player_country_candidates(root: Block) -> tuple[int, ...]:
    candidates: set[int] = set()

    for assignment in _iter_assignments(root, "player"):
        candidates.update(_collect_country_ids_from_player_node(assignment.value))

    return tuple(sorted(candidates))


def _collect_country_ids_from_player_node(node: ClausewitzNode) -> set[int]:
    country_ids: set[int] = set()
    stack: list[ClausewitzNode] = [node]

    while stack:
        current = stack.pop()
        if isinstance(current, Block):
            stack.extend(current.items)
            continue

        if not isinstance(current, Assignment):
            continue

        if current.key.value.strip().casefold() == "country":
            country_id = _atom_int(current.value)
            if country_id is not None:
                country_ids.add(country_id)

        if isinstance(current.value, Block):
            stack.append(current.value)

    return country_ids


def _extract_empires_by_country(
    root: Block,
    *,
    dlc_tokens: tuple[str, ...],
) -> dict[int, SaveEmpireFacts]:
    empires: dict[int, SaveEmpireFacts] = {}

    for assignment in _iter_assignments(root, "country"):
        if not isinstance(assignment.value, Block):
            continue

        for country_entry in assignment.value.items:
            if not isinstance(country_entry, Assignment):
                continue
            if not isinstance(country_entry.value, Block):
                continue

            country_id = _parse_country_id(country_entry.key.value)
            if country_id is None:
                continue

            empires[country_id] = _extract_empire_facts(
                country_id,
                country_entry.value,
                dlc_tokens=dlc_tokens,
            )

    return {country_id: empires[country_id] for country_id in sorted(empires)}


def _extract_empire_facts(
    country_id: int,
    country_block: Block,
    *,
    dlc_tokens: tuple[str, ...],
) -> SaveEmpireFacts:
    country_name = (
        _extract_first_atom_value(country_block, ("name", "country_name")) or ""
    )
    authority = _extract_first_atom_value(country_block, ("authority",))
    ethics = _extract_membership_values(country_block, ("ethics", "ethic"))
    civics = _extract_membership_values(country_block, ("civics", "civic"))
    origin = _extract_first_atom_value(country_block, ("origin",))
    ascension_perks = _extract_membership_values(
        country_block,
        ("ascension_perks", "ascension_perk", "ap_ascension_perks"),
    )
    country_flags = _extract_flag_values(country_block, ("country_flags", "flags"))

    (
        is_gestalt,
        is_machine_empire,
        is_hive_empire,
        is_regular_empire,
        is_individual_machine,
    ) = _infer_polity_flags(authority)

    return SaveEmpireFacts(
        country_id=country_id,
        country_name=country_name,
        is_gestalt=is_gestalt,
        is_machine_empire=is_machine_empire,
        is_hive_empire=is_hive_empire,
        is_regular_empire=is_regular_empire,
        is_individual_machine=is_individual_machine,
        authority=authority,
        ethics=ethics,
        civics=civics,
        origin=origin,
        ascension_perks=ascension_perks,
        country_flags=country_flags,
        dlcs=dlc_tokens,
    )


def _extract_save_name(meta_root: Block) -> str | None:
    return _extract_first_atom_value(meta_root, ("name", "save_name"))


def _extract_dlc_tokens(meta_root: Block, gamestate_root: Block) -> tuple[str, ...]:
    tokens: list[str] = []
    tokens.extend(_scan_dlc_tokens(meta_root))
    tokens.extend(_scan_dlc_tokens(gamestate_root))
    return _sorted_unique_tokens(tokens)


def _scan_dlc_tokens(root: Block) -> list[str]:
    tokens: list[str] = []
    stack: list[ClausewitzNode] = [root]

    while stack:
        current = stack.pop()
        if isinstance(current, Block):
            stack.extend(current.items)
            continue

        if not isinstance(current, Assignment):
            continue

        key = current.key.value.strip()
        normalized_key = key.casefold()
        if normalized_key.startswith("dlc"):
            key_token = _token_from_dlc_key(key)
            if key_token is not None:
                tokens.append(key_token)
            tokens.extend(_collect_dlc_values(current.value))

        if isinstance(current.value, Block):
            stack.append(current.value)

    return tokens


def _collect_dlc_values(node: ClausewitzNode) -> list[str]:
    tokens: list[str] = []
    stack: list[ClausewitzNode] = [node]

    while stack:
        current = stack.pop()
        if isinstance(current, Atom):
            token = _sanitize_dlc_token(current.token.value)
            if token is not None:
                tokens.append(token)
            continue

        if isinstance(current, Block):
            stack.extend(current.items)
            continue

        if not isinstance(current, Assignment):
            continue

        atom_value = _atom_text(current.value)
        if atom_value is not None:
            normalized_value = atom_value.strip().casefold()
            if normalized_value in _TRUTHY_LITERALS:
                key_token = _sanitize_dlc_token(current.key.value)
                if key_token is not None:
                    tokens.append(key_token)
            else:
                value_token = _sanitize_dlc_token(atom_value)
                if value_token is not None:
                    tokens.append(value_token)

        if isinstance(current.value, Block):
            stack.append(current.value)

    return tokens


def _extract_membership_values(
    country_block: Block, keys: tuple[str, ...]
) -> tuple[str, ...]:
    tokens: list[str] = []
    for key in keys:
        for assignment in _iter_assignments(country_block, key):
            tokens.extend(_collect_membership_tokens(assignment.value))
    return _sorted_unique_tokens(tokens)


def _extract_flag_values(
    country_block: Block, keys: tuple[str, ...]
) -> tuple[str, ...]:
    tokens: list[str] = []
    for key in keys:
        for assignment in _iter_assignments(country_block, key):
            tokens.extend(_collect_flag_tokens(assignment.value))
    return _sorted_unique_tokens(tokens)


def _collect_membership_tokens(node: ClausewitzNode) -> list[str]:
    if isinstance(node, Atom):
        token = node.token.value.strip()
        return [token] if token else []

    if not isinstance(node, Block):
        return []

    out: list[str] = []
    for item in node.items:
        if isinstance(item, Atom):
            token = item.token.value.strip()
            if token:
                out.append(token)
            continue

        if not isinstance(item, Assignment):
            continue

        atom_value = _atom_text(item.value)
        if atom_value is not None:
            normalized = atom_value.strip().casefold()
            if normalized in _TRUTHY_LITERALS:
                token = item.key.value.strip()
                if token:
                    out.append(token)
            elif normalized not in _BOOLEAN_LITERALS:
                token = atom_value.strip()
                if token:
                    out.append(token)
            continue

        if isinstance(item.value, Block):
            out.extend(_collect_membership_tokens(item.value))

    return out


def _collect_flag_tokens(node: ClausewitzNode) -> list[str]:
    if isinstance(node, Atom):
        token = node.token.value.strip()
        return [token] if token else []

    if not isinstance(node, Block):
        return []

    out: list[str] = []
    for item in node.items:
        if isinstance(item, Atom):
            token = item.token.value.strip()
            if token:
                out.append(token)
            continue

        if isinstance(item, Assignment):
            token = item.key.value.strip()
            if token:
                out.append(token)

    return out


def _extract_first_atom_value(block: Block, keys: tuple[str, ...]) -> str | None:
    keyset = {key.casefold() for key in keys}
    for item in block.items:
        if not isinstance(item, Assignment):
            continue
        if item.key.value.strip().casefold() not in keyset:
            continue
        value = _atom_text(item.value)
        if value is None:
            continue
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


def _infer_polity_flags(
    authority: str | None,
) -> tuple[bool | None, bool | None, bool | None, bool | None, bool | None]:
    if not authority:
        return None, None, None, None, None

    normalized = authority.strip().casefold()

    if "machine_intelligence" in normalized:
        return True, True, False, False, True

    if "hive_mind" in normalized:
        return True, False, True, False, False

    return False, False, False, True, False


def _iter_assignments(block: Block, key: str):
    target = key.casefold()
    for item in block.items:
        if not isinstance(item, Assignment):
            continue
        if item.key.value.strip().casefold() == target:
            yield item


def _parse_country_id(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _atom_text(node: ClausewitzNode) -> str | None:
    if isinstance(node, Atom):
        return node.token.value
    return None


def _atom_int(node: ClausewitzNode) -> int | None:
    text = _atom_text(node)
    if text is None:
        return None
    try:
        return int(text.strip())
    except ValueError:
        return None


def _token_from_dlc_key(key: str) -> str | None:
    normalized = key.strip().casefold()
    if normalized in _DLC_KEY_NAMES:
        return None
    if not normalized.startswith("dlc"):
        return None

    suffix = key.strip()[3:].strip("_-")
    if not suffix or suffix.isdigit():
        return None
    return _sanitize_dlc_token(suffix)


def _sanitize_dlc_token(value: str) -> str | None:
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return None

    normalized = cleaned.casefold()
    if normalized in _BOOLEAN_LITERALS:
        return None
    if normalized in _DLC_KEY_NAMES:
        return None
    return cleaned


def _sorted_unique_tokens(values: list[str]) -> tuple[str, ...]:
    unique_by_folded: dict[str, str] = {}
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        folded = cleaned.casefold()
        if folded not in unique_by_folded:
            unique_by_folded[folded] = cleaned
    return tuple(sorted(unique_by_folded.values(), key=str.casefold))


def _ordered_unique_encodings(encodings: tuple[str, ...]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for encoding in encodings:
        normalized = encoding.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)
