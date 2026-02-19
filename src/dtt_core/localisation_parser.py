from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dtt_core.file_decode import format_decode_warning, read_text_with_diagnostics
from dtt_core.source_manifest import normalize_manifest_path

_HEADER_PREFIX = "l_"
_REPLACE_PATH_PREFIX = "localisation/replace"


@dataclass(frozen=True)
class LocalisationDiagnostic:
    path: Path
    line: int
    message: str

    def format(self) -> str:
        if self.line <= 0:
            return f"{self.path}: {self.message}"
        return f"{self.path}:{self.line}: {self.message}"


@dataclass(frozen=True)
class ParsedLocalisationFile:
    path: Path
    language: str | None
    entries: dict[str, str]
    diagnostics: tuple[LocalisationDiagnostic, ...]


@dataclass(frozen=True)
class LocalisationMergeResult:
    entries: dict[str, str]
    diagnostics: tuple[LocalisationDiagnostic, ...]
    ordered_files: tuple[Path, ...]


@dataclass(frozen=True)
class _OrderedFile:
    path: Path
    relative_path: str
    phase: int
    order: int


def parse_localisation_file(
    path: Path,
    *,
    expected_language: str | None = None,
) -> ParsedLocalisationFile:
    file_path = Path(path)
    decoded = read_text_with_diagnostics(file_path)
    parsed = parse_localisation_text(
        decoded.text,
        path=file_path,
        expected_language=expected_language,
    )

    diagnostics = list(parsed.diagnostics)
    if decoded.diagnostics.has_warning:
        diagnostics.insert(
            0,
            LocalisationDiagnostic(
                path=file_path,
                line=0,
                message=format_decode_warning(decoded.diagnostics),
            ),
        )

    return ParsedLocalisationFile(
        path=file_path,
        language=parsed.language,
        entries=parsed.entries,
        diagnostics=tuple(diagnostics),
    )


def parse_localisation_text(
    text: str,
    *,
    path: Path | str = "<memory>",
    expected_language: str | None = None,
) -> ParsedLocalisationFile:
    file_path = Path(path)
    diagnostics: list[LocalisationDiagnostic] = []
    entries: dict[str, str] = {}
    header_language: str | None = None

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line
        if line_no == 1:
            line = line.lstrip("\ufeff")

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if header_language is None:
            parsed_header = _parse_header(stripped)
            if parsed_header is None:
                continue
            header_language = parsed_header
            if expected_language is not None:
                normalized_expected = _normalize_language(expected_language)
                if normalized_expected and normalized_expected != header_language:
                    diagnostics.append(
                        LocalisationDiagnostic(
                            path=file_path,
                            line=line_no,
                            message=(
                                "Header language does not match expected language "
                                f"({header_language} != {normalized_expected})"
                            ),
                        )
                    )
            continue

        parsed_entry = _parse_entry_line(
            line,
            path=file_path,
            line_no=line_no,
            diagnostics=diagnostics,
        )
        if parsed_entry is None:
            continue

        key, value = parsed_entry
        entries[key] = value

    if header_language is None:
        diagnostics.append(
            LocalisationDiagnostic(
                path=file_path,
                line=1,
                message="Missing localisation header (expected l_<language>:)",
            )
        )

    return ParsedLocalisationFile(
        path=file_path,
        language=header_language,
        entries=entries,
        diagnostics=tuple(diagnostics),
    )


def merge_localisation_file_stream(
    file_stream: Iterable[object],
    *,
    expected_language: str | None = None,
) -> LocalisationMergeResult:
    ordered_files = _order_file_stream(file_stream)
    merged_entries: dict[str, str] = {}
    diagnostics: list[LocalisationDiagnostic] = []
    merge_order: list[Path] = []

    for ordered_file in ordered_files:
        parsed = parse_localisation_file(
            ordered_file.path,
            expected_language=expected_language,
        )
        merge_order.append(ordered_file.path)
        diagnostics.extend(parsed.diagnostics)
        merged_entries.update(parsed.entries)

    return LocalisationMergeResult(
        entries=merged_entries,
        diagnostics=tuple(diagnostics),
        ordered_files=tuple(merge_order),
    )


def _parse_header(line: str) -> str | None:
    before_comment = line.split("#", 1)[0].strip()
    if not before_comment or not before_comment.endswith(":"):
        return None

    header = before_comment[:-1].strip().lower()
    if not header.startswith(_HEADER_PREFIX):
        return None

    suffix = header[len(_HEADER_PREFIX) :]
    if not suffix:
        return None

    if any(not (char.isalnum() or char == "_") for char in suffix):
        return None

    return header


