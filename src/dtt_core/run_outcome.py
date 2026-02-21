from __future__ import annotations

from enum import Enum


class RunOutcomeCode(str, Enum):
    SUCCESS = "success"
    INCOMPLETE = "incomplete"
    CANCELLED = "cancelled"
    ERROR = "error"


__all__ = ["RunOutcomeCode"]

