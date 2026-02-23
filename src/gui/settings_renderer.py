from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable

from pydantic import ValidationError  # pyright: ignore[reportMissingImports]
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from settings import Settings
from settings_schema_ref import resolve_schema_ref

SUPPORTED_SCHEMA_SUBSET: tuple[str, ...] = (
    "boolean",
    "integer",
    "number",
    "string",
    "string enum",
    "object",
    "array[primitive]",
)

_INT_MIN = -(2**31)
_INT_MAX = (2**31) - 1
_FLOAT_MIN = -1_000_000_000.0
_FLOAT_MAX = 1_000_000_000.0
_INVALID_STYLE = "border: 1px solid #c62828;"

Translator = Callable[[str], str]
ValidationChangedCallback = Callable[[bool, str], None]


@dataclass(frozen=True)
class _FieldSchema:
    path: tuple[str, ...]
    schema: dict[str, Any]


@dataclass
class _EditorBundle:
    widget: QWidget
    invalid_target: QWidget
    read_value: Callable[[], Any]
    write_value: Callable[[Any], None]
    connect_change: Callable[[Callable[[], None]], object]


@dataclass
class _FieldBinding:
    path: tuple[str, ...]
    key: str
    schema: dict[str, Any]
    editor: QWidget
    label_widget: QLabel
    invalid_target: QWidget
    error_label: QLabel
    read_value: Callable[[], Any]
    write_value: Callable[[Any], None]


@dataclass
class _GroupSection:
    box: QGroupBox
    form: QFormLayout


@dataclass
class _TabSection:
    widget: QWidget
    layout: QVBoxLayout
    groups: dict[str, _GroupSection]


class PathFieldWidget(QWidget):
    text_changed = pyqtSignal(str)
    browse_clicked = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        browse_button_text: str = "Browse",
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.line_edit = QLineEdit(self)
        self.browse_button = QPushButton(browse_button_text, self)
        self.browse_button.setEnabled(False)

        layout.addWidget(self.line_edit)
        layout.addWidget(self.browse_button)

        self.line_edit.textChanged.connect(self.text_changed.emit)
        self.browse_button.clicked.connect(self.browse_clicked.emit)

    def text(self) -> str:
        return self.line_edit.text()

    def setText(self, value: str) -> None:
        self.line_edit.setText(value)


