from typing import List, Set, Tuple

from .models import Technology
from .localization import RESEARCH_AREA_ICONS, LOCALIZATION_STRINGS


class RenderMixin:
    MAX_PREREQ_DISPLAY = 2
    ELLIPSIS = "…"

    def _format_single_tech(self, tech: Technology) -> str:
        area_icon = RESEARCH_AREA_ICONS.get(tech.research_area, "")
        if tech.is_dangerous_tech:
            color = '§R'
        elif tech.tier_level >= 5 or tech.is_repeatable_tech:
            color = '§M'
        else:
            color = '§W'
        return f"({tech.tier_level})['technology:{tech.tech_id}', {area_icon}{color}${tech.tech_id}$§!]"

    def _format_tech_tree_entry(self, tech_id: str, prefix_bars: list[bool], current_prereq: str = None, lang_code: str = "simp_chinese", collapsed: bool = False, is_last: bool = False) -> str:
        if tech_id not in self.all_technologies:
            return ""
        tech = self.all_technologies[tech_id]
        prefix_parts = ["│   " if keep else "    " for keep in prefix_bars[:-1]] if prefix_bars else []
        branch_symbol = "└─" if is_last else "├─"
        line_prefix = "".join(prefix_parts) + branch_symbol
        formatted = self._format_single_tech(tech)
        additional_prereqs = []
        if current_prereq and len(tech.prerequisite_tech_ids) > 1:
            for prereq_id in tech.prerequisite_tech_ids:
                if prereq_id == current_prereq or prereq_id not in self.all_technologies:
                    continue
                prereq_tech = self.all_technologies[prereq_id]
                additional_prereqs.append(self._format_single_tech(prereq_tech))
        prereq_suffix = ""
        if additional_prereqs:
            requires_text = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english']).get("requires", "Requires")
            if len(additional_prereqs) > self.MAX_PREREQ_DISPLAY:
                display_list = additional_prereqs[: self.MAX_PREREQ_DISPLAY]
                display_text = " , ".join(display_list) + f" {self.ELLIPSIS}"
            else:
                display_text = " , ".join(additional_prereqs)
            prereq_suffix = f" [§R{requires_text}§! {display_text}]"
        collapse_suffix = f" {self.ELLIPSIS}" if collapsed else ""
        return f"{line_prefix}{formatted}{prereq_suffix}{collapse_suffix}"

    def _compute_actual_max_depth(self, root_id: str) -> int:
        if root_id not in self.all_technologies:
            return 0
        max_depth = 0
        visited: Set[str] = set()
        stack = [(root_id, 0)]
        while stack:
            nid, d = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)
            max_depth = max(max_depth, d)
            tech = self.all_technologies.get(nid)
            if not tech:
                continue
            for cid in tech.unlocked_tech_ids:
                if cid not in visited:
                    stack.append((cid, d + 1))
        return max_depth

    def _compute_max_degree_except_root(self, root_id: str) -> int:
        m = 0
        for tid, tech in self.all_technologies.items():
            if tid == root_id:
                continue
            m = max(m, len(tech.unlocked_tech_ids))
        return max(m, 1)

    def _visit_count_for_limits(self, root_id: str, x: int, y: int, T: int) -> int:
        if root_id not in self.all_technologies:
            return 0
        visited: Set[str] = set()

        def dfs(nid: str, depth: int, is_root: bool):
            if x > 0 and depth > x:
                return
            tech = self.all_technologies.get(nid)
            if not tech:
                return
            children = sorted(tech.unlocked_tech_ids, key=lambda cid: (self.all_technologies.get(cid, Technology(cid)).tier_level, cid))
            if not is_root and y > 0 and len(children) > y:
                children = children[:y]
            for cid in children:
                if cid not in visited:
                    visited.add(cid)
                    if T > 0 and len(visited) > T:
                        return
                    dfs(cid, depth + 1, False)

        from .models import Technology
        dfs(root_id, 0, True)
        return len(visited)

    def _choose_best_xy_for_root(self, root_id: str):
        if root_id not in self.all_technologies:
            return -1
        root = self.all_technologies[root_id]
        T = self.max_display_nodes
        root_children_count = len(root.unlocked_tech_ids)
        if T > 0 and root_children_count > T:
            return -1
        X_max = self.max_tree_depth if self.max_tree_depth > 0 else self._compute_actual_max_depth(root_id)
        if X_max <= 0:
            X_max = 1
        Y_max_config = self.max_children_per_node
        if Y_max_config > 0:
            Y_max = Y_max_config
        else:
            Y_max = self._compute_max_degree_except_root(root_id)
        best_x = 0
        best_y = 0
        best_size = -1
        for x in range(X_max, 0, -1):
            if T > 0 and best_size == T:
                break
            low, high = 1, Y_max
            feasible_y = None
            feasible_size = -1
            if Y_max == 1:
                size = self._visit_count_for_limits(root_id, x, 1, T)
                if T == 0 or size <= T:
                    feasible_y = 1
                    feasible_size = size
            else:
                while low <= high:
                    mid = (low + high) // 2
                    size = self._visit_count_for_limits(root_id, x, mid, T)
                    if T == 0:
                        feasible_y = mid
                        feasible_size = size
                        low = mid + 1
                    else:
                        if size > T:
                            high = mid - 1
                        else:
                            feasible_y = mid
                            feasible_size = size
                            low = mid + 1
            if feasible_y is not None:
                if (feasible_size > best_size or
                    (feasible_size == best_size and x > best_x) or
                    (feasible_size == best_size and x == best_x and feasible_y > best_y)):
                    best_x, best_y, best_size = x, feasible_y, feasible_size
        if best_size < 0:
            return -1
        return best_x, best_y, best_size

    def _count_remaining_unique(self, start_nodes: List[str], root_id: str, x: int, y: int, current_depth: int, visited_global: Set[str]) -> int:
        if not start_nodes:
            return 0
        stack = []
        for n in start_nodes:
            stack.append((n, current_depth + 1))
        local_seen: Set[str] = set()
        from .models import Technology
        while stack:
            nid, d = stack.pop()
            if nid in visited_global or nid in local_seen:
                continue
            local_seen.add(nid)
            if d >= x:
                continue
            tech = self.all_technologies.get(nid)
            if not tech:
                continue
            children = sorted(tech.unlocked_tech_ids, key=lambda cid: (self.all_technologies.get(cid, Technology(cid)).tier_level, cid))
            if d > 0 and y > 0:
                if nid != root_id and len(children) > y:
                    children = children[:y]
            for cid in children:
                stack.append((cid, d + 1))
        return len(local_seen)
    def _render_tree_with_limits(self, root_id: str, x: int, y: int, T: int, lang_code: str, suppress_overflow_line: bool = False):
        from .models import Technology
        if root_id not in self.all_technologies:
            return [], False
        root = self.all_technologies[root_id]
        already_shown_text = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english']).get("already_shown", "already shown")
        folded_more_tpl = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english']).get("folded_more", "({count} more)")
        global_overflow_tpl = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english']).get("global_overflow_reached", "(and {count} more)")
        lines: List[str] = []
        visited_unique: Set[str] = set()
        overflow = False
        root_children = sorted(root.unlocked_tech_ids, key=lambda cid: (self.all_technologies.get(cid, Technology(cid)).tier_level, cid))

        def render_children(parent_id: str, children: List[str], parent_depth: int, is_root: bool, prefix_bars: List[bool]):
            nonlocal overflow
            if overflow:
                return
            if parent_depth >= x:
                return
            truncated = False
            display_children = children
            if (not is_root) and y > 0 and len(children) > y:
                display_children = children[:y]
                truncated = True
            for idx, cid in enumerate(display_children):
                if overflow:
                    break
                if T > 0 and len(visited_unique) >= T:
                    remaining_nodes = display_children[idx:]
                    more = self._count_remaining_unique(remaining_nodes, root_id, x, y, parent_depth, visited_unique)
                    overflow = True
                    if not suppress_overflow_line:
                        prefix_parts = ["│   " if keep else "    " for keep in prefix_bars]
                        lines.append("".join(prefix_parts) + "└─" + self.ELLIPSIS + global_overflow_tpl.format(count=more))
                    break
                has_more_siblings = (idx < len(display_children) - 1) or (truncated and not overflow)
                line = self._format_tech_tree_entry(cid, prefix_bars + [has_more_siblings], parent_id, lang_code, is_last=not has_more_siblings)
                if not line:
                    continue
                duplicate = cid in visited_unique
                if duplicate:
                    line += f" §g({already_shown_text})§!"
                else:
                    visited_unique.add(cid)
                lines.append(line)
                if not duplicate and (parent_depth + 1) < x and not overflow:
                    child_tech = self.all_technologies.get(cid)
                    if child_tech and child_tech.unlocked_tech_ids:
                        render_children(cid,
                                        sorted(child_tech.unlocked_tech_ids, key=lambda nid: (self.all_technologies.get(nid, Technology(nid)).tier_level, nid)),
                                        parent_depth + 1,
                                        False,
                                        prefix_bars + [has_more_siblings])
            if not overflow and truncated:
                hidden = len(children) - len(display_children)
                if hidden > 0:
                    prefix_parts = ["│   " if keep else "    " for keep in prefix_bars]
                    lines.append("".join(prefix_parts) + "└─" + self.ELLIPSIS + folded_more_tpl.format(count=hidden))

        render_children(root_id, root_children, 0, True, [])
        return lines, overflow

    def generate_tech_tree_content(self, tech_id: str, lang_code: str = "simp_chinese") -> str:
        if tech_id not in self.all_technologies:
            return ""
        header = "\\n\\n§H$technology_tree_title$§!"
        root = self.all_technologies[tech_id]
        T = self.max_display_nodes
        root_children_count = len(root.unlocked_tech_ids)
        if T > 0 and root_children_count > T:
            try:
                if hasattr(self, 'overlong_tech_ids'):
                    self.overlong_tech_ids.add(tech_id)
            except Exception:
                pass
            msg = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english']).get("root_children_exceed_limit", "Root children exceed limit")
            content = f"{header}\n└─§R{msg}§!"
            return content.replace("\n", "\\n")

        raw_x = self.max_tree_depth if self.max_tree_depth > 0 else self._compute_actual_max_depth(tech_id)
        if raw_x <= 0:
            raw_x = 1
        raw_y = self.max_children_per_node
        lines_stage_probe, overflow_stage_probe = self._render_tree_with_limits(tech_id, raw_x, raw_y, T, lang_code, suppress_overflow_line=True)

        if not overflow_stage_probe or T == 0:
            lines_stage_final, _ = self._render_tree_with_limits(tech_id, raw_x, raw_y, T, lang_code, suppress_overflow_line=False)
            if not lines_stage_final:
                content = f"{header}\n§Y$tech_tree_max_level$§!"
            else:
                content = header + "\n" + "\n".join(lines_stage_final)
            return content.replace("\n", "\\n")

        chosen = self._choose_best_xy_for_root(tech_id)
        if chosen == -1:
            msg = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english']).get("root_children_exceed_limit", "Root children exceed limit")
            content = f"{header}\n└─§R{msg}§!"
            return content.replace("\n", "\\n")
        best_x, best_y, _ = chosen
        lines_stage_final, overflow_final = self._render_tree_with_limits(tech_id, best_x, best_y, T, lang_code, suppress_overflow_line=False)
        if not lines_stage_final:
            content = f"{header}\n§Y$tech_tree_max_level$§!"
        else:
            content = header + "\n" + "\n".join(lines_stage_final)
        return content.replace("\n", "\\n")
