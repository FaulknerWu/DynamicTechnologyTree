from __future__ import annotations

import configparser
import os
from typing import Callable, Optional

from PyQt6.QtCore import Qt
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

from gui.path_detector import DetectedPaths, PathDetector


LANGUAGE_OPTIONS = [
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


class ConfigEditor(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs)

        self._build_paths_tab()
        self._build_localization_tab()
        self._build_display_tab()

    def _build_paths_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        auto_detect_button = QPushButton("自动检测所有路径", tab)
        self._style_action_button(auto_detect_button)
        auto_detect_button.clicked.connect(self.auto_detect_all_paths)

        auto_row = QHBoxLayout()
        auto_row.setContentsMargins(0, 0, 0, 0)
        auto_row.addWidget(auto_detect_button)
        auto_row.addStretch()
        layout.addLayout(auto_row)

        form = QFormLayout()
        form.setSpacing(10)
        layout.addLayout(form)

        base_row, self.base_game_path_input = self._create_path_row(
            "选择群星本体安装目录",
            is_file=False,
            detect_callback=self._detect_game_path,
        )
        form.addRow("本体安装目录", base_row)

        mod_row, self.mod_folder_path_input = self._create_path_row(
            "选择 Steam 创意工坊目录",
            is_file=False,
            detect_callback=self._detect_workshop_path,
        )
        form.addRow("创意工坊目录", mod_row)

        dlc_row, self.dlc_load_path_input = self._create_path_row(
            "选择 dlc_load.json",
            is_file=True,
            file_filter="JSON Files (*.json);;All Files (*)",
            detect_callback=self._detect_dlc_load_path,
        )
        form.addRow("dlc_load.json（可选）", dlc_row)

        local_mod_row, self.local_mod_folder_path_input = self._create_path_row(
            "选择本地 MOD 目录",
            is_file=False,
            detect_callback=self._detect_local_mod_path,
        )
        form.addRow("本地 MOD 目录（可选）", local_mod_row)

        self.tabs.addTab(tab, "路径设置")

    def _build_localization_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)

        self.language_combo = QComboBox(tab)
        self.language_combo.addItems(LANGUAGE_OPTIONS)
        form.addRow("语言", self.language_combo)

        self.priority_mods_input = QLineEdit(tab)
        self.priority_mods_input.setPlaceholderText("例如: 2131014154,2131014155")
        form.addRow("优先 MOD 列表", self.priority_mods_input)

        self.tabs.addTab(tab, "本地化设置")

    def _build_display_tab(self) -> None:
        tab = QWidget(self)
        form = QFormLayout(tab)

        self.max_children_spin = QSpinBox(tab)
        self.max_children_spin.setRange(0, 999)
        form.addRow("最大子节点数 (0 = 无限制)", self.max_children_spin)

        self.max_depth_spin = QSpinBox(tab)
        self.max_depth_spin.setRange(0, 99)
        form.addRow("最大树深度 (0 = 无限制)", self.max_depth_spin)

        self.max_nodes_spin = QSpinBox(tab)
        self.max_nodes_spin.setRange(0, 9999)
        form.addRow("最大显示节点数 (0 = 无限制)", self.max_nodes_spin)

        self.tabs.addTab(tab, "显示设置")

    def _create_path_row(
        self,
        dialog_title: str,
        *,
        is_file: bool,
        file_filter: str = "All Files (*)",
        detect_callback: Optional[Callable[[], str | None]] = None,
    ) -> tuple[QWidget, QLineEdit]:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        line_edit = QLineEdit(container)
        browse_button = QPushButton("浏览...", container)
        detect_button = QPushButton("自动检测", container)
        status_label = QLabel("?", container)
        status_label.setFixedWidth(20)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_path_status(status_label, line_edit.text())

        self._style_action_button(browse_button)
        self._style_action_button(detect_button)

        layout.addWidget(line_edit)
        layout.addWidget(browse_button)
        layout.addWidget(detect_button)
        layout.addWidget(status_label)

        if is_file:
            browse_button.clicked.connect(
                lambda: self._browse_file(line_edit, dialog_title, file_filter)
            )
        else:
            browse_button.clicked.connect(lambda: self._browse_folder(line_edit, dialog_title))

        line_edit.textChanged.connect(
            lambda text: self._update_path_status(status_label, text)
        )
        if detect_callback is not None:
            detect_button.clicked.connect(
                lambda: self._apply_detected_path(line_edit, detect_callback)
            )

        return container, line_edit

    def _browse_folder(self, target: QLineEdit, title: str) -> None:
        start_dir = target.text().strip()
        directory = QFileDialog.getExistingDirectory(self, title, start_dir)
        if directory:
            target.setText(directory)

    def _browse_file(self, target: QLineEdit, title: str, file_filter: str) -> None:
        start_dir = target.text().strip()
        file_path, _ = QFileDialog.getOpenFileName(self, title, start_dir, file_filter)
        if file_path:
            target.setText(file_path)

    def load_from_config(self, config: configparser.ConfigParser) -> None:
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

        language = config.get("localization", "language", fallback="simp_chinese").strip().lower()
        if not language:
            language = "simp_chinese"
        language_index = self.language_combo.findText(language)
        if language_index == -1:
            language_index = self.language_combo.findText("simp_chinese")
        if language_index == -1:
            language_index = 0
        self.language_combo.setCurrentIndex(language_index)

        self.priority_mods_input.setText(
            config.get("localization", "priority_mods", fallback="2131014154").strip()
        )

        self.max_children_spin.setValue(self._get_int(config, "display", "max_children_per_node", 12))
        self.max_depth_spin.setValue(self._get_int(config, "display", "max_tree_depth", 4))
        self.max_nodes_spin.setValue(self._get_int(config, "display", "max_display_nodes", 128))

    def save_to_config(self, config: configparser.ConfigParser) -> None:
        self._ensure_section(config, "paths")
        config.set("paths", "base_game_path", self.base_game_path_input.text().strip())
        config.set("paths", "mod_folder_path", self.mod_folder_path_input.text().strip())
        config.set("paths", "dlc_load_path", self.dlc_load_path_input.text().strip())
        config.set(
            "paths", "local_mod_folder_path", self.local_mod_folder_path_input.text().strip()
        )

        self._ensure_section(config, "localization")
        config.set("localization", "language", self.language_combo.currentText())
        config.set("localization", "priority_mods", self.priority_mods_input.text().strip())

        self._ensure_section(config, "display")
        config.set("display", "max_children_per_node", str(self.max_children_spin.value()))
        config.set("display", "max_tree_depth", str(self.max_depth_spin.value()))
        config.set("display", "max_display_nodes", str(self.max_nodes_spin.value()))

    def validate(self) -> tuple[bool, str]:
        missing_fields = []
        if not self.base_game_path_input.text().strip():
            missing_fields.append("本体安装目录")
        if not self.mod_folder_path_input.text().strip():
            missing_fields.append("创意工坊目录")

        if missing_fields:
            return False, f"路径设置缺少必填项: {', '.join(missing_fields)}"
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
        user_data_path = PathDetector().detect_user_data_path()
        if not user_data_path:
            return None
        dlc_path = os.path.join(user_data_path, "dlc_load.json")
        return dlc_path if os.path.exists(dlc_path) else None

    @staticmethod
    def _detect_local_mod_path() -> str | None:
        user_data_path = PathDetector().detect_user_data_path()
        if not user_data_path:
            return None
        local_mod_path = os.path.join(user_data_path, "mod")
        return local_mod_path if os.path.exists(local_mod_path) else None

    @staticmethod
    def _update_path_status(label: QLabel, path_text: str) -> None:
        path = path_text.strip()
        label.setCursor(Qt.CursorShape.WhatsThisCursor)
        if not path:
            label.setText("?")
            label.setToolTip("未设置路径")
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
            label.setToolTip(f"路径有效: {path}")
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
            label.setToolTip(f"路径不存在: {path}")
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
                border: 1px solid #ccc;
                border-radius: 3px;
                background-color: #f8f8f8;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #2196f3;
            }
            QPushButton:pressed {
                background-color: #bbdefb;
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
