from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from dtt_core.error_localization import localization_key_for_error_code
from dtt_core.events import EventKind, EventSink, GenerationEvent
from dtt_core.prepared_run import AmbiguousPlayerEmpireError
from dtt_core.run_outcome import RunOutcome, RunOutcomeCode
from dtt_core.sav_reader import SaveReaderError
from dtt_core.save_context import SaveContext
from gui.i18n import t
from localization import require_supported_language_code
from settings import Settings


class GenerationOutcomeCode(str, Enum):
    SUCCESS = "success"
    CANCELLED = "cancelled"
    AMBIGUOUS_COUNTRY_SELECTION = "ambiguous_country_selection"
    UNSUPPORTED_SAVE_FORMAT = "unsupported_save_format"
    INCOMPLETE = "incomplete"
    ERROR = "error"


@dataclass(frozen=True)
class GenerationOutcome:
    code: GenerationOutcomeCode
    message: str = ""
    empire_options: tuple[dict[str, Any], ...] = ()

    @property
    def success(self) -> bool:
        return self.code == GenerationOutcomeCode.SUCCESS


class _QtEventSink(EventSink):
    def __init__(self, emit_event: Callable[[GenerationEvent], None]) -> None:
        self._emit_event = emit_event

    def emit(self, event: GenerationEvent) -> None:
        self._emit_event(event)


class GenerationWorker(QThread):
    log_message = pyqtSignal(str)
    progress = pyqtSignal(int)
    generation_event = pyqtSignal(object)
    finished = pyqtSignal(object)

    def __init__(
        self,
        settings: Settings,
        application_root: Path | str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._settings_snapshot = settings.model_copy(deep=True)
        self._application_root = (
            Path(application_root) if application_root is not None else None
        )
        self.save_path: str | None = None
        self.country_id: int | None = None
        self._cancelled = Event()
        self._progress_value = 0

    def run(self) -> None:
        try:
            lang = self._ui_language()
            if self._cancelled.is_set():
                self._emit_finished(
                    GenerationOutcomeCode.CANCELLED,
                    t("ui_worker_generation_cancelled", lang),
                )
                return

            save_path = (self.save_path or "").strip()
            if not save_path:
                self._emit_finished(
                    GenerationOutcomeCode.ERROR,
                    "save_path is required and cannot be empty",
                )
                return

            try:
                core_outcome = self._run_generator(
                    save_path=save_path,
                    country_id=self.country_id,
                )
            except AmbiguousPlayerEmpireError as exc:
                self._emit_finished(
                    GenerationOutcomeCode.AMBIGUOUS_COUNTRY_SELECTION,
                    empire_options=tuple(
                        self._build_ambiguous_empire_options(exc.save_context)
                    ),
                )
                return

            if core_outcome.code == RunOutcomeCode.SUCCESS:
                self._emit_finished(GenerationOutcomeCode.SUCCESS)
                return

            if core_outcome.code == RunOutcomeCode.CANCELLED:
                self._emit_finished(
                    GenerationOutcomeCode.CANCELLED,
                    t("ui_worker_generation_cancelled", lang),
                )
                return

            if core_outcome.code == RunOutcomeCode.ERROR:
                self._emit_finished(
                    GenerationOutcomeCode.ERROR,
                    self._localize_core_error(core_outcome, lang),
                )
                return

            if core_outcome.code == RunOutcomeCode.INCOMPLETE:
                self._emit_finished(
                    GenerationOutcomeCode.INCOMPLETE,
                    self._format_incomplete_message(core_outcome, lang),
                )
                return

            self._emit_finished(
                GenerationOutcomeCode.ERROR,
                f"内部错误：未知的运行结果 {core_outcome.code!r}",
            )
        except SaveReaderError as exc:
            self._emit_finished(GenerationOutcomeCode.UNSUPPORTED_SAVE_FORMAT, str(exc))
        except Exception as exc:  # pragma: no cover - GUI error handling
            self.log_message.emit(traceback.format_exc().rstrip())
            self._emit_finished(GenerationOutcomeCode.ERROR, str(exc))

    @staticmethod
    def _unknown_error_code_message(code: str) -> str:
        return f"Unknown error code: {code}"

    def _build_ambiguous_empire_options(
        self, save_context: SaveContext
    ) -> list[dict[str, Any]]:
        options: list[dict[str, Any]] = []
        for country_id in sorted(save_context.player_country_candidates):
            facts = save_context.empires_by_country_id.get(country_id)
            name = facts.country_name.strip() if facts else ""
            label = f"{country_id} - {name}" if name else str(country_id)
            options.append({"country_id": country_id, "label": label})
        return options

    def _run_generator(self, *, save_path: str, country_id: int | None) -> RunOutcome:
        from generator import TechTreeGenerator

        if self._application_root is None:
            generator = TechTreeGenerator(settings=self._settings_snapshot)
        else:
            generator = TechTreeGenerator(
                settings=self._settings_snapshot,
                application_root=self._application_root,
            )
        self._progress_value = 0
        return generator.run_generation_process(
            save_path=save_path,
            country_id=country_id,
            event_sink=_QtEventSink(self._handle_generation_event),
            cancel_event=self._cancelled,
        )

    def _ui_language(self) -> str:
        try:
            return require_supported_language_code(
                self._settings_snapshot.localization.target_language_code,
                field_name="settings.localization.target_language_code",
            )
        except ValueError:
            return "english"

    def cancel(self) -> None:
        self._cancelled.set()

    def _handle_generation_event(self, event: GenerationEvent) -> None:
        self.generation_event.emit(event)

        if event.kind == EventKind.PROGRESS and event.progress is not None:
            if event.progress > self._progress_value:
                self._progress_value = event.progress
                self.progress.emit(event.progress)

        if event.message and event.kind in {
            EventKind.LOG,
            EventKind.WARNING,
            EventKind.ERROR,
            EventKind.PROGRESS,
        }:
            self.log_message.emit(event.message)

    @staticmethod
    def _format_incomplete_message(outcome: RunOutcome, lang: str) -> str:
        message = t("ui_worker_generation_incomplete", lang)
        failures = []
        for failure in outcome.artifact_summary.failed:
            failures.append(str(failure.path))
        if failures:
            message = f"{message}\n" + "\n".join(failures)
        return message

    @staticmethod
    def _error_details_dict(outcome: RunOutcome) -> dict[str, str]:
        details: dict[str, str] = {}
        for key, value in outcome.error_details:
            details[key] = value
        return details

    def _localize_core_error(self, outcome: RunOutcome, lang: str) -> str:
        key = localization_key_for_error_code(outcome.error_code)
        if key:
            # t() 在 key 不存在时返回 key 本身；检测到有效翻译时使用之
            translated = t(key, lang, **self._error_details_dict(outcome))
            if translated != key:
                return translated

        message = str(outcome.message).strip()
        if message:
            return message

        if outcome.error_code:
            return self._unknown_error_code_message(outcome.error_code)

        return "unknown error"

    def _emit_finished(
        self,
        code: GenerationOutcomeCode,
        message: str = "",
        *,
        empire_options: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.finished.emit(
            GenerationOutcome(
                code=code,
                message=message,
                empire_options=empire_options,
            )
        )
