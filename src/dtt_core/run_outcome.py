from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from dtt_core.output import ArtifactWriteSummary
from dtt_core.typed_error import TypedErrorDetails


class RunOutcomeCode(str, Enum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(frozen=True)
class RunOutcome:
    code: RunOutcomeCode
    artifact_summary: ArtifactWriteSummary = field(default_factory=ArtifactWriteSummary)
    message: str = ""
    error_code: str = ""
    error_details: TypedErrorDetails = ()


__all__ = ["RunOutcome", "RunOutcomeCode"]
