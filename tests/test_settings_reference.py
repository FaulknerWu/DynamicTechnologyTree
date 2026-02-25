"""Settings 参考文档自动生成测试。"""

from __future__ import annotations

import importlib
from typing import Any

settings_module = importlib.import_module("settings")
settings_json_schema = settings_module.settings_json_schema

ref_module = importlib.import_module("settings_reference")
generate_reference_markdown = ref_module.generate_reference_markdown
leaf_field_paths = ref_module.leaf_field_paths


def _resolve_ref(node: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        return node
    defs = root.get("$defs", {})
    target = defs.get(ref[len(prefix) :], {})
    merged = dict(target)
    merged.update({k: v for k, v in node.items() if k != "$ref"})
    return merged


def _iter_leaf_paths(
    schema_node: dict[str, Any],
    *,
    root: dict[str, Any],
    path: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    resolved = _resolve_ref(schema_node, root)
    if resolved.get("type") == "object":
        props = resolved.get("properties")
        if not isinstance(props, dict):
            return []
        leaves: list[tuple[str, ...]] = []
        for name, child in props.items():
            if isinstance(name, str) and isinstance(child, dict):
                leaves.extend(_iter_leaf_paths(child, root=root, path=(*path, name)))
        return leaves
    return [path]


def _iter_leaf_fields(
    schema_node: dict[str, Any],
    *,
    root: dict[str, Any],
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    resolved = _resolve_ref(schema_node, root)
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


def test_settings_reference_covers_all_leaves() -> None:
    schema = settings_json_schema()
    schema_paths = sorted(".".join(p) for p in _iter_leaf_paths(schema, root=schema))
    assert schema_paths, "Expected at least one Settings leaf field"

    md = generate_reference_markdown()
    missing = [p for p in schema_paths if f"`{p}`" not in md]
    assert not missing, "Settings leaf fields missing from reference:\n" + "\n".join(
        f"  - {p}" for p in missing
    )


def test_settings_reference_leaf_field_paths_matches_schema() -> None:
    schema = settings_json_schema()
    expected = sorted(".".join(p) for p in _iter_leaf_paths(schema, root=schema))
    actual = leaf_field_paths()
    assert actual == expected, (
        f"leaf_field_paths() drift.\n"
        f"  Missing: {sorted(set(expected) - set(actual))}\n"
        f"  Extra:   {sorted(set(actual) - set(expected))}"
    )


def test_settings_reference_has_all_tabs() -> None:
    localization_module = importlib.import_module("localization")
    language_code = localization_module.DEFAULT_LANGUAGE_CODE
    strings = localization_module.LOCALIZATION_STRINGS.get(language_code, {})
    schema = settings_json_schema()

    tabs: set[str] = set()
    for _path, field_schema in _iter_leaf_fields(schema, root=schema):
        tab = field_schema.get("tab")
        if isinstance(tab, str) and tab.strip():
            tabs.add(tab.strip())
    assert tabs, "Expected at least one tab in schema"

    md = generate_reference_markdown()
    # 参考文档会将“当前默认语言”的 tab 标题作为二级标题渲染出来
    missing_tabs = []
    for tab in tabs:
        title = strings.get(tab, tab)
        if f"## {title}" not in md:
            missing_tabs.append(f"{tab} (expected heading '## {title}')")
    assert not missing_tabs, "Tabs missing from reference:\n" + "\n".join(
        f"  - {t}" for t in missing_tabs
    )


def test_settings_reference_contains_defaults() -> None:
    md = generate_reference_markdown()
    assert "| 默认值 |" in md, "参考文档缺少“默认值”列"
    assert "`12`" in md, "Expected max_children_per_node default of 12"
    assert "`4`" in md, "Expected max_tree_depth default of 4"
    assert '`"utf-8-sig"`' in md, "Expected yml_encoding default"


def test_settings_reference_deterministic() -> None:
    md1 = generate_reference_markdown()
    md2 = generate_reference_markdown()
    assert md1 == md2, "Reference generation is not deterministic"