class SettingsRenderer:
    def __init__(
        self,
        schema: dict[str, Any],
        settings: Settings,
        *,
        parent: QWidget | None = None,
        translate: Translator | None = None,
        on_validation_changed: ValidationChangedCallback | None = None,
    ) -> None:
        self.schema = schema
        self.settings = settings
        self._translate = translate or (lambda key: key)
        self._on_validation_changed = on_validation_changed
        self.validation_runs = 0
        self.validation_errors: dict[str, str] = {}
        self._syncing = False

        self.widget = QWidget(parent)
        self._root_layout = QVBoxLayout(self.widget)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(8)

        self.tabs_widget = QTabWidget(self.widget)
        self._root_layout.addWidget(self.tabs_widget)

        self._tabs: dict[str, _TabSection] = {}
        self._bindings_by_path: dict[tuple[str, ...], _FieldBinding] = {}
        self.field_widgets: dict[str, QWidget] = {}
        self.field_labels: dict[str, QLabel] = {}

        for field in _collect_leaf_fields(self.schema):
            self._add_field(field)

        self.refresh_from_settings()

    def widget_for(self, field_path: str) -> QWidget:
        return self.field_widgets[field_path]

    def tab_widget_for(self, tab_key: str) -> QWidget | None:
        section = self._tabs.get(tab_key)
        if section is None:
            return None
        return section.widget

    def label_for(self, field_path: str) -> QLabel:
        return self.field_labels[field_path]

    def error_for(self, field_path: str) -> str | None:
        return self.validation_errors.get(field_path)

    def refresh_from_settings(self) -> None:
        self._syncing = True
        try:
            for path, binding in self._bindings_by_path.items():
                binding.write_value(_read_path(self.settings, path))
        finally:
            self._syncing = False
        self.validate()

    def retranslate(self, translate: Translator | None = None) -> None:
        if translate is not None:
            self._translate = translate

        for tab_key, section in self._tabs.items():
            tab_index = self.tabs_widget.indexOf(section.widget)
            if tab_index != -1:
                self.tabs_widget.setTabText(
                    tab_index, _human_label(tab_key, self._translate)
                )

            for group_key, group in section.groups.items():
                group.box.setTitle(_human_label(group_key, self._translate))

        for binding in self._bindings_by_path.values():
            field_schema = _FieldSchema(path=binding.path, schema=binding.schema)
            help_text = _help_for_field(field_schema, self._translate)
            binding.label_widget.setText(
                _label_for_field(field_schema, self._translate)
            )
            binding.label_widget.setToolTip(help_text)
            binding.editor.setToolTip(help_text)

    def validate(self) -> bool:
        self.validation_runs += 1
        payload = self.settings.model_dump(mode="python", round_trip=True)

        try:
            Settings.model_validate(payload, strict=True)
        except ValidationError as exc:
            errors = self._map_validation_errors(exc)
            self.validation_errors = errors
            self._apply_validation_feedback(errors)
            first_key, first_message = next(iter(errors.items()), ("", "Invalid value"))
            if first_key:
                self._emit_validation_changed(False, f"{first_key}: {first_message}")
            else:
                self._emit_validation_changed(False, first_message)
            return False

        self.validation_errors = {}
        self._apply_validation_feedback({})
        self._emit_validation_changed(True, "")
        return True

    def _emit_validation_changed(self, is_valid: bool, error_message: str) -> None:
        if self._on_validation_changed is None:
            return
        self._on_validation_changed(is_valid, error_message)

    def _add_field(self, field: _FieldSchema) -> None:
        tab_key = _meta_str(field.schema, "tab", default="settings")
        group_key = _meta_str(field.schema, "group", default="general")
        form_layout = self._ensure_group_form(tab_key, group_key)

        bundle = _build_editor(field)
        field_key = _path_to_key(field.path)
        field_label = _label_for_field(field, self._translate)
        help_text = _help_for_field(field, self._translate)

        label = QLabel(field_label, self.widget)
        if help_text:
            label.setToolTip(help_text)

        if help_text:
            bundle.widget.setToolTip(help_text)

        bundle.widget.setObjectName(f"settings-field-{field_key.replace('.', '-')}")

        field_container = QWidget(self.widget)
        container_layout = QVBoxLayout(field_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)
        container_layout.addWidget(bundle.widget)

        error_label = QLabel("", field_container)
        error_label.setStyleSheet("color: #c62828;")
        error_label.setVisible(False)
        container_layout.addWidget(error_label)

        form_layout.addRow(label, field_container)

        binding = _FieldBinding(
            path=field.path,
            key=field_key,
            schema=field.schema,
            editor=bundle.widget,
            label_widget=label,
            invalid_target=bundle.invalid_target,
            error_label=error_label,
            read_value=bundle.read_value,
            write_value=bundle.write_value,
        )
        self._bindings_by_path[field.path] = binding
        self.field_widgets[field_key] = bundle.widget
        self.field_labels[field_key] = label

        bundle.connect_change(
            lambda current_binding=binding: self._on_field_changed(current_binding)
        )

    def _ensure_group_form(self, tab_key: str, group_key: str) -> QFormLayout:
        section = self._tabs.get(tab_key)
        if section is None:
            tab_widget = QWidget(self.tabs_widget)
            tab_layout = QVBoxLayout(tab_widget)
            tab_layout.setContentsMargins(10, 10, 10, 10)
            tab_layout.setSpacing(8)

            section = _TabSection(widget=tab_widget, layout=tab_layout, groups={})
            self._tabs[tab_key] = section
            self.tabs_widget.addTab(tab_widget, _human_label(tab_key, self._translate))

        group = section.groups.get(group_key)
        if group is not None:
            return group.form

        group_box = QGroupBox(_human_label(group_key, self._translate), section.widget)
        form = QFormLayout(group_box)
        form.setSpacing(6)
        section.layout.addWidget(group_box)
        section.groups[group_key] = _GroupSection(box=group_box, form=form)
        return form

    def _on_field_changed(self, binding: _FieldBinding) -> None:
        if self._syncing:
            return

        value = binding.read_value()
        _write_path(self.settings, binding.path, value)
        self.validate()

    def _map_validation_errors(self, exc: ValidationError) -> dict[str, str]:
        errors: dict[str, str] = {}
        for error in exc.errors(include_url=False):
            raw_loc = error.get("loc", ())
            if not isinstance(raw_loc, tuple):
                continue

            binding = _find_closest_binding(raw_loc, self._bindings_by_path)
            if binding is None or binding.key in errors:
                continue

            errors[binding.key] = str(error.get("msg", "Invalid value"))
        return errors

    def _apply_validation_feedback(self, errors: dict[str, str]) -> None:
        for binding in self._bindings_by_path.values():
            message = errors.get(binding.key)
            if message:
                binding.error_label.setText(message)
                binding.error_label.setVisible(True)
                binding.invalid_target.setStyleSheet(_INVALID_STYLE)
                continue

            binding.error_label.clear()
            binding.error_label.setVisible(False)
            binding.invalid_target.setStyleSheet("")


