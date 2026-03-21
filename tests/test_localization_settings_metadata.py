from __future__ import annotations

import importlib
import re
from typing import Any

settings_module = importlib.import_module("settings")
settings_json_schema = settings_module.settings_json_schema

localization_module = importlib.import_module("localization")
LOCALIZATION_STRINGS = localization_module.LOCALIZATION_STRINGS

gui_i18n_module = importlib.import_module("gui.i18n")
t = gui_i18n_module.t

_LOCALIZATION_KEY_PATTERN = re.compile(r"^[a-z0-9_]+$")
_RUNTIME_UI_KEYS = {
    "ui_label_settings_profile",
    "ui_btn_open_profile",
    "ui_btn_save_profile_as",
    "ui_hint_fix_settings",
    "ui_error_ini_not_supported",
    "ui_dialog_title_choose_settings_file",
    "ui_dialog_title_save_settings_file",
    "ui_tab_advanced",
    "ui_action_apply_json",
    "ui_settings_json_valid",
    "ui_settings_json_invalid_json",
    "ui_settings_json_schema_mismatch",
    "ui_settings_json_schema_validation_failed",
    "ui_label_paths",
    "ui_label_autodetect",
    "ui_label_localization",
    "ui_label_display",
    "ui_label_output",
    "ui_label_eligibility",
    "ui_label_schema",
}


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
    root_schema: dict[str, Any],
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    resolved = _resolve_ref(schema_node, root_schema)

    if resolved.get("type") != "object":
        return [(path, resolved)]

    properties = resolved.get("properties")
    if not isinstance(properties, dict):
        return []

    leaf_fields: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    for field_name, child_schema in properties.items():
        if not isinstance(field_name, str) or not isinstance(child_schema, dict):
            continue
        leaf_fields.extend(
            _iter_leaf_fields(
                child_schema,
                root_schema=root_schema,
                path=(*path, field_name),
            )
        )

    return leaf_fields


def _field_key(path: tuple[str, ...]) -> str:
    return ".".join(path)


def test_localization_settings_metadata() -> None:
    schema = settings_json_schema()
    leaf_fields = _iter_leaf_fields(schema, root_schema=schema)

    assert leaf_fields, "Expected at least one leaf settings field in schema"

    english_strings = LOCALIZATION_STRINGS.get("english")
    assert isinstance(
        english_strings, dict
    ), "Expected localization strings for english"

    errors: list[str] = []
    for field_path, field_schema in leaf_fields:
        field_key = _field_key(field_path)

        for metadata_key in ("label_key", "help_key"):
            raw_key = field_schema.get(metadata_key)
            if not isinstance(raw_key, str) or not raw_key.strip():
                errors.append(f"{field_key}: missing {metadata_key}")
                continue

            localization_key = raw_key.strip()
            if not _LOCALIZATION_KEY_PATTERN.fullmatch(localization_key):
                errors.append(
                    f"{field_key}: {metadata_key} must be a localization key, got {localization_key!r}"
                )
                continue

            if localization_key not in english_strings:
                errors.append(
                    f"{field_key}: {metadata_key} '{localization_key}' is missing for english"
                )
                continue

            for language in LOCALIZATION_STRINGS:
                translated = t(localization_key, language)
                if translated == localization_key:
                    errors.append(
                        f"{field_key}: {metadata_key} '{localization_key}' is not translatable for {language}"
                    )

    assert not errors, "\n".join(errors)


def test_localization_no_ini_keys() -> None:
    forbidden_exact_keys = {
        "ui_dialog_title_choose_dlc_load",
        "ui_label_dlc_load_path_optional",
        "msg_priority_localization_mods",
    }
    forbidden_substrings = ("dlc_load_path", "priority_mods")

    violations: list[str] = []
    for language, strings in LOCALIZATION_STRINGS.items():
        for key in strings:
            if key in forbidden_exact_keys or any(
                token in key for token in forbidden_substrings
            ):
                violations.append(f"{language}: {key}")

    assert not violations, "\n".join(violations)


def test_runtime_ui_localization_keys_are_translatable() -> None:
    english_strings = LOCALIZATION_STRINGS.get("english")
    assert isinstance(
        english_strings, dict
    ), "Expected localization strings for english"

    errors: list[str] = []
    for localization_key in sorted(_RUNTIME_UI_KEYS):
        if localization_key not in english_strings:
            errors.append(f"{localization_key} is missing for english")
            continue

        for language in LOCALIZATION_STRINGS:
            translated = t(localization_key, language)
            if translated == localization_key:
                errors.append(f"{localization_key} is not translatable for {language}")

    assert not errors, "\n".join(errors)
