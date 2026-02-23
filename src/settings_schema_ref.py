from __future__ import annotations

from typing import Any

_REF_PREFIX = "#/$defs/"


def resolve_schema_ref(
    node: dict[str, Any],
    root_schema: dict[str, Any],
    *,
    strict: bool,
) -> dict[str, Any]:
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node

    if not ref.startswith(_REF_PREFIX):
        if strict:
            raise ValueError(f"Unsupported $ref format: {ref}")
        return node

    defs = root_schema.get("$defs")
    if not isinstance(defs, dict):
        if strict:
            raise ValueError("Schema is missing $defs for $ref resolution")
        defs = {}

    target_name = ref[len(_REF_PREFIX) :]
    target = defs.get(target_name)
    if not isinstance(target, dict):
        if strict:
            raise ValueError(f"Schema $ref target not found: {target_name}")
        target = {}

    merged = dict(target)
    merged.update({key: value for key, value in node.items() if key != "$ref"})
    return merged

