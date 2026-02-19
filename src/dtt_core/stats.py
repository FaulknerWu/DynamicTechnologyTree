from collections import Counter
from typing import Callable, Dict, Set

from config import GeneratorConfig
from dtt_core.events import (
    EventKind,
    EventSink,
    GenerationEvent,
    NullEventSink,
    StageId,
)
from models import Technology


class StatsReporter:
    def __init__(
        self,
        all_technologies: Dict[str, Technology],
        base_game_tech_ids: Set[str],
        tech_descriptions: Dict[str, Dict[str, str]],
        overlong_tech_ids: Set[str],
        config: GeneratorConfig,
        localize: Callable[..., str],
        print_overlong_tree_roots: Callable[[], None],
        event_sink: EventSink | None = None,
    ) -> None:
        self.all_technologies = all_technologies
        self.base_game_tech_ids = base_game_tech_ids
        self.tech_descriptions = tech_descriptions
        self.overlong_tech_ids = overlong_tech_ids
        self.config = config
        self._l = localize
        self._print_overlong_tree_roots = print_overlong_tree_roots
        self._event_sink: EventSink = (
            event_sink if event_sink is not None else NullEventSink()
        )

    def set_event_sink(self, event_sink: EventSink | None) -> None:
        self._event_sink = event_sink if event_sink is not None else NullEventSink()

    def _emit(self, kind: EventKind, message: str) -> None:
        self._event_sink.emit(
            GenerationEvent(
                stage_id=StageId.RENDER,
                kind=kind,
                message=message,
            )
        )

    def calculate_generation_statistics(self) -> Dict[str, object]:
        stats = {
            "total": len(self.all_technologies),
            "base": len(self.base_game_tech_ids),
            "dangerous": sum(
                1 for t in self.all_technologies.values() if t.is_dangerous_tech
            ),
            "repeatable": sum(
                1 for t in self.all_technologies.values() if t.is_repeatable_tech
            ),
            "per_area": dict(
                Counter(
                    t.research_area or "unknown" for t in self.all_technologies.values()
                )
            ),
            "per_tier": dict(
                Counter(t.tier_level for t in self.all_technologies.values())
            ),
        }
        stats["mod"] = stats["total"] - stats["base"]
        return stats

    def display_generation_statistics(self) -> None:
        stats = self.calculate_generation_statistics()
        self._emit(EventKind.LOG, f"\n{self._l('stats_header')}")
        self._emit(
            EventKind.LOG,
            self._l(
                "stats_total",
                total=stats["total"],
                base=stats["base"],
                mod=stats["mod"],
            ),
        )
        lang_code = self.config.localization.target_language_code
        localized_count = sum(
            1 for descs in self.tech_descriptions.values() if lang_code in descs
        )
        self._emit(
            EventKind.LOG,
            self._l("stats_localization", lang=lang_code, count=localized_count),
        )
        if self.overlong_tech_ids:
            self._emit(
                EventKind.WARNING,
                self._l(
                    "stats_overlong",
                    threshold=self.config.display.max_display_nodes,
                    count=len(self.overlong_tech_ids),
                ),
            )
            self._print_overlong_tree_roots()
        else:
            max_display_nodes = self.config.display.max_display_nodes
            if max_display_nodes > 0:
                self._emit(
                    EventKind.LOG,
                    self._l("overbreadth_zero", threshold=max_display_nodes),
                )