def _parse_entry_line(
    line: str,
    *,
    path: Path,
    line_no: int,
    diagnostics: list[LocalisationDiagnostic],
) -> tuple[str, str] | None:
    index = 0
    length = len(line)

    while index < length and line[index].isspace():
        index += 1

    if index >= length or line[index] == "#":
        return None

    key_start = index
    while index < length and not line[index].isspace() and line[index] != ":":
        index += 1
    key = line[key_start:index]
    if not key:
        diagnostics.append(
            LocalisationDiagnostic(
                path=path,
                line=line_no,
                message="Invalid localisation entry: missing key",
            )
        )
        return None

    while index < length and line[index].isspace():
        index += 1

    if index >= length or line[index] != ":":
        diagnostics.append(
            LocalisationDiagnostic(
                path=path,
                line=line_no,
                message=f"Invalid localisation entry for key '{key}': missing ':'",
            )
        )
        return None
    index += 1

    while index < length and line[index].isspace():
        index += 1

    while index < length and line[index].isdigit():
        index += 1

    while index < length and line[index].isspace():
        index += 1

    if index >= length or line[index] != '"':
        diagnostics.append(
            LocalisationDiagnostic(
                path=path,
                line=line_no,
                message=(
                    f"Invalid localisation entry for key '{key}': missing opening quote"
                ),
            )
        )
        return None

    index += 1
    value_parts: list[str] = []
    closed_quote = False

    while index < length:
        char = line[index]
        if char == '"':
            closed_quote = True
            index += 1
            break

        if char == "\\":
            index += 1
            if index >= length:
                diagnostics.append(
                    LocalisationDiagnostic(
                        path=path,
                        line=line_no,
                        message=(
                            f"Invalid localisation entry for key '{key}': "
                            "unterminated escape sequence"
                        ),
                    )
                )
                return None

            escaped_char = line[index]
            if escaped_char in {'"', "\\"}:
                value_parts.append(escaped_char)
                index += 1
                continue

            if escaped_char == "n":
                value_parts.append("\n")
                index += 1
                continue

            if escaped_char == "r":
                value_parts.append("\r")
                index += 1
                continue

            if escaped_char == "t":
                value_parts.append("\t")
                index += 1
                continue

            if escaped_char == "b":
                value_parts.append("\b")
                index += 1
                continue

            if escaped_char == "f":
                value_parts.append("\f")
                index += 1
                continue

            if escaped_char == "0":
                value_parts.append("\0")
                index += 1
                continue

            if escaped_char == "u":
                maybe_hex = line[index + 1 : index + 5]
                if len(maybe_hex) == 4 and all(
                    _is_hex_digit(char) for char in maybe_hex
                ):
                    value_parts.append(chr(int(maybe_hex, 16)))
                    index += 5
                    continue

                diagnostics.append(
                    LocalisationDiagnostic(
                        path=path,
                        line=line_no,
                        message=(
                            f"Invalid localisation entry for key '{key}': "
                            "invalid unicode escape"
                        ),
                    )
                )
                value_parts.append("\\u")
                index += 1
                continue

            diagnostics.append(
                LocalisationDiagnostic(
                    path=path,
                    line=line_no,
                    message=(
                        f"Unknown escape sequence for key '{key}': \\{escaped_char}"
                    ),
                )
            )
            value_parts.append(f"\\{escaped_char}")
            index += 1
            continue

        value_parts.append(char)
        index += 1

    if not closed_quote:
        diagnostics.append(
            LocalisationDiagnostic(
                path=path,
                line=line_no,
                message=(
                    f"Invalid localisation entry for key '{key}': "
                    "unterminated quoted value"
                ),
            )
        )
        return None

    while index < length and line[index].isspace():
        index += 1

    if index < length and line[index] != "#":
        diagnostics.append(
            LocalisationDiagnostic(
                path=path,
                line=line_no,
                message=(
                    f"Invalid localisation entry for key '{key}': "
                    "unexpected trailing content"
                ),
            )
        )
        return None

    return key, "".join(value_parts)


def _order_file_stream(file_stream: Iterable[object]) -> tuple[_OrderedFile, ...]:
    indexed: list[_OrderedFile] = []
    for order, file_ref in enumerate(file_stream):
        path, relative_path, explicit_phase = _coerce_file_ref(file_ref)
        inferred_phase = 1 if _is_replace_localisation_path(relative_path) else 0
        indexed.append(
            _OrderedFile(
                path=path,
                relative_path=relative_path,
                phase=max(explicit_phase, inferred_phase),
                order=order,
            )
        )

    return tuple(sorted(indexed, key=lambda item: (item.phase, item.order)))


def _coerce_file_ref(file_ref: object) -> tuple[Path, str, int]:
    if isinstance(file_ref, Path):
        normalized = normalize_manifest_path(file_ref.as_posix())
        return file_ref, normalized, 0

    if isinstance(file_ref, str):
        path = Path(file_ref)
        normalized = normalize_manifest_path(file_ref)
        return path, normalized, 0

    absolute_path = getattr(file_ref, "absolute_path", None)
    if absolute_path is not None:
        path = Path(absolute_path)
        relative_path = str(getattr(file_ref, "relative_path", path.as_posix()))
        normalized = normalize_manifest_path(relative_path)

        phase = 0
        sort_key = getattr(file_ref, "sort_key", None)
        if isinstance(sort_key, tuple) and sort_key:
            first = sort_key[0]
            if isinstance(first, int):
                phase = first

        return path, normalized, phase

    raise TypeError(
        "Unsupported file stream entry; expected Path, str, or object with "
        "absolute_path/relative_path"
    )


def _is_replace_localisation_path(path_value: str) -> bool:
    normalized = normalize_manifest_path(path_value)
    if not normalized:
        return False

    if normalized == _REPLACE_PATH_PREFIX:
        return True
    if normalized.startswith(f"{_REPLACE_PATH_PREFIX}/"):
        return True

    parts = normalized.split("/")
    for index in range(len(parts) - 1):
        if parts[index] == "localisation" and parts[index + 1] == "replace":
            return True
    return False


def _normalize_language(language: str) -> str:
    normalized = language.strip().lower()
    if not normalized:
        return ""
    if normalized.startswith(_HEADER_PREFIX):
        return normalized
    return f"{_HEADER_PREFIX}{normalized}"


def _is_hex_digit(char: str) -> bool:
    return char.isdigit() or ("a" <= char.lower() <= "f")
