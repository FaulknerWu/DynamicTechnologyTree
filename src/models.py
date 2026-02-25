from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Technology:
    tech_id: str
    research_area: str = ""
    tier_level: int = 0
    prerequisite_tech_ids: list[str] = field(default_factory=list)
    unlocked_tech_ids: list[str] = field(default_factory=list)
    is_dangerous_tech: bool = False
    is_repeatable_tech: bool = False