def render_settings_fields(
    schema: dict[str, Any],
    settings: Settings,
    *,
    parent: QWidget | None = None,
    translate: Translator | None = None,
    on_validation_changed: ValidationChangedCallback | None = None,
) -> SettingsRenderer:
    return SettingsRenderer(
        schema,
        settings,
        parent=parent,
        translate=translate,
        on_validation_changed=on_validation_changed,
    )


def _collect_leaf_fields(
    schema_node: dict[str, Any],
    *,
    root_schema: dict[str, Any] | None = None,
    path: tuple[str, ...] = (),
) -> list[_FieldSchema]:
    root = root_schema or schema_node
    resolved = resolve_schema_ref(schema_node, root, strict=True)

    node_type = resolved.get("type")
    if node_type == "object":
        properties = resolved.get("properties")
        if not isinstance(properties, dict):
            return []

        fields: list[_FieldSchema] = []
        for field_name, child_node in properties.items():
            if not isinstance(field_name, str) or not isinstance(child_node, dict):
                continue

            fields.extend(
                _collect_leaf_fields(
                    child_node,
                    root_schema=root,
                    path=(*path, field_name),
                )
            )
        return fields

    if node_type == "array":
        item_schema = resolved.get("items")
        item_type = item_schema.get("type") if isinstance(item_schema, dict) else None
        if item_type not in {"boolean", "integer", "number", "string"}:
            raise ValueError(
                "Unsupported schema field "
                f"'{_path_to_key(path)}': arrays must contain primitive item types"
            )
        return [_FieldSchema(path=path, schema=resolved)]

    if node_type in {"boolean", "integer", "number", "string"}:
        return [_FieldSchema(path=path, schema=resolved)]

    raise ValueError(
        "Unsupported schema field "
        f"'{_path_to_key(path)}' with type '{node_type}'. "
        f"Supported subset: {', '.join(SUPPORTED_SCHEMA_SUBSET)}"
    )


