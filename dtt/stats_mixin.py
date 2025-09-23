from collections import Counter


class StatsMixin:
    def calculate_generation_statistics(self):
        stats = {
            'total': len(self.all_technologies),
            'base': len(self.base_game_tech_ids),
            'dangerous': sum(1 for t in self.all_technologies.values() if t.is_dangerous_tech),
            'repeatable': sum(1 for t in self.all_technologies.values() if t.is_repeatable_tech),
            'per_area': dict(Counter(t.research_area or 'unknown' for t in self.all_technologies.values())),
            'per_tier': dict(Counter(t.tier_level for t in self.all_technologies.values()))
        }
        stats['mod'] = stats['total'] - stats['base']
        return stats

    def display_generation_statistics(self):
        stats = self.calculate_generation_statistics()
        print(f"\n{self._l('stats_header')}")
        print(self._l('stats_total', total=stats['total'], base=stats['base'], mod=stats['mod']))
        localized_count = sum(1 for descs in self.tech_descriptions.values() if self.target_language_code in descs)
        print(self._l('stats_localization', lang=self.target_language_code, count=localized_count))
        if self.overlong_tech_ids:
            print(self._l('stats_overlong', threshold=self.max_display_nodes, count=len(self.overlong_tech_ids)))
            self._print_overlong_tree_roots()
        else:
            if self.max_display_nodes > 0:
                print(self._l('overbreadth_zero', threshold=self.max_display_nodes))
