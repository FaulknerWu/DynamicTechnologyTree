from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

PREFERRED_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8")
DEFAULT_FALLBACK_ENCODINGS: tuple[str, ...] = ("cp1252", "latin-1")


@dataclass(frozen=True)
class DecodeDiagnostics:
    path: Path
    encoding_used: str
    attempted_encodings: tuple[str, ...]
    failed_attempts: tuple[str, ...]
    used_fallback_encoding: bool
    used_replacement: bool

    @property
    def has_warning(self) -> bool:
        return self.used_fallback_encoding or self.used_replacement


@dataclass(frozen=True)
class DecodedText:
    text: str
    diagnostics: DecodeDiagnostics


def read_text_with_diagnostics(
    path: Path,
    *,
    fallback_encodings: Sequence[str] = DEFAULT_FALLBACK_ENCODINGS,
    replacement_encoding: str = "utf-8",
) -> DecodedText:
    raw_bytes = path.read_bytes()
    ordered_encodings = _ordered_unique_encodings(
        (*PREFERRED_ENCODINGS, *fallback_encodings)
    )
    failed_attempts: list[str] = []

    for encoding in ordered_encodings:
        try:
            text = raw_bytes.decode(encoding)
            diagnostics = DecodeDiagnostics(
                path=path,
                encoding_used=encoding,
                attempted_encodings=ordered_encodings,
                failed_attempts=tuple(failed_attempts),
                used_fallback_encoding=encoding not in PREFERRED_ENCODINGS,
                used_replacement=False,
            )
            return DecodedText(text=text, diagnostics=diagnostics)
        except UnicodeDecodeError as exc:
            failed_attempts.append(f"{encoding}: {exc.reason} at byte {exc.start}")
        except LookupError as exc:
            failed_attempts.append(f"{encoding}: unknown encoding ({exc})")

    text = raw_bytes.decode(replacement_encoding, errors="replace")
    failed_attempts.append(f"{replacement_encoding}: replacement characters inserted")
    diagnostics = DecodeDiagnostics(
        path=path,
        encoding_used=replacement_encoding,
        attempted_encodings=ordered_encodings,
        failed_attempts=tuple(failed_attempts),
        used_fallback_encoding=False,
        used_replacement=True,
    )
    return DecodedText(text=text, diagnostics=diagnostics)


def format_decode_warning(diagnostics: DecodeDiagnostics) -> str:
    failures = "; ".join(diagnostics.failed_attempts) or "none"
    if diagnostics.used_replacement:
        mode = f"decoded with replacement using {diagnostics.encoding_used}"
    else:
        mode = f"decoded using fallback encoding {diagnostics.encoding_used}"
    return f"{mode}; failed attempts: {failures}"


def _ordered_unique_encodings(encodings: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for encoding in encodings:
        normalized = encoding.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)
