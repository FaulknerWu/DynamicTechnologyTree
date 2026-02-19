from __future__ import annotations

import configparser
import traceback
from dataclasses import dataclass
from enum import Enum
from threading import Event
from typing import Any, Callable

from PyQt6.QtCore import QThread, pyqtSignal

from dtt_core.events import EventKind, EventSink, GenerationEvent, StageId
from dtt_core.sav_reader import SaveReaderError, load_save_context
from dtt_core.save_context import SaveContext
from gui.i18n import LOCALIZATION_STRINGS, default_language_from_system, t


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

    def __init__(self, config_path: str, parent=None) -> None:
        super().__init__(parent)
        self.config_path = config_path
        self.save_path: str | None = None
        self.country_id: int | None = None
        self._cancelled = Event()
        self._progress_value = 0
        self._saw_generation_done = False

    def run(self) -> None:
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
            save_context = self._inspect_save_context(save_path)
            candidates = tuple(sorted(save_context.player_country_candidates))
            if self.country_id is None and len(candidates) > 1:
                self._emit_finished(
                    GenerationOutcomeCode.AMBIGUOUS_COUNTRY_SELECTION,
                    empire_options=tuple(
                        self._build_ambiguous_empire_options(save_context)
                    ),
                )
                return

            selected_country_id = self.country_id
            if selected_country_id is None and len(candidates) == 1:
                selected_country_id = candidates[0]

            if self._run_generator(save_path=save_path, country_id=selected_country_id):
                self._emit_finished(GenerationOutcomeCode.SUCCESS)
            else:
                self._emit_finished(
                    GenerationOutcomeCode.INCOMPLETE,
                    t("ui_worker_generation_incomplete", lang),
                )
        except SaveReaderError as exc:
            self._emit_finished(GenerationOutcomeCode.UNSUPPORTED_SAVE_FORMAT, str(exc))
        except Exception as exc:  # pragma: no cover - GUI error handling
            self.log_message.emit(traceback.format_exc().rstrip())
            self._emit_finished(GenerationOutcomeCode.ERROR, str(exc))

    def _inspect_save_context(self, save_path: str) -> SaveContext:
        return load_save_context(save_path)

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

        generator = TechTreeGenerator(self.config_path)
        self._progress_value = 0
        self._saw_generation_done = False
        generator.run_generation_process(
            save_path=save_path,
            country_id=country_id,
            event_sink=_QtEventSink(self._handle_generation_event),
        )

        return self._saw_generation_done

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

        if (
            event.stage_id == StageId.DONE
            and event.kind == EventKind.PROGRESS
            and event.progress == 100
        ):
            self._saw_generation_done = True

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
