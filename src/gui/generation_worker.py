from __future__ import annotations

import traceback
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Event
from typing import Any
from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from dtt_core.events import EventKind, EventSink, GenerationEvent, StageId
from dtt_core.load_order_resolver import LoadOrderResolutionError
from dtt_core.prepared_run import AmbiguousPlayerEmpireError
from dtt_core.sav_reader import SaveReaderError
from dtt_core.save_context import SaveContext
from dtt_core.settings_snapshot import require_settings_snapshot
from dtt_core.typed_error import TypedCoreError
from gui.i18n import t
from localization import LOCALIZATION_STRINGS
from settings import Settings, require_supported_language


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


_LOAD_ORDER_ERROR_KEYS: dict[str, str] = {
    "missing_database_path": "ui_error_launcher_db_missing_database_path",
    "empty_database_path": "ui_error_launcher_db_empty_database_path",
    "missing_database": "ui_error_launcher_db_missing_database",
    "database_not_file": "ui_error_launcher_db_not_a_file",
    "database_locked": "ui_error_launcher_db_locked",
    "open_failed": "ui_error_launcher_db_open_failed",
    "read_failed": "ui_error_launcher_db_read_failed",
    "corrupt_database": "ui_error_launcher_db_corrupt",
    "database_error": "ui_error_launcher_db_query_failed",
    "schema_playsets_missing": "ui_error_launcher_db_schema_missing_table",
    "schema_playsets_mods_missing": "ui_error_launcher_db_schema_missing_table",
    "schema_mods_missing": "ui_error_launcher_db_schema_missing_table",
    "schema_playsets_columns": "ui_error_launcher_db_schema_missing_columns",
    "schema_playsets_mods_columns": "ui_error_launcher_db_schema_missing_columns",
    "schema_mods_columns": "ui_error_launcher_db_schema_missing_columns",
    "no_active_playset": "ui_error_launcher_db_no_active_playset",
}


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
        self._settings_snapshot = require_settings_snapshot(settings)
        self._application_root = (
            Path(application_root) if application_root is not None else None
        )
        self.save_path: str | None = None
        self.country_id: int | None = None
        self._cancelled = Event()
        self._progress_value = 0
        self._final_done_event: GenerationEvent | None = None

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
                generation_completed = self._run_generator(
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
            except LoadOrderResolutionError as exc:
                self._emit_finished(
                    GenerationOutcomeCode.ERROR,
                    self._localize_load_order_error(exc, lang),
                )
                return
            except TypedCoreError as exc:
                if exc.code == "technology_swap_collision":
                    self._emit_finished(
                        GenerationOutcomeCode.ERROR,
                        t("ui_error_technology_swap_collision", lang, **exc.details_dict()),
                    )
                    return
                self._emit_finished(
                    GenerationOutcomeCode.ERROR,
                    self._unknown_error_code_message(exc.code),
                )
                return

            resolved_done_event = self._final_done_event
            done_details = dict(resolved_done_event.details) if resolved_done_event else {}
            outcome_code = str(done_details.get("outcome_code", "")).strip().lower()

            if outcome_code == GenerationOutcomeCode.SUCCESS.value:
                self._emit_finished(GenerationOutcomeCode.SUCCESS)
                return

            if outcome_code == GenerationOutcomeCode.CANCELLED.value:
                self._emit_finished(
                    GenerationOutcomeCode.CANCELLED,
                    t("ui_worker_generation_cancelled", lang),
                )
                return

            if outcome_code == GenerationOutcomeCode.ERROR.value:
                message = (resolved_done_event.message if resolved_done_event else "").strip()
                if not message:
                    message = t("ui_msgbox_body_generation_failed", lang, error="unknown error")
                self._emit_finished(GenerationOutcomeCode.ERROR, message)
                return

            if outcome_code == GenerationOutcomeCode.INCOMPLETE.value or not generation_completed:
                message = t("ui_worker_generation_incomplete", lang)
                failed_paths = str(done_details.get("artifact_failed_paths", "")).strip()
                if failed_paths:
                    message = f"{message}\n{failed_paths}"
                self._emit_finished(GenerationOutcomeCode.INCOMPLETE, message)
                return

            # Legacy fallback: treat DONE/100 as success.
            self._emit_finished(GenerationOutcomeCode.SUCCESS)
        except SaveReaderError as exc:
            self._emit_finished(GenerationOutcomeCode.UNSUPPORTED_SAVE_FORMAT, str(exc))
        except Exception as exc:  # pragma: no cover - GUI error handling
            self.log_message.emit(traceback.format_exc().rstrip())
            self._emit_finished(GenerationOutcomeCode.ERROR, str(exc))

    @staticmethod
    def _unknown_error_code_message(code: str) -> str:
        return f"Unknown error code: {code}"

    def _localize_load_order_error(
        self,
        exc: LoadOrderResolutionError,
        lang: str,
    ) -> str:
        key = _LOAD_ORDER_ERROR_KEYS.get(exc.code)
        if not key:
            return self._unknown_error_code_message(exc.code)

        english = LOCALIZATION_STRINGS.get("english", {})
        if key not in english:
            return self._unknown_error_code_message(exc.code)

        return t(key, lang, **exc.details_dict())

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

    def _run_generator(self, *, save_path: str, country_id: int | None) -> bool:
        from generator import TechTreeGenerator

        if self._application_root is None:
            generator = TechTreeGenerator(settings=self._settings_snapshot)
        else:
            generator = TechTreeGenerator(
                settings=self._settings_snapshot,
                application_root=self._application_root,
            )
        self._progress_value = 0
        self._final_done_event = None
        generator.run_generation_process(
            save_path=save_path,
            country_id=country_id,
            event_sink=_QtEventSink(self._handle_generation_event),
            cancel_event=self._cancelled,
        )

        return self._is_successful_done_event(self._final_done_event)

    def _ui_language(self) -> str:
        return require_supported_language(self._settings_snapshot.localization.language)

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

        if event.stage_id == StageId.DONE:
            self._final_done_event = event

    @staticmethod
    def _is_successful_done_event(event: GenerationEvent | None) -> bool:
        if event is None:
            return False

        details = dict(event.details)
        outcome_code = str(details.get("outcome_code", "")).strip().lower()
        if outcome_code:
            return outcome_code == GenerationOutcomeCode.SUCCESS.value

        # Legacy fallback: DONE/100% implies success.
        return event.kind == EventKind.PROGRESS and event.progress == 100

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
