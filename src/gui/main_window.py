from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEvent, QSignalBlocker, Qt
from PyQt6.QtGui import QCloseEvent, QFontDatabase
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui import _default_settings_path
from gui.generation_worker import (
    GenerationOutcome,
    GenerationOutcomeCode,
    GenerationWorker,
)
from gui.i18n import t
from gui.path_detector import PathDetector
from gui.settings_panel import SettingsPanel
from gui.title_bar import CustomTitleBar
from settings import Settings, require_supported_language, settings_json_schema
from settings_store import SettingsStoreError, load_settings, save_settings


class MainWindow(QMainWindow):
    def __init__(
        self,
        config_path: str | os.PathLike[str] | None = None,
        application_path: str | os.PathLike[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumSize(700, 500)

        self.settings_path = (
            Path(config_path) if config_path else _default_settings_path()
        )
        self.application_path = Path(application_path) if application_path else None
        self.config_path = self.settings_path
        self.settings = Settings()
        self.setWindowTitle(t("ui_app_title", self._current_lang()))

        self.worker: GenerationWorker | None = None
        self._selected_save_path = ""
        self._pending_empire_options: list[dict[str, Any]] = []

        self._settings_file_error = ""
        self._generation_blocking_error = ""

        self._build_ui()
        self.load_config()
        self.retranslate_ui()
        self._check_and_auto_detect()
        self._refresh_validation_state()

    def _current_lang(self) -> str:
        try:
            return require_supported_language(self.settings.localization.language)
        except ValueError:
            return "english"

    def _t(self, key: str, **kwargs: object) -> str:
        return t(key, self._current_lang(), **kwargs)

    def _t_or_default(self, key: str, fallback: str) -> str:
        translated = self._t(key)
        if translated and translated != key:
            return translated
        return fallback

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

        content_widget = QWidget(central_widget)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(8)

        profiles_row = QHBoxLayout()
        self.settings_profile_label = QLabel(content_widget)
        profiles_row.addWidget(self.settings_profile_label)

        self.settings_profile_combo = QComboBox(content_widget)
        self.settings_profile_combo.setObjectName("settingsProfileCombo")
        self.settings_profile_combo.currentTextChanged.connect(
            self._on_profile_combo_changed
        )
        profiles_row.addWidget(self.settings_profile_combo, 1)

        self.open_profile_button = QPushButton(content_widget)
        self.open_profile_button.setObjectName("openSettingsProfileButton")
        self.open_profile_button.clicked.connect(self.on_open_profile_clicked)
        profiles_row.addWidget(self.open_profile_button)

        self.save_as_profile_button = QPushButton(content_widget)
        self.save_as_profile_button.setObjectName("saveAsSettingsProfileButton")
        self.save_as_profile_button.clicked.connect(self.on_save_as_profile_clicked)
        profiles_row.addWidget(self.save_as_profile_button)

        content_layout.addLayout(profiles_row)

        self.settings_panel = SettingsPanel(
            settings_json_schema(),
            self.settings,
            parent=content_widget,
            translate=lambda key: self._t(key),
        )
        self.settings_panel.validation_changed.connect(
            self._on_settings_panel_validation_changed
        )
        self.settings_panel.raw_apply_finished.connect(self._on_raw_apply_finished)
        content_layout.addWidget(self.settings_panel)

        self.settings_error_label = QLabel(content_widget)
        self.settings_error_label.setWordWrap(True)
        self.settings_error_label.setStyleSheet("color: #c62828;")
        self.settings_error_label.setVisible(False)
        content_layout.addWidget(self.settings_error_label)

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

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self._t("ui_app_title"))

        if self.worker and self.worker.isRunning():
            self.generate_button.setText(self._t("ui_btn_generating"))
        else:
            self.generate_button.setText(self._t("ui_btn_generate"))

        self.save_button.setText(self._t("ui_btn_save_config"))
        self.settings_profile_label.setText(
            self._t_or_default("ui_label_settings_profile", "Settings Profile:")
        )
        self.open_profile_button.setText(
            self._t_or_default("ui_btn_open_profile", "Open Profile...")
        )
        self.save_as_profile_button.setText(
            self._t_or_default("ui_btn_save_profile_as", "Save Profile As...")
        )
        self.settings_panel.retranslate(lambda key: self._t(key))

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
        self._register_profile_path(self.settings_path)

        if self._is_ini_settings_path(self.settings_path):
            self._settings_file_error = self._format_ini_not_supported_error(
                self.settings_path
            )
            self.append_log(self._settings_file_error)
            self.settings_panel.refresh_from_settings()
            self._refresh_validation_state()
            return

        if not self.settings_path.exists():
            self._settings_file_error = ""
            self.append_log(
                self._t("ui_log_config_not_found", path=str(self.settings_path))
            )
            self.settings_panel.refresh_from_settings()
            self._refresh_validation_state()
            return

        try:
            loaded_settings = load_settings(self.settings_path)
        except SettingsStoreError as exc:
            self._settings_file_error = self._format_settings_store_error(
                self.settings_path, exc
            )
            self.append_log(self._settings_file_error)
            self._refresh_validation_state()
            return

        self._load_settings_into_ssot(loaded_settings)
        self._settings_file_error = ""
        self.settings_panel.refresh_from_settings()
        self.append_log(self._t("ui_log_loaded_config", path=str(self.settings_path)))
        self._refresh_validation_state()

    def switch_settings_profile(
        self, settings_path: str | os.PathLike[str]
    ) -> bool:
        target_path = Path(settings_path)
        previous_path = self.settings_path

        if target_path == previous_path:
            return True

        if self._is_ini_settings_path(target_path):
            error_message = self._format_ini_not_supported_error(target_path)
            self._settings_file_error = error_message
            self.settings_path = previous_path
            self.config_path = previous_path
            self._set_current_profile_path(previous_path)
            self._refresh_validation_state()
            QMessageBox.warning(
                self,
                self._t("ui_msgbox_title_config_error"),
                error_message,
            )
            return False

        if target_path.exists():
            try:
                loaded_settings = load_settings(target_path)
            except SettingsStoreError as exc:
                error_message = self._format_settings_store_error(target_path, exc)
                self._settings_file_error = error_message
                self.settings_path = previous_path
                self.config_path = previous_path
                self._set_current_profile_path(previous_path)
                self._refresh_validation_state()
                QMessageBox.warning(
                    self,
                    self._t("ui_msgbox_title_config_error"),
                    error_message,
                )
                return False

            self._load_settings_into_ssot(loaded_settings)
            self._settings_file_error = ""
            self.append_log(self._t("ui_log_loaded_config", path=str(target_path)))
        else:
            self._settings_file_error = ""
            self.append_log(self._t("ui_log_config_not_found", path=str(target_path)))

        self.settings_path = target_path
        self.config_path = target_path
        self._register_profile_path(target_path)
        self._set_current_profile_path(target_path)
        self.settings_panel.refresh_from_settings()
        self.retranslate_ui()
        self._refresh_validation_state()
        return True

    def _load_settings_into_ssot(self, incoming: Settings) -> None:
        incoming_snapshot = incoming.model_copy(deep=True)
        for field_name in Settings.model_fields:
            setattr(self.settings, field_name, getattr(incoming_snapshot, field_name))

    def _format_settings_store_error(
        self,
        path: Path,
        exc: SettingsStoreError,
    ) -> str:
        details = exc.message
        if exc.path:
            dotted_path = ".".join(str(part) for part in exc.path)
            details = f"{details} ({dotted_path})"
        if exc.line is not None and exc.column is not None:
            details = f"{details} at line {exc.line}, column {exc.column}"

        return self._build_actionable_settings_error(f"{details} [{path}]")

    def _check_and_auto_detect(self) -> None:
        base_path = self.settings.paths.base_game_path.strip()
        mod_path = self.settings.paths.mod_folder_path.strip()

        if not base_path or not mod_path:
            self.append_log(self._t("ui_log_autodetect_start"))
            self.status_bar.showMessage(self._t("ui_status_autodetecting"))

            detected = PathDetector(self.settings).detect_all()
            detected_count = 0
            detected_count += self._set_path_if_empty(
                "base_game_path", detected.game_path
            )
            detected_count += self._set_path_if_empty(
                "mod_folder_path", detected.workshop_path
            )
            detected_count += self._set_path_if_empty(
                "launcher_db_path", detected.launcher_db_path
            )
            detected_count += self._set_path_if_empty(
                "local_mod_folder_path", detected.local_mod_path
            )

            if detected_count:
                self.settings_panel.refresh_from_settings()

            self.append_log(self._t("ui_log_autodetect_done", count=detected_count))

        self._update_detection_status()

    def _set_path_if_empty(self, field_name: str, detected_value: str | None) -> int:
        current_value = getattr(self.settings.paths, field_name, "")
        if current_value.strip() or not detected_value:
            return 0

        setattr(self.settings.paths, field_name, detected_value)
        return 1

    def _update_detection_status(self) -> None:
        base_path = self.settings.paths.base_game_path.strip()
        mod_path = self.settings.paths.mod_folder_path.strip()

        if base_path and mod_path:
            self.status_bar.showMessage(self._t("ui_status_paths_ok"))
        elif mod_path:
            self.status_bar.showMessage(self._t("ui_status_steam_ok"))
        elif base_path:
            self.status_bar.showMessage(self._t("ui_status_game_ok"))
        else:
            self.status_bar.showMessage(self._t("ui_status_need_manual_paths"))

    def _required_path_validation_error(self) -> str:
        missing_fields: list[str] = []
        if not self.settings.paths.base_game_path.strip():
            missing_fields.append(self._t("ui_field_base_game_path"))
        if not self.settings.paths.mod_folder_path.strip():
            missing_fields.append(self._t("ui_field_workshop_path"))
        if not self.settings.paths.launcher_db_path.strip():
            missing_fields.append(self._t("ui_field_launcher_db_path"))

        if missing_fields:
            return self._t(
                "ui_error_missing_required_paths",
                fields=", ".join(missing_fields),
            )
        return ""

    def _build_actionable_settings_error(self, detail: str) -> str:
        hint = self._t_or_default(
            "ui_hint_fix_settings",
            "Fix the highlighted fields or choose a valid JSON settings profile.",
        )
        cleaned_detail = detail.strip()
        if not cleaned_detail:
            return hint
        return f"{cleaned_detail} {hint}"

    def _is_ini_settings_path(self, path: Path) -> bool:
        return path.suffix.lower() == ".ini"

    def _format_ini_not_supported_error(self, path: Path) -> str:
        return self._build_actionable_settings_error(
            f"INI settings profiles are no longer supported [{path}]. "
            "Use a JSON settings profile (*.json), for example settings.json."
        )

    def _compute_generation_blocking_error(self) -> str:
        if self._settings_file_error:
            return self._settings_file_error

        if not self.settings_panel.is_valid:
            return self._build_actionable_settings_error(
                self.settings_panel.validation_error
            )

        required_paths_error = self._required_path_validation_error()
        if required_paths_error:
            return self._build_actionable_settings_error(required_paths_error)

        return ""

    def _refresh_validation_state(self) -> None:
        self._generation_blocking_error = self._compute_generation_blocking_error()
        self.settings_error_label.setVisible(bool(self._generation_blocking_error))
        if self._generation_blocking_error:
            self.settings_error_label.setText(self._generation_blocking_error)
        else:
            self.settings_error_label.clear()

        if self.worker and self.worker.isRunning():
            return

        self.generate_button.setEnabled(not self._generation_blocking_error)
        self.save_button.setEnabled(self.settings_panel.is_valid)

    def _on_settings_panel_validation_changed(
        self,
        _is_valid: bool,
        _error_message: str,
    ) -> None:
        self.retranslate_ui()
        self._refresh_validation_state()

    def _on_raw_apply_finished(self, success: bool, error_message: str) -> None:
        if success:
            self._refresh_validation_state()
            return

        QMessageBox.warning(
            self,
            self._t("ui_msgbox_title_config_error"),
            self._build_actionable_settings_error(error_message),
        )

    def save_config(self) -> bool:
        if not self.settings_path:
            self.append_log(self._t("ui_log_no_config_path"))
            return False

        if not self.settings_panel.is_valid:
            QMessageBox.warning(
                self,
                self._t("ui_msgbox_title_config_error"),
                self._build_actionable_settings_error(
                    self.settings_panel.validation_error
                ),
            )
            return False

        try:
            save_settings(self.settings_path, self.settings)
        except SettingsStoreError as exc:
            error_message = self._format_settings_store_error(self.settings_path, exc)
            self.append_log(error_message)
            QMessageBox.critical(
                self,
                self._t("ui_msgbox_title_save_failed"),
                error_message,
            )
            return False

        self._settings_file_error = ""
        self._register_profile_path(self.settings_path)
        self._set_current_profile_path(self.settings_path)
        self.append_log(self._t("ui_log_config_saved", path=str(self.settings_path)))
        self._refresh_validation_state()
        return True

    def on_save_clicked(self) -> None:
        self.save_config()

    def _on_profile_combo_changed(self, selected_path: str) -> None:
        path_text = selected_path.strip()
        if not path_text:
            return

        candidate = Path(path_text)
        if candidate == self.settings_path:
            return

        self.switch_settings_profile(candidate)

    def on_open_profile_clicked(self) -> None:
        selected_path = self._choose_settings_profile_file()
        if not selected_path:
            return

        self.switch_settings_profile(selected_path)

    def on_save_as_profile_clicked(self) -> None:
        selected_path = self._choose_settings_profile_save_path()
        if not selected_path:
            return

        previous_path = self.settings_path
        self.settings_path = selected_path
        self.config_path = selected_path
        self._register_profile_path(selected_path)
        self._set_current_profile_path(selected_path)

        if self.save_config():
            return

        self.settings_path = previous_path
        self.config_path = previous_path
        self._set_current_profile_path(previous_path)
        self._refresh_validation_state()

    def _register_profile_path(self, path: Path) -> None:
        profile_text = str(path)
        if self.settings_profile_combo.findText(profile_text) != -1:
            return
        self.settings_profile_combo.addItem(profile_text)

    def _set_current_profile_path(self, path: Path) -> None:
        profile_text = str(path)
        if self.settings_profile_combo.findText(profile_text) == -1:
            self.settings_profile_combo.addItem(profile_text)

        blocker = QSignalBlocker(self.settings_profile_combo)
        try:
            self.settings_profile_combo.setCurrentText(profile_text)
        finally:
            del blocker

    def _choose_settings_profile_file(self) -> Path | None:
        start_dir = str(self.settings_path.parent)
        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            self._t_or_default(
                "ui_dialog_title_choose_settings_file", "Select settings profile"
            ),
            start_dir,
            self._t("ui_file_filter_json"),
        )
        selected_text = selected_path.strip()
        if not selected_text:
            return None
        return Path(selected_text)

    def _choose_settings_profile_save_path(self) -> Path | None:
        start_path = str(self.settings_path)
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            self._t_or_default(
                "ui_dialog_title_save_settings_file", "Save settings profile"
            ),
            start_path,
            self._t("ui_file_filter_json"),
        )
        selected_text = selected_path.strip()
        if not selected_text:
            return None

        profile_path = Path(selected_text)
        if profile_path.suffix.lower() != ".json":
            profile_path = profile_path.with_suffix(".json")
        return profile_path

    def _choose_save_file(self) -> str:
        save_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            self._t("ui_dialog_title_choose_save_file"),
            "",
            self._t("ui_file_filter_save"),
        )
        return save_path.strip()

    def _set_generation_controls(self, generating: bool) -> None:
        self.settings_panel.setEnabled(not generating)
        self.settings_profile_combo.setEnabled(not generating)
        self.open_profile_button.setEnabled(not generating)
        self.save_as_profile_button.setEnabled(not generating)

        if generating:
            self.generate_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.generate_button.setText(self._t("ui_btn_generating"))
            return

        self.retranslate_ui()
        self._refresh_validation_state()

    def _start_generation_worker(self, save_path: str, country_id: int | None) -> None:
        self._selected_save_path = save_path
        self._pending_empire_options = []
        self._set_generation_controls(True)
        self.log_output.clear()
        self.progress_bar.setValue(0)

        if self.application_path is None:
            self.worker = GenerationWorker(self.settings.model_copy(deep=True))
        else:
            self.worker = GenerationWorker(
                self.settings.model_copy(deep=True),
                application_root=self.application_path,
            )
        self.worker.save_path = save_path
        self.worker.country_id = country_id
        self.worker.log_message.connect(self.on_log_message)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_generation_finished)
        self.worker.start()

    def _choose_ambiguous_empire(self) -> int | None:
        labels: list[str] = []
        label_to_country: dict[str, int] = {}
        for option in self._pending_empire_options:
            country_id = option.get("country_id")
            label = str(option.get("label", "")).strip()
            if not isinstance(country_id, int):
                continue
            if not label:
                label = str(country_id)
            labels.append(label)
            label_to_country[label] = country_id

        if not labels:
            return None

        selected_label, accepted = QInputDialog.getItem(
            self,
            self._t("ui_dialog_title_choose_empire"),
            self._t("ui_dialog_body_choose_empire"),
            labels,
            0,
            False,
        )
        if not accepted:
            return None
        return label_to_country.get(selected_label)

    def on_generate_clicked(self) -> None:
        if self._generation_blocking_error:
            QMessageBox.warning(
                self,
                self._t("ui_msgbox_title_config_error"),
                self._generation_blocking_error,
            )
            return

        if not self.save_config():
            return

        save_path = self._choose_save_file()
        if not save_path:
            return

        self._start_generation_worker(save_path, country_id=None)

    def on_log_message(self, message: str) -> None:
        self.log_output.append(message)

    def on_generation_finished(self, outcome: object, legacy_message: str = "") -> None:
        resolved_outcome = self._coerce_generation_outcome(outcome, legacy_message)

        self._set_generation_controls(False)
        if self.worker:
            self.worker.wait()
            self.worker.deleteLater()
            self.worker = None

        if resolved_outcome.code == GenerationOutcomeCode.AMBIGUOUS_COUNTRY_SELECTION:
            self._pending_empire_options = [
                option
                for option in resolved_outcome.empire_options
                if isinstance(option, dict)
            ]
            selected_country_id = self._choose_ambiguous_empire()
            self._pending_empire_options = []
            if selected_country_id is None:
                return
            if not self._selected_save_path:
                return
            self._start_generation_worker(
                self._selected_save_path,
                country_id=selected_country_id,
            )
            return

        if resolved_outcome.success:
            QMessageBox.information(
                self,
                self._t("ui_msgbox_title_done"),
                self._t("ui_msgbox_body_generation_done"),
            )
        elif resolved_outcome.code == GenerationOutcomeCode.CANCELLED:
            QMessageBox.information(
                self,
                self._t("ui_msgbox_title_cancelled"),
                self._t("ui_msgbox_body_generation_cancelled"),
            )
        elif resolved_outcome.code == GenerationOutcomeCode.INCOMPLETE:
            details = resolved_outcome.message.strip()
            if not details:
                details = self._t("ui_worker_generation_incomplete")
            QMessageBox.warning(
                self,
                self._t("ui_msgbox_title_incomplete"),
                self._t("ui_msgbox_body_generation_incomplete", details=details),
            )
        else:
            if resolved_outcome.code == GenerationOutcomeCode.UNSUPPORTED_SAVE_FORMAT:
                unsupported_error = resolved_outcome.message.strip()
                QMessageBox.critical(
                    self,
                    self._t("ui_msgbox_title_unsupported_save_format"),
                    self._t(
                        "ui_msgbox_body_unsupported_save_format",
                        error=unsupported_error,
                    ),
                )
                return

            error_message = resolved_outcome.message.strip()
            if not error_message:
                error_message = self._t("ui_worker_generation_incomplete")
            QMessageBox.critical(
                self,
                self._t("ui_msgbox_title_error"),
                self._t("ui_msgbox_body_generation_failed", error=error_message),
            )

    def _coerce_generation_outcome(
        self, outcome: object, legacy_message: str
    ) -> GenerationOutcome:
        if isinstance(outcome, GenerationOutcome):
            return outcome

        if isinstance(outcome, bool):
            if outcome:
                return GenerationOutcome(code=GenerationOutcomeCode.SUCCESS)
            return GenerationOutcome(
                code=GenerationOutcomeCode.ERROR,
                message=str(legacy_message),
            )

        if isinstance(outcome, str):
            return GenerationOutcome(code=GenerationOutcomeCode.ERROR, message=outcome)

        return GenerationOutcome(code=GenerationOutcomeCode.ERROR, message=str(outcome))

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        if a0 is None:
            return
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(5000)
        a0.accept()
