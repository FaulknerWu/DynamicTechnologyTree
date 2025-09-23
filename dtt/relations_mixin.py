class RelationsMixin:
    def build_technology_tree_relationships(self):
        for tech in self.all_technologies.values():
            for prereq_id in tech.prerequisite_tech_ids:
                if prereq_id in self.all_technologies:
                    prereq_tech = self.all_technologies[prereq_id]
                    if tech.tech_id not in prereq_tech.unlocked_tech_ids:
                        prereq_tech.unlocked_tech_ids.append(tech.tech_id)

    def _precompute_overlong_trees(self) -> None:
        self.overlong_tech_ids.clear()
        T = self.max_display_nodes
        if T <= 0:
            return
        for tid, tech in self.all_technologies.items():
            if len(tech.unlocked_tech_ids) > T:
                self.overlong_tech_ids.add(tid)

    def _print_overlong_tree_roots(self, limit: int = 50):
        T = self.max_display_nodes
        if T <= 0:
            return
        roots = sorted(self.overlong_tech_ids)
        if not roots:
            return
        print(self._l('overbreadth_list_header'))
        for idx, tid in enumerate(roots):
            if idx >= limit:
                remaining = len(roots) - limit
                print(self._l('overbreadth_truncated', remaining=remaining))
                break
            tech = self.all_technologies.get(tid)
            child_cnt = len(tech.unlocked_tech_ids) if tech else 0
            print(self._l('overbreadth_entry', tech_id=tid, child_count=child_cnt, threshold=T))
