from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class StageId(str, Enum):
    SAVE_PARSE = "SAVE_PARSE"
    LOAD_ORDER = "LOAD_ORDER"
    INGEST_TECH = "INGEST_TECH"
    INGEST_L10N = "INGEST_L10N"
    RELATIONS = "RELATIONS"
    CYCLES = "CYCLES"
    RENDER = "RENDER"
    WRITE_OUTPUT = "WRITE_OUTPUT"
    DONE = "DONE"


class EventKind(str, Enum):
    PROGRESS = "progress"
    LOG = "log"
    WARNING = "warning"
    ERROR = "error"
    ARTIFACT = "artifact"


@dataclass(frozen=True)
class GenerationEvent:
    stage_id: StageId
    kind: EventKind
    message: str
    progress: int | None = None
    artifact_path: str | None = None
    details: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.progress is not None and not 0 <= self.progress <= 100:
            raise ValueError("progress must be between 0 and 100")

        if self.artifact_path is not None and not self.artifact_path.strip():
            raise ValueError("artifact_path must not be blank")

        normalized_details: list[tuple[str, str]] = []
        for detail in self.details:
            if len(detail) != 2:
                raise ValueError("details entries must be (key, value) tuples")
            key, value = detail
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("details entries must be (str, str)")
            normalized_details.append((key, value))

        object.__setattr__(self, "details", tuple(normalized_details))


@runtime_checkable
class EventSink(Protocol):
    def emit(self, event: GenerationEvent) -> None: ...


class NullEventSink:
    def emit(self, event: GenerationEvent) -> None:
        _ = event


__all__ = [
    "EventKind",
    "EventSink",
    "GenerationEvent",
    "NullEventSink",
    "StageId",
]
