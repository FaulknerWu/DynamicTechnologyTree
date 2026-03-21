# pyright: reportMissingImports=false

from __future__ import annotations

import copy
import json
import os
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QWidget

from gui.settings_panel import SettingsPanel
from settings import Settings, settings_json_schema


def _build_panel(
    qt_app: Any,
    *,
    schema: dict[str, Any] | None = None,
) -> tuple[SettingsPanel, Settings, dict[str, Any]]:
    resolved_schema = schema or settings_json_schema()
    settings = Settings()
    panel = SettingsPanel(resolved_schema, settings)
    panel.show()
    qt_app.processEvents()
    return panel, settings, resolved_schema


def _resolve_ref(node: dict[str, Any], root_schema: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node

    prefix = "#/$defs/"
    assert ref.startswith(prefix), f"Unsupported $ref format: {ref}"

    defs = root_schema.get("$defs")
    assert isinstance(defs, dict), "Schema is missing $defs for $ref resolution"

    target_name = ref[len(prefix) :]
    target = defs.get(target_name)
    assert isinstance(target, dict), f"Schema $ref target not found: {target_name}"

    merged = dict(target)
    merged.update({key: value for key, value in node.items() if key != "$ref"})
    return merged


def _iter_leaf_fields(
    schema_node: dict[str, Any],
    *,
    root_schema: dict[str, Any] | None = None,
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    root = root_schema or schema_node
    resolved = _resolve_ref(schema_node, root)

    node_type = resolved.get("type")
    if node_type == "object":
        properties = resolved.get("properties")
        if not isinstance(properties, dict):
            return []

        fields: list[tuple[tuple[str, ...], dict[str, Any]]] = []
        for field_name, child_node in properties.items():
            if not isinstance(field_name, str) or not isinstance(child_node, dict):
                continue

            fields.extend(
                _iter_leaf_fields(
                    child_node,
                    root_schema=root,
                    path=(*path, field_name),
                )
            )
        return fields

    return [(path, resolved)]


def _field_key(path: tuple[str, ...]) -> str:
    return ".".join(path)


def _tab_key(field_schema: dict[str, Any]) -> str:
    tab = field_schema.get("tab")
    if isinstance(tab, str) and tab.strip():
        return tab.strip()
    return "settings"


def _is_raw_editor_only(field_schema: dict[str, Any]) -> bool:
    for key in ("raw_editor_only", "raw_only"):
        value = field_schema.get(key)
        if isinstance(value, bool) and value:
            return True
    return False


def _is_descendant(widget: QWidget, ancestor: QWidget) -> bool:
    current: QWidget | None = widget
    while current is not None:
        if current is ancestor:
            return True
        current = current.parentWidget()
    return False


def _set_leaf_bool_metadata(
    schema: dict[str, Any],
    path: tuple[str, ...],
    *,
    key: str,
    value: bool,
) -> None:
    assert path, "Path must point to a leaf field"

    current: dict[str, Any] = schema
    for part in path[:-1]:
        resolved = _resolve_ref(current, schema)
        properties = resolved.get("properties")
        assert isinstance(properties, dict), f"Missing object properties at '{part}'"

        next_node = properties.get(part)
        assert isinstance(next_node, dict), f"Schema path not found: {_field_key(path)}"
        current = next_node

    resolved_parent = _resolve_ref(current, schema)
    properties = resolved_parent.get("properties")
    assert isinstance(properties, dict), f"Schema path not found: {_field_key(path)}"

    leaf_node = properties.get(path[-1])
    assert isinstance(leaf_node, dict), f"Schema path not found: {_field_key(path)}"
    leaf_node[key] = value


def _assert_gui_settings_parity(panel: SettingsPanel, schema: dict[str, Any]) -> None:
    leaf_fields = _iter_leaf_fields(schema)
    assert leaf_fields, "Expected at least one Settings leaf field in schema"

    renderer = panel.settings_renderer
    for path, field_schema in leaf_fields:
        field_key = _field_key(path)
        widget = renderer.field_widgets.get(field_key)
        raw_only = _is_raw_editor_only(field_schema)

        if widget is None:
            assert raw_only, (
                f"Missing control for schema field '{field_key}'. "
                "Add an auto-control or mark it as raw-editor-only."
            )
            continue

        tab_key = _tab_key(field_schema)
        tab_widget = renderer.tab_widget_for(tab_key)
        assert tab_widget is not None, (
            f"Field '{field_key}' references tab '{tab_key}' "
            "but the tab is not rendered"
        )
        assert _is_descendant(
            widget, tab_widget
        ), f"Field '{field_key}' must render under tab '{tab_key}'"


def test_gui_settings_parity_all_leaf_fields_have_controls_in_schema_tab(
    qt_app: Any,
) -> None:
    panel, _settings, schema = _build_panel(qt_app)
    try:
        _assert_gui_settings_parity(panel, schema)
    finally:
        panel.close()
        panel.deleteLater()
        qt_app.processEvents()


def test_gui_settings_parity_catches_missing_non_raw_only_control(qt_app: Any) -> None:
    panel, _settings, schema = _build_panel(qt_app)
    try:
        removed = panel.settings_renderer.field_widgets.pop(
            "paths.base_game_path", None
        )
        assert removed is not None

        with pytest.raises(AssertionError, match="paths.base_game_path"):
            _assert_gui_settings_parity(panel, schema)
    finally:
        panel.close()
        panel.deleteLater()
        qt_app.processEvents()


def test_gui_settings_parity_raw_only_fields_are_editable_and_validated(
    qt_app: Any,
) -> None:
    schema = copy.deepcopy(settings_json_schema())
    _set_leaf_bool_metadata(
        schema,
        ("display", "max_tree_depth"),
        key="raw_editor_only",
        value=True,
    )

    panel, settings, _schema = _build_panel(qt_app, schema=schema)
    try:
        removed = panel.settings_renderer.field_widgets.pop(
            "display.max_tree_depth", None
        )
        assert removed is not None

        _assert_gui_settings_parity(panel, schema)

        payload = settings.model_dump(mode="json")
        payload["display"]["max_tree_depth"] = 9
        panel.raw_editor.text_edit.setPlainText(json.dumps(payload, indent=2))
        qt_app.processEvents()

        assert panel.raw_editor.is_valid
        assert panel.apply_raw_editor_changes() is True
        assert panel.settings is not settings
        assert panel.settings.display.max_tree_depth == 9
    finally:
        panel.close()
        panel.deleteLater()
        qt_app.processEvents()
