from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence

from config import DEFAULT_DECODE_REPLACEMENT_ENCODING, DecodeFailurePolicy
from dtt_core.clausewitz_parser import (
    Assignment,
    Atom,
    Block,
    ClausewitzNode,
    Diagnostic,
    TokenKind,
    parse,
)
from dtt_core.clausewitz_text import _atom_text
from dtt_core.file_decode import (
    DEFAULT_FAILURE_POLICY,
    DEFAULT_FALLBACK_ENCODINGS,
    PREFERRED_ENCODINGS,
    DecodeDiagnostics,
    read_text_with_diagnostics,
)


@dataclass(frozen=True)
class ModDescriptor:
    path: Path
    replace_paths: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    supported_version: str | None = None
    remote_file_id: str | None = None
    decode_diagnostics: DecodeDiagnostics | None = None
    parse_diagnostics: tuple[Diagnostic, ...] = ()


def load_descriptor(
    path: Path | str,
    *,
    preferred_encodings: Sequence[str] = PREFERRED_ENCODINGS,
    fallback_encodings: Sequence[str] = DEFAULT_FALLBACK_ENCODINGS,
    replacement_encoding: str = DEFAULT_DECODE_REPLACEMENT_ENCODING,
    on_failure: DecodeFailurePolicy = DEFAULT_FAILURE_POLICY,
) -> ModDescriptor:
    descriptor_path = Path(path)
    decoded = read_text_with_diagnostics(
        descriptor_path,
        preferred_encodings=preferred_encodings,
        fallback_encodings=fallback_encodings,
        replacement_encoding=replacement_encoding,
        on_failure=on_failure,
    )
    parse_result = parse(decoded.text, path=str(descriptor_path))

    replace_paths: list[str] = []
    dependencies: list[str] = []
    supported_version: str | None = None
    remote_file_id: str | None = None

    for item in parse_result.root.items:
        if not isinstance(item, Assignment):
            continue

        key = item.key.value.casefold()
        if key == "replace_path":
            value = _atom_text(item.value)
            if value:
                replace_paths.append(value)
            continue

        if key == "dependencies":
            dependencies.extend(_extract_dependencies(item.value))
            continue

        if key == "supported_version":
            supported_version = _atom_text(item.value)
            continue

        if key == "remote_file_id":
            remote_file_id = _atom_text(item.value)

    return ModDescriptor(
        path=descriptor_path,
        replace_paths=tuple(replace_paths),
        dependencies=tuple(dependencies),
        supported_version=supported_version,
        remote_file_id=remote_file_id,
        decode_diagnostics=decoded.diagnostics,
        parse_diagnostics=tuple(parse_result.diagnostics),
    )


class ModDescriptorLoader:
    def load_descriptor(
        self,
        path: Path | str,
        *,
        preferred_encodings: Sequence[str] = PREFERRED_ENCODINGS,
        fallback_encodings: Sequence[str] = DEFAULT_FALLBACK_ENCODINGS,
        replacement_encoding: str = DEFAULT_DECODE_REPLACEMENT_ENCODING,
        on_failure: DecodeFailurePolicy = DEFAULT_FAILURE_POLICY,
    ) -> ModDescriptor:
        return load_descriptor(
            path,
            preferred_encodings=preferred_encodings,
            fallback_encodings=fallback_encodings,
            replacement_encoding=replacement_encoding,
            on_failure=on_failure,
        )


def _extract_dependencies(node: ClausewitzNode) -> list[str]:
    if isinstance(node, Atom):
        if node.token.kind == TokenKind.STRING:
            return [node.token.value]
        return []

    if isinstance(node, Block):
        dependencies: list[str] = []
        for item in node.items:
            if isinstance(item, Atom) and item.token.kind == TokenKind.STRING:
                dependencies.append(item.token.value)
        return dependencies

    return []
