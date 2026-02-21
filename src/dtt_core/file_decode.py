from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

from config import (
    DEFAULT_DECODE_FALLBACK_ENCODINGS,
    DEFAULT_DECODE_PREFERRED_ENCODINGS,
    DEFAULT_DECODE_REPLACEMENT_ENCODING,
    DecodeFailurePolicy,
)

PREFERRED_ENCODINGS: tuple[str, ...] = DEFAULT_DECODE_PREFERRED_ENCODINGS
DEFAULT_FALLBACK_ENCODINGS: tuple[str, ...] = DEFAULT_DECODE_FALLBACK_ENCODINGS
DEFAULT_FAILURE_POLICY: DecodeFailurePolicy = "replace"


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
    preferred_encodings: Sequence[str] = PREFERRED_ENCODINGS,
    fallback_encodings: Sequence[str] = DEFAULT_FALLBACK_ENCODINGS,
    replacement_encoding: str = DEFAULT_DECODE_REPLACEMENT_ENCODING,
    on_failure: DecodeFailurePolicy = DEFAULT_FAILURE_POLICY,
) -> DecodedText:
    raw_bytes = path.read_bytes()
    normalized_preferred = _ordered_unique_encodings(preferred_encodings)
    ordered_encodings = _ordered_unique_encodings(
        (*normalized_preferred, *fallback_encodings)
    )
    preferred_encoding_set = set(normalized_preferred)
    failed_attempts: list[str] = []

    for encoding in ordered_encodings:
        try:
            text = raw_bytes.decode(encoding)
            diagnostics = DecodeDiagnostics(
                path=path,
                encoding_used=encoding,
                attempted_encodings=ordered_encodings,
                failed_attempts=tuple(failed_attempts),
                used_fallback_encoding=encoding not in preferred_encoding_set,
                used_replacement=False,
            )
            return DecodedText(text=text, diagnostics=diagnostics)
        except UnicodeDecodeError as exc:
            failed_attempts.append(f"{encoding}: {exc.reason} at byte {exc.start}")
        except LookupError as exc:
            failed_attempts.append(f"{encoding}: unknown encoding ({exc})")

    normalized_replacement = _normalize_encoding_name(replacement_encoding)
    if not normalized_replacement:
        raise ValueError("replacement_encoding must be non-empty")

    if on_failure == "strict":
        failure_summary = "; ".join(failed_attempts) or "no encodings were attempted"
        raise UnicodeDecodeError(
            normalized_replacement,
            raw_bytes,
            0,
            len(raw_bytes),
            f"all configured decode attempts failed ({failure_summary})",
        )

    if on_failure != "replace":
        raise ValueError("on_failure must be one of: replace, strict")

    text = raw_bytes.decode(normalized_replacement, errors="replace")
    failed_attempts.append(f"{normalized_replacement}: replacement characters inserted")
    diagnostics = DecodeDiagnostics(
        path=path,
        encoding_used=normalized_replacement,
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
        normalized = _normalize_encoding_name(encoding)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _normalize_encoding_name(value: str) -> str:
    return str(value).strip().lower()
