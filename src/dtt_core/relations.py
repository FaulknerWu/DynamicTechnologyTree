from config import DisplayConfig
from models import Technology


class RelationsBuilder:
    def __init__(
        self,
        all_technologies: dict[str, Technology],
        overlong_tech_ids: set[str],
        display_config: DisplayConfig,
    ) -> None:
        self.all_technologies = all_technologies
        self.overlong_tech_ids = overlong_tech_ids
        self.display_config = display_config

    def build_technology_tree_relationships(self) -> None:
        for tech in self.all_technologies.values():
            for prereq_id in tech.prerequisite_tech_ids:
                if prereq_id in self.all_technologies:
                    prereq_tech = self.all_technologies[prereq_id]
                    if tech.tech_id not in prereq_tech.unlocked_tech_ids:
                        prereq_tech.unlocked_tech_ids.append(tech.tech_id)

    def precompute_overlong_trees(self) -> None:
        self.overlong_tech_ids.clear()
        T = self.display_config.max_display_nodes
        if T <= 0:
            return
        for tid, tech in self.all_technologies.items():
            if len(tech.unlocked_tech_ids) > T:
                self.overlong_tech_ids.add(tid)
