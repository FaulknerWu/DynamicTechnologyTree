from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path
from typing import Optional, Union

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QCloseEvent, QFontDatabase
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QMessageBox,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui.config_editor import ConfigEditor
from gui.generation_worker import GenerationWorker
from gui.title_bar import CustomTitleBar


class MainWindow(QMainWindow):
    def __init__(
        self,
        config_path: Optional[Union[str, os.PathLike]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle("Stellaris 科技树生成器")
        self.setMinimumSize(700, 500)

        self.config_path = Path(config_path) if config_path else self._default_config_path()
        self.config = configparser.ConfigParser()
        self.worker: Optional[GenerationWorker] = None

        self._build_ui()
        self.load_config()
        self._check_and_auto_detect()

    def _default_config_path(self) -> Path:
        frozen = getattr(sys, "frozen", False)
        application_path = Path(sys.executable).parent if frozen else Path(sys.argv[0]).resolve().parent
        return application_path / "config.ini"

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        central_widget.setStyleSheet("""
            QWidget#centralWidget {
                background-color: white;
                border: 1px solid #ccc;
            }
        """)
        central_widget.setObjectName("centralWidget")
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(central_widget)
        self.title_bar.min_button.clicked.connect(self.showMinimized)
        self.title_bar.max_button.clicked.connect(self._toggle_max_restore)
        self.title_bar.close_button.clicked.connect(self.close)
        self.title_bar.set_maximized(self.isMaximized())
        main_layout.addWidget(self.title_bar)

        # Content area with padding
        content_widget = QWidget(central_widget)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(8)

        self.config_editor = ConfigEditor(content_widget)
        content_layout.addWidget(self.config_editor)

        controls_layout = QHBoxLayout()
        self.generate_button = QPushButton("生成科技树", content_widget)
        self.generate_button.clicked.connect(self.on_generate_clicked)
        controls_layout.addWidget(self.generate_button)

        self.progress_bar = QProgressBar(content_widget)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        controls_layout.addWidget(self.progress_bar)

        content_layout.addLayout(controls_layout)

        self.log_output = QTextEdit(content_widget)
        self.log_output.setReadOnly(True)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.log_output.setFont(fixed_font)
        content_layout.addWidget(self.log_output)

        main_layout.addWidget(content_widget)

        self.setCentralWidget(central_widget)
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

    def _toggle_max_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            if hasattr(self, "title_bar"):
                self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(event)

    def append_log(self, message: str) -> None:
        self.log_output.append(message)

    def load_config(self) -> None:
        self.config = configparser.ConfigParser()
        if self.config_path.exists():
            self.config.read(self.config_path, encoding="utf-8")
            self.append_log(f"已加载配置: {self.config_path}")
        else:
            self.append_log(f"未找到配置文件: {self.config_path}")
        self.config_editor.load_from_config(self.config)

    def _check_and_auto_detect(self) -> None:
        """Auto-detect paths if required fields are empty."""
        base_path = self.config.get("paths", "base_game_path", fallback="").strip()
        mod_path = self.config.get("paths", "mod_folder_path", fallback="").strip()

        if not base_path or not mod_path:
            self.append_log("检测到首次运行或路径未配置，正在自动检测...")
            self.status_bar.showMessage("正在自动检测路径...")
            self.config_editor.auto_detect_all_paths()
            detected_count = sum(
                1
                for field in (
                    self.config_editor.base_game_path_input,
                    self.config_editor.mod_folder_path_input,
                    self.config_editor.dlc_load_path_input,
                    self.config_editor.local_mod_folder_path_input,
                )
                if field.text().strip()
            )
            self.append_log(f"自动检测完成，找到 {detected_count} 个路径")

        self._update_detection_status()

    def _update_detection_status(self) -> None:
        base_path = self.config_editor.base_game_path_input.text().strip()
        mod_path = self.config_editor.mod_folder_path_input.text().strip()

        if base_path and mod_path:
            self.status_bar.showMessage("已检测到必要路径")
        elif mod_path:
            self.status_bar.showMessage("已检测到 Steam 路径")
        elif base_path:
            self.status_bar.showMessage("已检测到本体路径")
        else:
            self.status_bar.showMessage("请手动配置路径")

    def save_config(self) -> bool:
        if not self.config_path:
            self.append_log("未设置配置路径，无法保存。")
            return False
        self.config_editor.save_to_config(self.config)
        try:
            with self.config_path.open("w", encoding="utf-8") as config_file:
                self.config.write(config_file)
        except OSError as exc:
            self.append_log(f"保存配置失败: {exc}")
            QMessageBox.critical(self, "保存失败", f"无法写入配置文件：{exc}")
            return False
        self.append_log(f"已保存配置: {self.config_path}")
        return True

    def on_generate_clicked(self) -> None:
        valid, error_message = self.config_editor.validate()
        if not valid:
            QMessageBox.warning(self, "配置错误", error_message)
            return

        if not self.save_config():
            return
        self.generate_button.setEnabled(False)
        self.generate_button.setText("生成中...")
        self.log_output.clear()
        self.progress_bar.setValue(0)

        self.worker = GenerationWorker(str(self.config_path))
        self.worker.log_message.connect(self.on_log_message)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_generation_finished)
        self.worker.start()

    def on_log_message(self, message: str) -> None:
        self.log_output.append(message)

    def on_generation_finished(self, success: bool, message: str) -> None:
        self.generate_button.setEnabled(True)
        self.generate_button.setText("生成科技树")
        self.progress_bar.setValue(100 if success else 0)
        if self.worker:
            self.worker.wait()
            self.worker.deleteLater()
            self.worker = None

        if success:
            QMessageBox.information(self, "完成", "科技树生成完成！")
        else:
            QMessageBox.critical(self, "错误", f"生成失败：{message}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(5000)
        event.accept()
