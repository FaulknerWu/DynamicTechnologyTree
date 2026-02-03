from __future__ import annotations

import configparser
import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from threading import Event

from PyQt6.QtCore import QThread, pyqtSignal

from gui.i18n import LOCALIZATION_STRINGS, default_language_from_system, t


class SignalWriter(io.StringIO):
    def __init__(self, signal, on_message=None) -> None:
        super().__init__()
        self.signal = signal
        self.on_message = on_message

    def write(self, text: str) -> int:
        if text.strip():
            message = text.rstrip()
            self.signal.emit(message)
            if self.on_message:
                self.on_message(message)
        return len(text)


class GenerationWorker(QThread):
    """Background thread for running tech tree generation."""

    log_message = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, config_path: str, parent=None) -> None:
        super().__init__(parent)
        self.config_path = config_path
        self._cancelled = Event()
        self._progress_markers: dict[str, int] = {}
        self._progress_value = 0
        self._saw_generation_done = False

    def run(self) -> None:
        lang = self._ui_language()
        if self._cancelled.is_set():
            self.finished.emit(False, t("ui_worker_generation_cancelled", lang))
            return

        try:
            from generator import TechTreeGenerator

            stdout_writer = SignalWriter(self.log_message, self._handle_log_message)
            stderr_writer = SignalWriter(self.log_message, self._handle_log_message)
            with redirect_stdout(stdout_writer), redirect_stderr(stderr_writer):
                generator = TechTreeGenerator(self.config_path)
                self._progress_markers = {
                    generator._l("msg_start_generation"): 10,
                    generator._l("msg_counting_tree"): 50,
                    generator._l("msg_generation_done"): 100,
                }
                self._progress_value = 0
                self._saw_generation_done = False
                generator.run_generation_process()

            if self._saw_generation_done:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, t("ui_worker_generation_incomplete", lang))
        except Exception as exc:  # pragma: no cover - GUI error handling
            # Preserve traceback for debugging when the failure happens before stdout/stderr redirection.
            self.log_message.emit(traceback.format_exc().rstrip())
            self.finished.emit(False, str(exc))

    def _ui_language(self) -> str:
        """Return a best-effort GUI language key derived from config.ini.

        Prefer the user's configured Stellaris language when valid; otherwise fall
        back to a system-derived UI language.
        """

        fallback = default_language_from_system()
        try:
            parser = configparser.ConfigParser()
            read_files = parser.read(self.config_path, encoding="utf-8-sig")
            if not read_files:
                return fallback

            candidate = (
                parser.get("localization", "language", fallback="").strip().lower()
            )
            if not candidate:
                return fallback
            if candidate not in LOCALIZATION_STRINGS:
                return fallback
            return candidate
        except Exception:
            return fallback

    def cancel(self) -> None:
        self._cancelled.set()

    def _handle_log_message(self, message: str) -> None:
        for marker, value in self._progress_markers.items():
            if marker and marker in message:
                if value > self._progress_value:
                    self._progress_value = value
                    self.progress.emit(value)
                if value == 100:
                    self._saw_generation_done = True
                break
