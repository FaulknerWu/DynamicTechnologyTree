from __future__ import annotations

from dtt_core.events import GenerationEvent


class StdoutEventSink:
    def emit(self, event: GenerationEvent) -> None:
        if event.message == "":
            return
        print(event.message)


__all__ = ["StdoutEventSink"]