def _build_editor(field: _FieldSchema) -> _EditorBundle:
    schema = field.schema
    schema_type = schema.get("type")

    if schema_type == "boolean":
        checkbox = QCheckBox()
        return _EditorBundle(
            widget=checkbox,
            invalid_target=checkbox,
            read_value=checkbox.isChecked,
            write_value=lambda value: checkbox.setChecked(bool(value)),
            connect_change=lambda callback: checkbox.stateChanged.connect(
                lambda _state: callback()
            ),
        )

    if schema_type == "integer":
        spin = QSpinBox()
        min_value, max_value = _int_bounds(schema)
        spin.setRange(min_value, max_value)

        default_value = _int_default(schema, min_value)

        def _write_int(value: Any) -> None:
            try:
                candidate = int(value)
            except (TypeError, ValueError):
                candidate = default_value
            spin.setValue(max(min_value, min(max_value, candidate)))

        return _EditorBundle(
            widget=spin,
            invalid_target=spin,
            read_value=spin.value,
            write_value=_write_int,
            connect_change=lambda callback: spin.valueChanged.connect(
                lambda _value: callback()
            ),
        )

    if schema_type == "number":
        spin = QDoubleSpinBox()
        min_value, max_value = _float_bounds(schema)
        spin.setRange(min_value, max_value)
        spin.setDecimals(6)

        default_value = _float_default(schema, min_value)

        def _write_float(value: Any) -> None:
            try:
                candidate = float(value)
            except (TypeError, ValueError):
                candidate = default_value
            spin.setValue(max(min_value, min(max_value, candidate)))

        return _EditorBundle(
            widget=spin,
            invalid_target=spin,
            read_value=spin.value,
            write_value=_write_float,
            connect_change=lambda callback: spin.valueChanged.connect(
                lambda _value: callback()
            ),
        )

    if schema_type == "string" and isinstance(schema.get("enum"), list):
        combo = QComboBox()
        combo.setEditable(True)

        enum_values = [str(item) for item in schema.get("enum", [])]
        combo.addItems(enum_values)

        def _write_enum(value: Any) -> None:
            text = "" if value is None else str(value)
            if text in enum_values:
                combo.setCurrentText(text)
                return
            combo.setEditText(text)

        return _EditorBundle(
            widget=combo,
            invalid_target=combo,
            read_value=combo.currentText,
            write_value=_write_enum,
            connect_change=lambda callback: combo.currentTextChanged.connect(
                lambda _text: callback()
            ),
        )

    if schema_type == "string" and _is_path_like(field):
        path_widget = PathFieldWidget()
        return _EditorBundle(
            widget=path_widget,
            invalid_target=path_widget.line_edit,
            read_value=path_widget.text,
            write_value=lambda value: path_widget.setText(
                "" if value is None else str(value)
            ),
            connect_change=lambda callback: path_widget.text_changed.connect(
                lambda _text: callback()
            ),
        )

    if schema_type == "string":
        line_edit = QLineEdit()
        return _EditorBundle(
            widget=line_edit,
            invalid_target=line_edit,
            read_value=line_edit.text,
            write_value=lambda value: line_edit.setText(
                "" if value is None else str(value)
            ),
            connect_change=lambda callback: line_edit.textChanged.connect(
                lambda _text: callback()
            ),
        )

    if schema_type == "array":
        line_edit = QLineEdit()
        line_edit.setPlaceholderText('["value1", "value2"]')

        def _read_array() -> Any:
            raw = line_edit.text().strip()
            if not raw:
                return []
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw

        def _write_array(value: Any) -> None:
            if isinstance(value, list):
                line_edit.setText(json.dumps(value, ensure_ascii=True))
                return
            line_edit.setText("" if value is None else str(value))

        return _EditorBundle(
            widget=line_edit,
            invalid_target=line_edit,
            read_value=_read_array,
            write_value=_write_array,
            connect_change=lambda callback: line_edit.textChanged.connect(
                lambda _text: callback()
            ),
        )

    raise ValueError(
        f"Unsupported field type at {_path_to_key(field.path)}: {schema_type}"
    )


