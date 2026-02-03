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
from gui.i18n import t
from gui.title_bar import CustomTitleBar

# Note: keep imports flat to match the project's packaging/runtime model.


class MainWindow(QMainWindow):
    def __init__(
        self,
        config_path: Optional[Union[str, os.PathLike]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        # Title is retranslated after config/language is loaded.
        self.setWindowTitle(t("ui_app_title", "english"))
        self.setMinimumSize(700, 500)

        self.config_path = (
            Path(config_path) if config_path else self._default_config_path()
        )
        self.config = configparser.ConfigParser()
        self.worker: Optional[GenerationWorker] = None

        self._build_ui()
        self.load_config()
        self.retranslate_ui()
        self._check_and_auto_detect()

    def _current_lang(self) -> str:
        # Task constraint: read language from the combo's currentText.
        if hasattr(self, "config_editor"):
            lang = self.config_editor.language_combo.currentText().strip().lower()
            return lang or "english"
        return "english"

    def _t(self, key: str, **kwargs: object) -> str:
        return t(key, self._current_lang(), **kwargs)

    def _default_config_path(self) -> Path:
        frozen = getattr(sys, "frozen", False)
        application_path = (
            Path(sys.executable).parent
            if frozen
            else Path(sys.argv[0]).resolve().parent
        )
        return application_path / "config.ini"

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        central_widget.setStyleSheet("""
            QWidget#centralWidget {
                background-color: palette(window);
                border: 1px solid palette(mid);
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
        self.config_editor.language_combo.currentTextChanged.connect(
            self._on_language_changed
        )
        content_layout.addWidget(self.config_editor)

        controls_layout = QHBoxLayout()
        self.generate_button = QPushButton(self._t("ui_btn_generate"), content_widget)
        self.generate_button.clicked.connect(self.on_generate_clicked)
        controls_layout.addWidget(self.generate_button)

        self.save_button = QPushButton(self._t("ui_btn_save_config"), content_widget)
        self.save_button.clicked.connect(self.on_save_clicked)
        controls_layout.addWidget(self.save_button)

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

    def _on_language_changed(self, _lang_text: str) -> None:
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        # Minimum runtime retranslation requirements for this task.
        self.setWindowTitle(self._t("ui_app_title"))

        if self.worker and self.worker.isRunning():
            self.generate_button.setText(self._t("ui_btn_generating"))
        else:
            self.generate_button.setText(self._t("ui_btn_generate"))

        if hasattr(self, "save_button"):
            self.save_button.setText(self._t("ui_btn_save_config"))

        # Status bar string is based on current detection state.
        self._update_detection_status()

    def _toggle_max_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, a0: QEvent | None) -> None:
        if a0 is not None and a0.type() == QEvent.Type.WindowStateChange:
            if hasattr(self, "title_bar"):
                self.title_bar.set_maximized(self.isMaximized())
        super().changeEvent(a0)

    def append_log(self, message: str) -> None:
        self.log_output.append(message)

    def load_config(self) -> None:
        self.config = configparser.ConfigParser()
        if self.config_path.exists():
            self.config.read(self.config_path, encoding="utf-8")
        self.config_editor.load_from_config(self.config)

        if self.config_path.exists():
            self.append_log(self._t("ui_log_loaded_config", path=str(self.config_path)))
        else:
            self.append_log(
                self._t("ui_log_config_not_found", path=str(self.config_path))
            )

    def _check_and_auto_detect(self) -> None:
        """Auto-detect paths if required fields are empty."""
        base_path = self.config.get("paths", "base_game_path", fallback="").strip()
        mod_path = self.config.get("paths", "mod_folder_path", fallback="").strip()

        if not base_path or not mod_path:
            self.append_log(self._t("ui_log_autodetect_start"))
            self.status_bar.showMessage(self._t("ui_status_autodetecting"))
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
            self.append_log(self._t("ui_log_autodetect_done", count=detected_count))

        self._update_detection_status()

    def _update_detection_status(self) -> None:
        base_path = self.config_editor.base_game_path_input.text().strip()
        mod_path = self.config_editor.mod_folder_path_input.text().strip()

        if base_path and mod_path:
            self.status_bar.showMessage(self._t("ui_status_paths_ok"))
        elif mod_path:
            self.status_bar.showMessage(self._t("ui_status_steam_ok"))
        elif base_path:
            self.status_bar.showMessage(self._t("ui_status_game_ok"))
        else:
            self.status_bar.showMessage(self._t("ui_status_need_manual_paths"))

    def save_config(self) -> bool:
        if not self.config_path:
            self.append_log(self._t("ui_log_no_config_path"))
            return False
        self.config_editor.save_to_config(self.config)
        try:
            with self.config_path.open("w", encoding="utf-8") as config_file:
                self.config.write(config_file)
        except OSError as exc:
            self.append_log(self._t("ui_log_save_failed", error=str(exc)))
            QMessageBox.critical(
                self,
                self._t("ui_msgbox_title_save_failed"),
                self._t("ui_msgbox_body_save_failed", error=str(exc)),
            )
            return False
        self.append_log(self._t("ui_log_config_saved", path=str(self.config_path)))
        return True

    def on_save_clicked(self) -> None:
        valid, error_message = self.config_editor.validate()
        if not valid:
            QMessageBox.warning(
                self, self._t("ui_msgbox_title_config_error"), error_message
            )
            return
        self.save_config()

    def on_generate_clicked(self) -> None:
        valid, error_message = self.config_editor.validate()
        if not valid:
            QMessageBox.warning(
                self, self._t("ui_msgbox_title_config_error"), error_message
            )
            return

        if not self.save_config():
            return
        self.generate_button.setEnabled(False)
        self.generate_button.setText(self._t("ui_btn_generating"))
        self.save_button.setEnabled(False)
        self.config_editor.language_combo.setEnabled(False)
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
        self.generate_button.setText(self._t("ui_btn_generate"))
        self.save_button.setEnabled(True)
        self.config_editor.language_combo.setEnabled(True)
        self.progress_bar.setValue(100 if success else 0)
        if self.worker:
            self.worker.wait()
            self.worker.deleteLater()
            self.worker = None

        if success:
            QMessageBox.information(
                self,
                self._t("ui_msgbox_title_done"),
                self._t("ui_msgbox_body_generation_done"),
            )
        else:
            QMessageBox.critical(
                self,
                self._t("ui_msgbox_title_error"),
                self._t("ui_msgbox_body_generation_failed", error=message),
            )

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        if a0 is None:
            return
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(5000)
        a0.accept()
