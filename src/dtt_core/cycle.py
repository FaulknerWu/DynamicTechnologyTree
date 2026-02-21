from collections.abc import Callable

from dtt_core.events import (
    EventKind,
    EventSink,
    GenerationEvent,
    NullEventSink,
    StageId,
)
from models import Technology


class CycleDetector:
    def __init__(
        self,
        all_technologies: dict[str, Technology],
        localize: Callable[..., str],
        event_sink: EventSink | None = None,
    ) -> None:
        self.all_technologies = all_technologies
        self._l = localize
        self._event_sink: EventSink = (
            event_sink if event_sink is not None else NullEventSink()
        )

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink if event_sink is not None else NullEventSink()

    def _emit(self, kind: EventKind, message: str) -> None:
        self._event_sink.emit(
            GenerationEvent(
                stage_id=StageId.CYCLES,
                kind=kind,
                message=message,
            )
        )

    def detect_circular_dependencies(self) -> list[list[str]]:
        cycles: list[list[str]] = []
        visited: set[str] = set()
        on_path: set[str] = set()
        stack: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            on_path.add(node)
            stack.append(node)
            tech = self.all_technologies.get(node)
            if tech:
                for nxt in tech.unlocked_tech_ids:
                    if nxt not in self.all_technologies:
                        continue
                    if nxt not in visited:
                        dfs(nxt)
                    elif nxt in on_path:
                        if nxt in stack:
                            idx = stack.index(nxt)
                            cycle = stack[idx:] + [nxt]
                            if cycle not in cycles:
                                cycles.append(cycle)
            stack.pop()
            on_path.remove(node)

        for tid in list(self.all_technologies.keys()):
            if tid not in visited:
                dfs(tid)
        return cycles

    def report_circular_dependencies(self) -> None:
        self._emit(EventKind.LOG, self._l("msg_detecting_cycles"))
        cycles = self.detect_circular_dependencies()
        if cycles:
            self._emit(
                EventKind.WARNING, self._l("msg_cycles_found", count=len(cycles))
            )
            self_loops = []
            complex_cycles = []
            for cycle in cycles:
                if len(cycle) == 2 and cycle[0] == cycle[1]:
                    self_loops.append(cycle[0])
                else:
                    complex_cycles.append(cycle)
            if self_loops:
                self._emit(
                    EventKind.WARNING,
                    self._l("msg_self_loops_header", count=len(self_loops)),
                )
                for tech in self_loops:
                    self._emit(
                        EventKind.WARNING, self._l("msg_self_loop_entry", tech=tech)
                    )
            if complex_cycles:
                self._emit(
                    EventKind.WARNING,
                    self._l("msg_complex_loops_header", count=len(complex_cycles)),
                )
                for i, cycle in enumerate(complex_cycles, 1):
                    cycle_str = " -> ".join(cycle)
                    self._emit(
                        EventKind.WARNING,
                        self._l("msg_cycle_entry", index=i, cycle=cycle_str),
                    )
        else:
            self._emit(EventKind.LOG, self._l("msg_no_cycles"))
