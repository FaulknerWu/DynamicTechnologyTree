from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Protocol, runtime_checkable


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


class EventEmitterMixin:
    """统一事件发射行为的 Mixin。子类通过设置 _STAGE_ID 类属性指定默认阶段。"""

    _STAGE_ID: ClassVar[StageId]
    _event_sink: EventSink

    def _init_event_sink(self, event_sink: EventSink | None) -> None:
        """在 __init__ 中调用以初始化 event_sink。"""
        self._event_sink = event_sink if event_sink is not None else NullEventSink()

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        """替换当前 event sink。"""
        self._event_sink = event_sink if event_sink is not None else NullEventSink()

    def _emit(
        self,
        kind: EventKind,
        message: str,
        *,
        stage_id: StageId | None = None,
        progress: int | None = None,
        artifact_path: str | None = None,
        details: tuple[tuple[str, str], ...] = (),
    ) -> None:
        """发射一个生成事件。stage_id 默认使用类属性 _STAGE_ID。"""
        self._event_sink.emit(
            GenerationEvent(
                stage_id=stage_id if stage_id is not None else self._STAGE_ID,
                kind=kind,
                message=message,
                progress=progress,
                artifact_path=artifact_path,
                details=details,
            )
        )


__all__ = [
    "EventEmitterMixin",
    "EventKind",
    "EventSink",
    "GenerationEvent",
    "NullEventSink",
    "StageId",
]
