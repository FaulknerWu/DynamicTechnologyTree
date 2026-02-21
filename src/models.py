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

    def __post_init__(self):
        dangerous_tech_list = {
            "tech_synthetic_workers",
            "tech_sapient_ai",
            "tech_positronic_ai",
            "tech_mega_engineering",
            "tech_colossus",
            "tech_juggernaut",
        }
        self.is_dangerous_tech = self.tech_id in dangerous_tech_list
        self.is_repeatable_tech = "repeatable" in self.tech_id
