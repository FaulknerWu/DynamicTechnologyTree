from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .models import Technology
from .localization import RESEARCH_AREA_ICONS, LOCALIZATION_STRINGS


@dataclass
class RenderContext:
    """Immutable rendering configuration."""
    root_id: str
    max_depth: int          # X limit
    max_children: int       # Y limit
    max_nodes: int          # T limit
    lang_code: str
    display_overrides: Optional[Dict[str, str]]
    suppress_overflow_line: bool
    # Pre-computed localized strings
    already_shown_text: str = ""
    folded_more_tpl: str = ""
    global_overflow_tpl: str = ""


@dataclass
class RenderState:
    """Mutable state during rendering."""
    lines: List[str] = field(default_factory=list)
    visited_unique: Set[str] = field(default_factory=set)
    overflow: bool = False


class RenderMixin:
    MAX_PREREQ_DISPLAY = 2
    ELLIPSIS = "…"

    def _format_single_tech(self, tech: Technology, display_id: Optional[str] = None) -> str:
        display_id = display_id or tech.tech_id
        area_icon = RESEARCH_AREA_ICONS.get(tech.research_area, "")
        if tech.is_dangerous_tech:
            color = '§R'
        elif tech.tier_level >= 5 or tech.is_repeatable_tech:
            color = '§M'
        else:
            color = '§W'
        return f"({tech.tier_level})['technology:{tech.tech_id}', {area_icon}{color}${display_id}$§!]"

    def _format_tech_tree_entry(self, tech_id: str, prefix_bars: list[bool], current_prereq: str = None, lang_code: str = "simp_chinese", display_overrides: Optional[Dict[str, str]] = None, collapsed: bool = False, is_last: bool = False) -> str:
        if tech_id not in self.all_technologies:
            return ""
        tech = self.all_technologies[tech_id]
        display_id = display_overrides.get(tech_id, tech_id) if display_overrides else tech_id
        prefix_parts = ["│   " if keep else "    " for keep in prefix_bars[:-1]] if prefix_bars else []
        branch_symbol = "└─" if is_last else "├─"
        line_prefix = "".join(prefix_parts) + branch_symbol
        formatted = self._format_single_tech(tech, display_id)
        additional_prereqs = []
        if current_prereq and len(tech.prerequisite_tech_ids) > 1:
            for prereq_id in tech.prerequisite_tech_ids:
                if prereq_id == current_prereq or prereq_id not in self.all_technologies:
                    continue
                prereq_tech = self.all_technologies[prereq_id]
                display_prereq_id = display_overrides.get(prereq_id, prereq_id) if display_overrides else prereq_id
                additional_prereqs.append(self._format_single_tech(prereq_tech, display_prereq_id))
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
        T = self.config.display.max_display_nodes
        root_children_count = len(root.unlocked_tech_ids)
        if T > 0 and root_children_count > T:
            return -1
        max_tree_depth = self.config.display.max_tree_depth
        X_max = max_tree_depth if max_tree_depth > 0 else self._compute_actual_max_depth(root_id)
        if X_max <= 0:
            X_max = 1
        Y_max_config = self.config.display.max_children_per_node
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

    def _create_render_context(self, root_id: str, x: int, y: int, T: int, lang_code: str, display_overrides: Optional[Dict[str, str]] = None, suppress_overflow_line: bool = False) -> RenderContext:
        strings = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english'])
        return RenderContext(
            root_id=root_id,
            max_depth=x,
            max_children=y,
            max_nodes=T,
            lang_code=lang_code,
            display_overrides=display_overrides,
            suppress_overflow_line=suppress_overflow_line,
            already_shown_text=strings.get("already_shown", "already shown"),
            folded_more_tpl=strings.get("folded_more", "({count} more)"),
            global_overflow_tpl=strings.get("global_overflow_reached", "(and {count} more)"),
        )

    def _get_sorted_children(self, tech: Technology) -> List[str]:
        return sorted(tech.unlocked_tech_ids, key=lambda cid: (self.all_technologies.get(cid, Technology(cid)).tier_level, cid))

    def _apply_children_limit(self, children: List[str], is_root: bool, max_children: int) -> Tuple[List[str], bool]:
        if (not is_root) and max_children > 0 and len(children) > max_children:
            return children[:max_children], True
        return children, False

    def _check_node_overflow(self, ctx: RenderContext, state: RenderState, display_children: List[str], idx: int, parent_depth: int, prefix_bars: List[bool]) -> bool:
        if ctx.max_nodes > 0 and len(state.visited_unique) >= ctx.max_nodes:
            remaining_nodes = display_children[idx:]
            more = self._count_remaining_unique(remaining_nodes, ctx.root_id, ctx.max_depth, ctx.max_children, parent_depth, state.visited_unique)
            state.overflow = True
            if not ctx.suppress_overflow_line:
                prefix_parts = ["│   " if keep else "    " for keep in prefix_bars]
                state.lines.append("".join(prefix_parts) + "└─" + self.ELLIPSIS + ctx.global_overflow_tpl.format(count=more))
            return True
        return False

    def _render_single_child(self, ctx: RenderContext, state: RenderState, parent_id: str, child_id: str, parent_depth: int, prefix_bars: List[bool], has_more_siblings: bool) -> None:
        line = self._format_tech_tree_entry(child_id, prefix_bars + [has_more_siblings], parent_id, ctx.lang_code, display_overrides=ctx.display_overrides, is_last=not has_more_siblings)
        if not line:
            return
        duplicate = child_id in state.visited_unique
        if duplicate:
            line += f" §g({ctx.already_shown_text})§!"
        else:
            state.visited_unique.add(child_id)
        state.lines.append(line)
        if not duplicate and (parent_depth + 1) < ctx.max_depth and not state.overflow:
            child_tech = self.all_technologies.get(child_id)
            if child_tech and child_tech.unlocked_tech_ids:
                self._render_children(ctx, state, child_id, self._get_sorted_children(child_tech), parent_depth + 1, False, prefix_bars + [has_more_siblings])

    def _append_truncation_message(self, ctx: RenderContext, state: RenderState, hidden: int, prefix_bars: List[bool]) -> None:
        if hidden <= 0:
            return
        prefix_parts = ["│   " if keep else "    " for keep in prefix_bars]
        state.lines.append("".join(prefix_parts) + "└─" + self.ELLIPSIS + ctx.folded_more_tpl.format(count=hidden))

    def _render_children(self, ctx: RenderContext, state: RenderState, parent_id: str, children: List[str], parent_depth: int, is_root: bool, prefix_bars: List[bool]) -> None:
        if state.overflow:
            return
        if parent_depth >= ctx.max_depth:
            return
        display_children, truncated = self._apply_children_limit(children, is_root, ctx.max_children)
        for idx, cid in enumerate(display_children):
            if state.overflow:
                break
            if self._check_node_overflow(ctx, state, display_children, idx, parent_depth, prefix_bars):
                break
            has_more_siblings = (idx < len(display_children) - 1) or (truncated and not state.overflow)
            self._render_single_child(ctx, state, parent_id, cid, parent_depth, prefix_bars, has_more_siblings)
        if not state.overflow and truncated:
            hidden = len(children) - len(display_children)
            self._append_truncation_message(ctx, state, hidden, prefix_bars)

    def _render_tree_with_limits(self, root_id: str, x: int, y: int, T: int, lang_code: str, display_overrides: Optional[Dict[str, str]] = None, suppress_overflow_line: bool = False) -> Tuple[List[str], bool]:
        if root_id not in self.all_technologies:
            return [], False
        ctx = self._create_render_context(root_id, x, y, T, lang_code, display_overrides, suppress_overflow_line)
        state = RenderState()
        root = self.all_technologies[root_id]
        root_children = self._get_sorted_children(root)
        self._render_children(ctx, state, root_id, root_children, parent_depth=0, is_root=True, prefix_bars=[])
        return state.lines, state.overflow

    def _check_root_overflow(self, tech_id: str, T: int, lang_code: str) -> bool:
        root = self.all_technologies[tech_id]
        root_children_count = len(root.unlocked_tech_ids)
        if T > 0 and root_children_count > T:
            try:
                if hasattr(self, 'overlong_tech_ids'):
                    self.overlong_tech_ids.add(tech_id)
            except Exception:
                pass
            return True
        return False

    def _format_root_overflow_message(self, header: str, lang_code: str) -> str:
        msg = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english']).get("root_children_exceed_limit", "Root children exceed limit")
        content = f"{header}\n└─§R{msg}§!"
        return content.replace("\n", "\\n")

    def _get_raw_render_params(self, tech_id: str) -> Tuple[int, int]:
        max_tree_depth = self.config.display.max_tree_depth
        raw_x = max_tree_depth if max_tree_depth > 0 else self._compute_actual_max_depth(tech_id)
        if raw_x <= 0:
            raw_x = 1
        raw_y = self.config.display.max_children_per_node
        return raw_x, raw_y

    def _finalize_tree_content(self, header: str, tech_id: str, x: int, y: int, T: int, lang_code: str, display_overrides: Optional[Dict[str, str]] = None) -> str:
        lines_stage_final, _ = self._render_tree_with_limits(tech_id, x, y, T, lang_code, display_overrides=display_overrides, suppress_overflow_line=False)
        if not lines_stage_final:
            content = f"{header}\n§Y$tech_tree_max_level$§!"
        else:
            content = header + "\n" + "\n".join(lines_stage_final)
        return content.replace("\n", "\\n")

    def _render_with_optimized_params(self, header: str, tech_id: str, T: int, lang_code: str, display_overrides: Optional[Dict[str, str]] = None) -> str:
        chosen = self._choose_best_xy_for_root(tech_id)
        if chosen == -1:
            return self._format_root_overflow_message(header, lang_code)
        best_x, best_y, _ = chosen
        return self._finalize_tree_content(header, tech_id, best_x, best_y, T, lang_code, display_overrides)

    def generate_tech_tree_content(self, tech_id: str, lang_code: str = "simp_chinese", display_overrides: Optional[Dict[str, str]] = None) -> str:
        if tech_id not in self.all_technologies:
            return ""
        header = "\\n\\n§H$technology_tree_title$§!"
        T = self.config.display.max_display_nodes
        if self._check_root_overflow(tech_id, T, lang_code):
            return self._format_root_overflow_message(header, lang_code)

        raw_x, raw_y = self._get_raw_render_params(tech_id)
        lines_stage_probe, overflow_stage_probe = self._render_tree_with_limits(tech_id, raw_x, raw_y, T, lang_code, display_overrides=display_overrides, suppress_overflow_line=True)
        if not overflow_stage_probe or T == 0:
            return self._finalize_tree_content(header, tech_id, raw_x, raw_y, T, lang_code, display_overrides)

        return self._render_with_optimized_params(header, tech_id, T, lang_code, display_overrides)
