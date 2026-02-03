from __future__ import annotations

import configparser
import os
from typing import Callable, Optional

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import DisplayConfig, LocalizationConfig
from gui.i18n import default_language_from_system, t
from gui.path_detector import DetectedPaths, PathDetector
from localization import LOCALIZATION_STRINGS


_LANGUAGE_ORDER = [
    "english",
    "simp_chinese",
    "french",
    "german",
    "spanish",
    "russian",
    "korean",
    "japanese",
    "polish",
    "braz_por",
]


def _language_options() -> list[str]:
    # Keep a stable order, but avoid drifting away from actual supported languages.
    keys = list(LOCALIZATION_STRINGS.keys())
    seen = set()
    ordered: list[str] = []
    for lang in _LANGUAGE_ORDER:
        if lang in LOCALIZATION_STRINGS and lang not in seen:
            ordered.append(lang)
            seen.add(lang)
    for lang in sorted(keys):
        if lang not in seen:
            ordered.append(lang)
            seen.add(lang)
    return ordered


class ConfigEditor(QWidget):
    language_changed = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        self._build_paths_tab()
        self._build_localization_tab()
        self._build_display_tab()

        # Prefer a stable default language before config is loaded.
        default_lang = default_language_from_system()
        default_index = self.language_combo.findText(default_lang)
        if default_index != -1:
            self.language_combo.setCurrentIndex(default_index)

        self.language_combo.currentTextChanged.connect(self._on_language_combo_changed)
        self.retranslate_ui()

    def _current_lang(self) -> str:
        # Task constraint: derive language from the combo's currentText.
        lang = self.language_combo.currentText().strip().lower()
        return lang or "english"

    def _t(self, key: str, **kwargs: object) -> str:
        return t(key, self._current_lang(), **kwargs)

    def _on_language_combo_changed(self, lang_text: str) -> None:
        lang = (lang_text or "").strip().lower() or "english"
        self.retranslate_ui()
        self.language_changed.emit(lang)

    def retranslate_ui(self) -> None:
        lang = self._current_lang()

        # Tabs
        paths_index = self.tabs.indexOf(self.paths_tab)
        if paths_index != -1:
            self.tabs.setTabText(paths_index, t("ui_tab_paths", lang))
        localization_index = self.tabs.indexOf(self.localization_tab)
        if localization_index != -1:
            self.tabs.setTabText(localization_index, t("ui_tab_localization", lang))
        display_index = self.tabs.indexOf(self.display_tab)
        if display_index != -1:
            self.tabs.setTabText(display_index, t("ui_tab_display", lang))

        # Buttons
        self.auto_detect_all_button.setText(t("ui_btn_autodetect_all", lang))
        for button in (
            self.base_game_browse_button,
            self.mod_folder_browse_button,
            self.dlc_load_browse_button,
            self.local_mod_browse_button,
        ):
            button.setText(t("ui_btn_browse", lang))
        for button in (
            self.base_game_detect_button,
            self.mod_folder_detect_button,
            self.dlc_load_detect_button,
            self.local_mod_detect_button,
        ):
            button.setText(t("ui_btn_autodetect", lang))

        # Form labels
        self.base_game_path_label.setText(t("ui_label_base_game_path", lang))
        self.mod_folder_path_label.setText(t("ui_label_workshop_path", lang))
        self.dlc_load_path_label.setText(t("ui_label_dlc_load_path_optional", lang))
        self.local_mod_path_label.setText(t("ui_label_local_mod_path_optional", lang))

        self.language_label.setText(t("ui_label_language", lang))
        self.priority_mods_label.setText(t("ui_label_priority_mods", lang))

        self.max_children_label.setText(t("ui_label_max_children", lang))
        self.max_depth_label.setText(t("ui_label_max_depth", lang))
        self.max_nodes_label.setText(t("ui_label_max_nodes", lang))

        # Placeholders
        self.priority_mods_input.setPlaceholderText(
            t("ui_placeholder_priority_mods", lang)
        )

        # Status tooltips
        self._update_path_status(
            self.base_game_status_label, self.base_game_path_input.text(), lang
        )
        self._update_path_status(
            self.mod_folder_status_label, self.mod_folder_path_input.text(), lang
        )
        self._update_path_status(
            self.dlc_load_status_label, self.dlc_load_path_input.text(), lang
        )
        self._update_path_status(
            self.local_mod_status_label,
            self.local_mod_folder_path_input.text(),
            lang,
        )

    def _build_paths_tab(self) -> None:
        tab = QWidget(self)
        self.paths_tab = tab
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        self.auto_detect_all_button = QPushButton(tab)
        self._style_action_button(self.auto_detect_all_button)
        self.auto_detect_all_button.clicked.connect(self.auto_detect_all_paths)

        auto_row = QHBoxLayout()
        auto_row.setContentsMargins(0, 0, 0, 0)
        auto_row.addWidget(self.auto_detect_all_button)
        auto_row.addStretch()
        layout.addLayout(auto_row)

        form = QFormLayout()
        form.setSpacing(10)
        layout.addLayout(form)

        (
            base_row,
            self.base_game_path_input,
            self.base_game_browse_button,
            self.base_game_detect_button,
            self.base_game_status_label,
        ) = self._create_path_row(
            "ui_dialog_title_choose_base_game_dir",
            is_file=False,
            detect_callback=self._detect_game_path,
        )
        self.base_game_path_label = QLabel(tab)
        form.addRow(self.base_game_path_label, base_row)

        (
            mod_row,
            self.mod_folder_path_input,
            self.mod_folder_browse_button,
            self.mod_folder_detect_button,
            self.mod_folder_status_label,
        ) = self._create_path_row(
            "ui_dialog_title_choose_workshop_dir",
            is_file=False,
            detect_callback=self._detect_workshop_path,
        )
        self.mod_folder_path_label = QLabel(tab)
        form.addRow(self.mod_folder_path_label, mod_row)

        (
            dlc_row,
            self.dlc_load_path_input,
            self.dlc_load_browse_button,
            self.dlc_load_detect_button,
            self.dlc_load_status_label,
        ) = self._create_path_row(
            "ui_dialog_title_choose_dlc_load",
            is_file=True,
            file_filter_key="ui_file_filter_json",
            detect_callback=self._detect_dlc_load_path,
        )
        self.dlc_load_path_label = QLabel(tab)
        form.addRow(self.dlc_load_path_label, dlc_row)

        (
            local_mod_row,
            self.local_mod_folder_path_input,
            self.local_mod_browse_button,
            self.local_mod_detect_button,
            self.local_mod_status_label,
        ) = self._create_path_row(
            "ui_dialog_title_choose_local_mod_dir",
            is_file=False,
            detect_callback=self._detect_local_mod_path,
        )
        self.local_mod_path_label = QLabel(tab)
        form.addRow(self.local_mod_path_label, local_mod_row)

        self.tabs.addTab(tab, "")

    def _build_localization_tab(self) -> None:
        tab = QWidget(self)
        self.localization_tab = tab
        form = QFormLayout(tab)

        self.language_combo = QComboBox(tab)
        self.language_combo.addItems(_language_options())
        self.language_label = QLabel(tab)
        form.addRow(self.language_label, self.language_combo)

        self.priority_mods_input = QLineEdit(tab)
        self.priority_mods_label = QLabel(tab)
        form.addRow(self.priority_mods_label, self.priority_mods_input)

        self.tabs.addTab(tab, "")

    def _build_display_tab(self) -> None:
        tab = QWidget(self)
        self.display_tab = tab
        form = QFormLayout(tab)

        self.max_children_spin = QSpinBox(tab)
        self.max_children_spin.setRange(0, 999)
        self.max_children_label = QLabel(tab)
        form.addRow(self.max_children_label, self.max_children_spin)

        self.max_depth_spin = QSpinBox(tab)
        self.max_depth_spin.setRange(0, 99)
        self.max_depth_label = QLabel(tab)
        form.addRow(self.max_depth_label, self.max_depth_spin)

        self.max_nodes_spin = QSpinBox(tab)
        self.max_nodes_spin.setRange(0, 9999)
        self.max_nodes_label = QLabel(tab)
        form.addRow(self.max_nodes_label, self.max_nodes_spin)

        self.tabs.addTab(tab, "")

    def _create_path_row(
        self,
        dialog_title_key: str,
        *,
        is_file: bool,
        file_filter_key: str = "ui_file_filter_all",
        detect_callback: Optional[Callable[[], str | None]] = None,
    ) -> tuple[QWidget, QLineEdit, QPushButton, QPushButton, QLabel]:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        line_edit = QLineEdit(container)
        browse_button = QPushButton(container)
        detect_button = QPushButton(container)
        status_label = QLabel("?", container)
        status_label.setFixedWidth(20)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_path_status(status_label, line_edit.text(), "english")

        self._style_action_button(browse_button)
        self._style_action_button(detect_button)

        layout.addWidget(line_edit)
        layout.addWidget(browse_button)
        layout.addWidget(detect_button)
        layout.addWidget(status_label)

        if is_file:
            browse_button.clicked.connect(
                lambda _checked=False: self._browse_file(
                    line_edit, dialog_title_key, file_filter_key
                )
            )
        else:
            browse_button.clicked.connect(
                lambda _checked=False: self._browse_folder(line_edit, dialog_title_key)
            )

        line_edit.textChanged.connect(
            lambda text: self._update_path_status(
                status_label, text, self._current_lang()
            )
        )
        if detect_callback is not None:
            detect_button.clicked.connect(
                lambda _checked=False: self._apply_detected_path(
                    line_edit, detect_callback
                )
            )
        else:
            detect_button.setEnabled(False)

        return container, line_edit, browse_button, detect_button, status_label

    def _browse_folder(self, target: QLineEdit, title_key: str) -> None:
        start_dir = target.text().strip()
        directory = QFileDialog.getExistingDirectory(
            self, self._t(title_key), start_dir
        )
        if directory:
            target.setText(directory)

    def _browse_file(
        self, target: QLineEdit, title_key: str, file_filter_key: str
    ) -> None:
        start_dir = target.text().strip()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._t(title_key),
            start_dir,
            self._t(file_filter_key),
        )
        if file_path:
            target.setText(file_path)

    def load_from_config(self, config: configparser.ConfigParser) -> None:
        default_loc = LocalizationConfig()
        default_display = DisplayConfig()

        self.base_game_path_input.setText(
            config.get("paths", "base_game_path", fallback="").strip()
        )
        self.mod_folder_path_input.setText(
            config.get("paths", "mod_folder_path", fallback="").strip()
        )
        self.dlc_load_path_input.setText(
            config.get("paths", "dlc_load_path", fallback="").strip()
        )
        self.local_mod_folder_path_input.setText(
            config.get("paths", "local_mod_folder_path", fallback="").strip()
        )

        language = config.get("localization", "language", fallback="").strip().lower()
        if not language or language not in LOCALIZATION_STRINGS:
            language = default_language_from_system()
        language_index = self.language_combo.findText(language)
        if language_index == -1:
            language_index = self.language_combo.findText(
                default_loc.target_language_code
            )
        if language_index == -1:
            language_index = 0
        with QSignalBlocker(self.language_combo):
            self.language_combo.setCurrentIndex(language_index)
        self.retranslate_ui()

        self.priority_mods_input.setText(
            config.get(
                "localization",
                "priority_mods",
                fallback=",".join(default_loc.priority_localization_mod_ids),
            ).strip()
        )

        self.max_children_spin.setValue(
            self._get_int(
                config,
                "display",
                "max_children_per_node",
                default_display.max_children_per_node,
            )
        )
        self.max_depth_spin.setValue(
            self._get_int(
                config,
                "display",
                "max_tree_depth",
                default_display.max_tree_depth,
            )
        )
        self.max_nodes_spin.setValue(
            self._get_int(
                config,
                "display",
                "max_display_nodes",
                default_display.max_display_nodes,
            )
        )

    def save_to_config(self, config: configparser.ConfigParser) -> None:
        self._ensure_section(config, "paths")
        config.set("paths", "base_game_path", self.base_game_path_input.text().strip())
        config.set(
            "paths", "mod_folder_path", self.mod_folder_path_input.text().strip()
        )
        config.set("paths", "dlc_load_path", self.dlc_load_path_input.text().strip())
        config.set(
            "paths",
            "local_mod_folder_path",
            self.local_mod_folder_path_input.text().strip(),
        )

        self._ensure_section(config, "localization")
        config.set("localization", "language", self.language_combo.currentText())
        config.set(
            "localization", "priority_mods", self.priority_mods_input.text().strip()
        )

        self._ensure_section(config, "display")
        config.set(
            "display", "max_children_per_node", str(self.max_children_spin.value())
        )
        config.set("display", "max_tree_depth", str(self.max_depth_spin.value()))
        config.set("display", "max_display_nodes", str(self.max_nodes_spin.value()))

    def validate(self) -> tuple[bool, str]:
        lang = self._current_lang()
        missing_fields: list[str] = []
        if not self.base_game_path_input.text().strip():
            missing_fields.append(t("ui_field_base_game_path", lang))
        if not self.mod_folder_path_input.text().strip():
            missing_fields.append(t("ui_field_workshop_path", lang))

        if missing_fields:
            return False, t(
                "ui_error_missing_required_paths",
                lang,
                fields=", ".join(missing_fields),
            )
        return True, ""

    def auto_detect_all_paths(self) -> None:
        detected = PathDetector().detect_all()
        self.apply_detected_paths(detected)

    def apply_detected_paths(self, detected: DetectedPaths) -> None:
        self._set_if_empty(self.base_game_path_input, detected.game_path)
        self._set_if_empty(self.mod_folder_path_input, detected.workshop_path)
        self._set_if_empty(self.dlc_load_path_input, detected.dlc_load_path)
        self._set_if_empty(self.local_mod_folder_path_input, detected.local_mod_path)

    @staticmethod
    def _set_if_empty(target: QLineEdit, value: str | None) -> None:
        if not target.text().strip() and value:
            target.setText(value)

    @staticmethod
    def _apply_detected_path(
        target: QLineEdit,
        detect_callback: Callable[[], str | None],
    ) -> None:
        detected = detect_callback()
        if detected:
            target.setText(detected)

    @staticmethod
    def _detect_game_path() -> str | None:
        return PathDetector().detect_game_path()

    @staticmethod
    def _detect_workshop_path() -> str | None:
        return PathDetector().detect_workshop_path()

    @staticmethod
    def _detect_dlc_load_path() -> str | None:
        return PathDetector().detect_dlc_load_path()

    @staticmethod
    def _detect_local_mod_path() -> str | None:
        return PathDetector().detect_local_mod_path()

    @staticmethod
    def _update_path_status(label: QLabel, path_text: str, lang: str) -> None:
        path = path_text.strip()
        label.setCursor(Qt.CursorShape.WhatsThisCursor)
        if not path:
            label.setText("?")
            label.setToolTip(t("ui_tooltip_path_not_set", lang))
            label.setStyleSheet("""
                QLabel {
                    color: #9e9e9e;
                    font-weight: bold;
                }
                QLabel:hover {
                    color: #616161;
                    background-color: #f5f5f5;
                    border-radius: 3px;
                }
            """)
        elif os.path.exists(path):
            label.setText("✓")
            label.setToolTip(t("ui_tooltip_path_valid", lang, path=path))
            label.setStyleSheet("""
                QLabel {
                    color: #2e7d32;
                    font-weight: bold;
                }
                QLabel:hover {
                    color: #1b5e20;
                    background-color: #e8f5e9;
                    border-radius: 3px;
                }
            """)
        else:
            label.setText("✗")
            label.setToolTip(t("ui_tooltip_path_missing", lang, path=path))
            label.setStyleSheet("""
                QLabel {
                    color: #c62828;
                    font-weight: bold;
                }
                QLabel:hover {
                    color: #b71c1c;
                    background-color: #ffebee;
                    border-radius: 3px;
                }
            """)

    @staticmethod
    def _style_action_button(button: QPushButton) -> None:
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet("""
            QPushButton {
                padding: 4px 10px;
                margin: 2px;
                border: 1px solid palette(mid);
                border-radius: 3px;
                background-color: palette(button);
                color: palette(buttonText);
            }
            QPushButton:hover {
                background-color: palette(midlight);
                border-color: palette(highlight);
            }
            QPushButton:pressed {
                background-color: palette(mid);
            }
            QPushButton:disabled {
                background-color: palette(window);
                color: palette(mid);
                border-color: palette(mid);
            }
        """)

    @staticmethod
    def _ensure_section(config: configparser.ConfigParser, section: str) -> None:
        if not config.has_section(section):
            config.add_section(section)

    @staticmethod
    def _get_int(
        config: configparser.ConfigParser,
        section: str,
        option: str,
        fallback: int,
    ) -> int:
        try:
            value = config.getint(section, option, fallback=fallback)
        except ValueError:
            value = fallback
        return value
