"""Auto-generate a Settings reference page from the Pydantic schema.

Reads ``settings_json_schema()`` and ``Settings()`` defaults, resolves
English label/help text from ``LOCALIZATION_STRINGS``, and emits a
grouped Markdown document.  No Qt dependency required.
"""

from __future__ import annotations

import json
from typing import Any

from settings_schema_ref import resolve_schema_ref


def _iter_leaf_fields(
    schema_node: dict[str, Any],
    *,
    root: dict[str, Any],
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    resolved = resolve_schema_ref(schema_node, root, strict=False)
    if resolved.get("type") == "object":
        props = resolved.get("properties")
        if not isinstance(props, dict):
            return []
        leaves: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        for name, child in props.items():
            if isinstance(name, str) and isinstance(child, dict):
                leaves.extend(_iter_leaf_fields(child, root=root, path=(*path, name)))
        return leaves
    return [(path, resolved)]


def _get_nested(obj: Any, path: tuple[str, ...]) -> Any:
    current = obj
    for part in path:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


# Preferred tab display order; anything unlisted sorts alphabetically after.
_TAB_ORDER = [
    "ui_tab_paths",
    "ui_tab_localization",
    "ui_tab_display",
    "ui_tab_output",
]


def _tab_sort_key(tab: str) -> tuple[int, str]:
    try:
        return (_TAB_ORDER.index(tab), tab)
    except ValueError:
        return (len(_TAB_ORDER), tab)


def _format_default(value: Any) -> str:
    if isinstance(value, str):
        return f'`"{value}"`' if value else '`""`'
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, (int, float)):
        return f"`{value}`"
    if isinstance(value, list):
        return f"`{json.dumps(value)}`"
    if value is None:
        return "`null`"
    return f"`{value}`"


def generate_reference_markdown() -> str:
    from localization import LOCALIZATION_STRINGS
    from settings import Settings, settings_json_schema

    schema = settings_json_schema()
    defaults_obj = Settings()
    defaults = defaults_obj.model_dump(mode="json")
    english = LOCALIZATION_STRINGS.get("english", {})

    leaves = _iter_leaf_fields(schema, root=schema)

    # Group by tab
    by_tab: dict[str, list[tuple[str, str, str, str]]] = {}
    for path, field_schema in leaves:
        dotted = ".".join(path)
        tab = field_schema.get("tab", "settings")
        label_key = field_schema.get("label_key", "")
        help_key = field_schema.get("help_key", "")
        label = str(english.get(label_key, label_key))
        help_text = str(english.get(help_key, help_key))
        default_val = _get_nested(defaults, path)
        formatted_default = _format_default(default_val)

        by_tab.setdefault(tab, []).append((dotted, label, help_text, formatted_default))

    # Sort fields within each tab by dotted path
    for tab in by_tab:
        by_tab[tab].sort(key=lambda t: t[0])

    # Build markdown
    lines: list[str] = [
        "# Settings Reference",
        "",
        "Auto-generated from the Settings schema. Do not edit by hand.",
        "",
        "Re-generate with:",
        "",
        "```bash",
        "python -m settings_reference",
        "```",
        "",
    ]

    sorted_tabs = sorted(by_tab.keys(), key=_tab_sort_key)
    for tab in sorted_tabs:
        tab_title = english.get(tab, tab)
        lines.append(f"## {tab_title}")
        lines.append("")
        lines.append("| Field | Label | Description | Default |")
        lines.append("|-------|-------|-------------|---------|")
        for dotted, label, help_text, default in by_tab[tab]:
            # Escape pipes in cell content
            safe_label = label.replace("|", "\\|")
            safe_help = help_text.replace("|", "\\|")
            safe_default = default.replace("|", "\\|")
            lines.append(
                f"| `{dotted}` | {safe_label} | {safe_help} | {safe_default} |"
            )
        lines.append("")

    return "\n".join(lines)


def leaf_field_paths() -> list[str]:
    """Return sorted dotted paths for every Settings leaf field."""
    from settings import settings_json_schema

    schema = settings_json_schema()
    leaves = _iter_leaf_fields(schema, root=schema)
    return sorted(".".join(path) for path, _ in leaves)


def main() -> None:
    import pathlib
    import sys

    md = generate_reference_markdown()
    out = (
        pathlib.Path(__file__).resolve().parent.parent
        / "docs"
        / "settings-reference.md"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
