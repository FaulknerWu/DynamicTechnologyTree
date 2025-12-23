from __future__ import annotations

import configparser
from typing import Optional

from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


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
        form = QFormLayout(tab)

        base_row, self.base_game_path_input = self._create_path_row(
            "选择群星本体安装目录",
            is_file=False,
        )
        form.addRow("本体安装目录", base_row)

        mod_row, self.mod_folder_path_input = self._create_path_row(
            "选择 Steam 创意工坊目录",
            is_file=False,
        )
        form.addRow("创意工坊目录", mod_row)

        dlc_row, self.dlc_load_path_input = self._create_path_row(
            "选择 dlc_load.json",
            is_file=True,
            file_filter="JSON Files (*.json);;All Files (*)",
        )
        form.addRow("dlc_load.json（可选）", dlc_row)

        local_mod_row, self.local_mod_folder_path_input = self._create_path_row(
            "选择本地 MOD 目录",
            is_file=False,
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
    ) -> tuple[QWidget, QLineEdit]:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        line_edit = QLineEdit(container)
        browse_button = QPushButton("浏览...", container)
        layout.addWidget(line_edit)
        layout.addWidget(browse_button)

        if is_file:
            browse_button.clicked.connect(
                lambda: self._browse_file(line_edit, dialog_title, file_filter)
            )
        else:
            browse_button.clicked.connect(lambda: self._browse_folder(line_edit, dialog_title))

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
            config.get("localization", "priority_mods", fallback="").strip()
        )

        self.max_children_spin.setValue(self._get_int(config, "display", "max_children_per_node", 0))
        self.max_depth_spin.setValue(self._get_int(config, "display", "max_tree_depth", 0))
        self.max_nodes_spin.setValue(self._get_int(config, "display", "max_display_nodes", 0))

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