def _label_for_field(field: _FieldSchema, translate: Translator) -> str:
    label_key = _meta_str(field.schema, "label_key")
    if label_key:
        return translate(label_key)

    title = field.schema.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()

    return _human_label(field.path[-1], translate)


def _help_for_field(field: _FieldSchema, translate: Translator) -> str:
    help_key = _meta_str(field.schema, "help_key")
    if not help_key:
        return ""
    return translate(help_key)


def _is_path_like(field: _FieldSchema) -> bool:
    widget_hint = field.schema.get("widget")
    if isinstance(widget_hint, str) and widget_hint.lower() == "path":
        return True

    group = field.schema.get("group")
    if isinstance(group, str) and group == "paths":
        return True

    return field.path[-1].endswith("_path")


def _find_closest_binding(
    location: tuple[Any, ...],
    bindings: dict[tuple[str, ...], _FieldBinding],
) -> _FieldBinding | None:
    for end in range(len(location), 0, -1):
        candidate = location[:end]
        if all(isinstance(part, str) for part in candidate):
            match = bindings.get(candidate)
            if match is not None:
                return match
    return None


def _meta_str(schema: dict[str, Any], key: str, *, default: str = "") -> str:
    value = schema.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _human_label(key: str, translate: Translator) -> str:
    translated = translate(key)
    if translated != key:
        return translated
    return key.replace("_", " ").title()


def _path_to_key(path: tuple[str, ...]) -> str:
    return ".".join(path)


def _read_path(root: Any, path: tuple[str, ...]) -> Any:
    current = root
    for part in path:
        current = getattr(current, part)
    return current


def _write_path(root: Any, path: tuple[str, ...], value: Any) -> None:
    parent = root
    for part in path[:-1]:
        parent = getattr(parent, part)
    setattr(parent, path[-1], value)


def _int_bounds(schema: dict[str, Any]) -> tuple[int, int]:
    minimum = _to_int(schema.get("minimum"), default=_INT_MIN)
    maximum = _to_int(schema.get("maximum"), default=_INT_MAX)

    exclusive_minimum = schema.get("exclusiveMinimum")
    if isinstance(exclusive_minimum, (int, float)) and not isinstance(
        exclusive_minimum, bool
    ):
        minimum = max(minimum, int(exclusive_minimum) + 1)

    exclusive_maximum = schema.get("exclusiveMaximum")
    if isinstance(exclusive_maximum, (int, float)) and not isinstance(
        exclusive_maximum, bool
    ):
        maximum = min(maximum, int(exclusive_maximum) - 1)

    if minimum > maximum:
        return maximum, minimum
    return minimum, maximum


def _int_default(schema: dict[str, Any], fallback: int) -> int:
    return _to_int(schema.get("default"), default=fallback)


def _to_int(value: Any, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _float_bounds(schema: dict[str, Any]) -> tuple[float, float]:
    minimum = _to_float(schema.get("minimum"), default=_FLOAT_MIN)
    maximum = _to_float(schema.get("maximum"), default=_FLOAT_MAX)

    exclusive_minimum = schema.get("exclusiveMinimum")
    if isinstance(exclusive_minimum, (int, float)) and not isinstance(
        exclusive_minimum, bool
    ):
        minimum = max(minimum, float(exclusive_minimum) + 1e-9)

    exclusive_maximum = schema.get("exclusiveMaximum")
    if isinstance(exclusive_maximum, (int, float)) and not isinstance(
        exclusive_maximum, bool
    ):
        maximum = min(maximum, float(exclusive_maximum) - 1e-9)

    if minimum > maximum:
        return maximum, minimum
    return minimum, maximum


def _float_default(schema: dict[str, Any], fallback: float) -> float:
    return _to_float(schema.get("default"), default=fallback)


def _to_float(value: Any, *, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


__all__ = [
    "PathFieldWidget",
    "SUPPORTED_SCHEMA_SUBSET",
    "SettingsRenderer",
    "render_settings_fields",
]
