# pyright: reportArgumentType=false

from __future__ import annotations

from dataclasses import dataclass, field

from config import DisplayConfig
from localization import LOCALIZATION_STRINGS, RESEARCH_AREA_ICONS
from models import Technology

# Stellaris 文本颜色标记
DANGEROUS_TECH_COLOR = "§R"
HIGH_TIER_TECH_COLOR = "§M"
NORMAL_TECH_COLOR = "§W"


@dataclass
class RenderContext:
    """Immutable rendering configuration."""

    root_id: str
    max_depth: int
    max_children: int
    max_nodes: int
    lang_code: str
    display_overrides: dict[str, str] | None
    allowed_tech_ids: set[str] | None
    suppress_overflow_line: bool
    # 预计算的本地化字符串
    already_shown_text: str = ""
    folded_more_tpl: str = ""
    global_overflow_tpl: str = ""


@dataclass
class RenderState:
    """Mutable state during rendering."""

    lines: list[str] = field(default_factory=list)
    visited_unique: set[str] = field(default_factory=set)
    overflow: bool = False


class TreeRenderer:
    ELLIPSIS = "…"
    # Stellaris 中 tier >= 5 的科技使用高级颜色标记
    HIGH_TIER_THRESHOLD = 5

    # Stellaris UI 部分字体（特别是拉丁字符集）不包含 Unicode
    # 制表符（U+2500..U+257F），会渲染为 "??"。
    # 使用纯 ASCII 确保科技树前缀始终正常显示。
    TREE_BAR = "|   "
    TREE_EMPTY = "    "
    TREE_BRANCH = "|-"

    def __init__(
        self,
        all_technologies: dict[str, Technology],
        display_config: DisplayConfig,
        localization_strings: dict[str, dict[str, str]] = LOCALIZATION_STRINGS,
        research_area_icons: dict[str, str] = RESEARCH_AREA_ICONS,
        overlong_tech_ids: set[str] | None = None,
    ) -> None:
        self.all_technologies = all_technologies
        self.display_config = display_config
        self.localization_strings = localization_strings
        self.research_area_icons = research_area_icons
        self.overlong_tech_ids = overlong_tech_ids

    def _format_single_tech(
        self, tech: Technology, display_id: str | None = None
    ) -> str:
        display_id = display_id or tech.tech_id
        area_icon = self.research_area_icons.get(tech.research_area, "")
        if tech.is_dangerous_tech:
            color = DANGEROUS_TECH_COLOR
        elif tech.tier_level >= self.HIGH_TIER_THRESHOLD or tech.is_repeatable_tech:
            color = HIGH_TIER_TECH_COLOR
        else:
            color = NORMAL_TECH_COLOR
        return f"({tech.tier_level})['technology:{tech.tech_id}', {area_icon}{color}${display_id}$§!]"

    def _format_tech_tree_entry(
        self,
        tech_id: str,
        prefix_bars: list[bool],
        current_prereq: str = "",
        lang_code: str = "simp_chinese",
        display_overrides: dict[str, str] | None = None,
        allowed_tech_ids: set[str] | None = None,
        collapsed: bool = False,
    ) -> str:
        if tech_id not in self.all_technologies:
            return ""
        if not self._is_tech_allowed(tech_id, allowed_tech_ids):
            return ""
        tech = self.all_technologies[tech_id]
        display_id = (
            display_overrides.get(tech_id, tech_id) if display_overrides else tech_id
        )
        prefix_parts = (
            [self.TREE_BAR if keep else self.TREE_EMPTY for keep in prefix_bars[:-1]]
            if prefix_bars
            else []
        )
        branch_symbol = self.TREE_BRANCH
        line_prefix = "".join(prefix_parts) + branch_symbol
        formatted = self._format_single_tech(tech, display_id)
        additional_prereqs = []
        if current_prereq and len(tech.prerequisite_tech_ids) > 1:
            for prereq_id in tech.prerequisite_tech_ids:
                if (
                    prereq_id == current_prereq
                    or prereq_id not in self.all_technologies
                    or not self._is_tech_allowed(prereq_id, allowed_tech_ids)
                ):
                    continue
                prereq_tech = self.all_technologies[prereq_id]
                display_prereq_id = (
                    display_overrides.get(prereq_id, prereq_id)
                    if display_overrides
                    else prereq_id
                )
                additional_prereqs.append(
                    self._format_single_tech(prereq_tech, display_prereq_id)
                )
        prereq_suffix = ""
        if additional_prereqs:
            strings = self.localization_strings.get(
                lang_code, self.localization_strings["english"]
            )
            requires_text = strings.get("requires", "Requires")
            max_prereq_display = self.display_config.max_prereq_display
            if len(additional_prereqs) > max_prereq_display:
                display_list = additional_prereqs[:max_prereq_display]
                display_text = " , ".join(display_list)
                if display_text:
                    display_text += f" {self.ELLIPSIS}"
                else:
                    display_text = self.ELLIPSIS
            else:
                display_text = " , ".join(additional_prereqs)
            prereq_suffix = f" [§R{requires_text}§! {display_text}]"
        collapse_suffix = f" {self.ELLIPSIS}" if collapsed else ""
        return f"{line_prefix}{formatted}{prereq_suffix}{collapse_suffix}"

    def _is_tech_allowed(
        self, tech_id: str, allowed_tech_ids: set[str] | None
    ) -> bool:
        return allowed_tech_ids is None or tech_id in allowed_tech_ids

    def _compute_actual_max_depth(
        self, root_id: str, allowed_tech_ids: set[str] | None = None
    ) -> int:
        if root_id not in self.all_technologies:
            return 0
        if not self._is_tech_allowed(root_id, allowed_tech_ids):
            return 0
        max_depth = 0
        visited: set[str] = set()
        stack = [(root_id, 0)]
        while stack:
            node_id, depth = stack.pop()
            if node_id in visited:
                continue
            if not self._is_tech_allowed(node_id, allowed_tech_ids):
                continue
            visited.add(node_id)
            max_depth = max(max_depth, depth)
            tech = self.all_technologies.get(node_id)
            if not tech:
                continue
            for cid in self._get_sorted_children(tech, allowed_tech_ids):
                if cid not in visited:
                    stack.append((cid, depth + 1))
        return max_depth

    def _compute_max_degree_except_root(
        self, root_id: str, allowed_tech_ids: set[str] | None = None
    ) -> int:
        max_degree = 0
        for tid, tech in self.all_technologies.items():
            if tid == root_id:
                continue
            if not self._is_tech_allowed(tid, allowed_tech_ids):
                continue
            max_degree = max(
                max_degree, len(self._get_sorted_children(tech, allowed_tech_ids))
            )
        return max(max_degree, 1)

    def _visit_count_for_limits(
        self,
        root_id: str,
        max_depth: int,
        max_children: int,
        max_nodes: int,
        allowed_tech_ids: set[str] | None = None,
    ) -> int:
        if root_id not in self.all_technologies:
            return 0
        visited: set[str] = set()

        def dfs(node_id: str, depth: int, is_root: bool):
            if max_depth > 0 and depth > max_depth:
                return
            if not self._is_tech_allowed(node_id, allowed_tech_ids):
                return
            tech = self.all_technologies.get(node_id)
            if not tech:
                return
            children = self._get_sorted_children(tech, allowed_tech_ids)
            if not is_root and max_children > 0 and len(children) > max_children:
                children = children[:max_children]
            for cid in children:
                if cid not in visited:
                    visited.add(cid)
                    if max_nodes > 0 and len(visited) > max_nodes:
                        return
                    dfs(cid, depth + 1, False)

        dfs(root_id, 0, True)
        return len(visited)

    def _choose_best_xy_for_root(
        self, root_id: str, allowed_tech_ids: set[str] | None = None
    ) -> tuple[int, int, int] | None:
        if root_id not in self.all_technologies:
            return None
        root = self.all_technologies[root_id]
        max_nodes = self.display_config.max_display_nodes
        root_children_count = len(self._get_sorted_children(root, allowed_tech_ids))
        if max_nodes > 0 and root_children_count > max_nodes:
            return None
        max_tree_depth = self.display_config.max_tree_depth
        depth_upper_bound = (
            max_tree_depth
            if max_tree_depth > 0
            else self._compute_actual_max_depth(root_id, allowed_tech_ids)
        )
        if depth_upper_bound <= 0:
            depth_upper_bound = 1
        children_upper_bound_config = self.display_config.max_children_per_node
        if children_upper_bound_config > 0:
            children_upper_bound = children_upper_bound_config
        else:
            children_upper_bound = self._compute_max_degree_except_root(
                root_id, allowed_tech_ids
            )
        best_depth = 0
        best_children = 0
        best_node_count = -1
        for max_depth in range(depth_upper_bound, 0, -1):
            if max_nodes > 0 and best_node_count == max_nodes:
                break
            low, high = 1, children_upper_bound
            feasible_children = None
            feasible_count = -1
            if children_upper_bound == 1:
                size = self._visit_count_for_limits(
                    root_id, max_depth, 1, max_nodes, allowed_tech_ids
                )
                if max_nodes == 0 or size <= max_nodes:
                    feasible_children = 1
                    feasible_count = size
            else:
                while low <= high:
                    mid = (low + high) // 2
                    size = self._visit_count_for_limits(
                        root_id,
                        max_depth,
                        mid,
                        max_nodes,
                        allowed_tech_ids,
                    )
                    if max_nodes == 0:
                        feasible_children = mid
                        feasible_count = size
                        low = mid + 1
                    else:
                        if size > max_nodes:
                            high = mid - 1
                        else:
                            feasible_children = mid
                            feasible_count = size
                            low = mid + 1
            if feasible_children is not None:
                if (
                    feasible_count > best_node_count
                    or (feasible_count == best_node_count and max_depth > best_depth)
                    or (
                        feasible_count == best_node_count
                        and max_depth == best_depth
                        and feasible_children > best_children
                    )
                ):
                    best_depth, best_children, best_node_count = (
                        max_depth,
                        feasible_children,
                        feasible_count,
                    )
        if best_node_count < 0:
            return None
        return best_depth, best_children, best_node_count

    def _count_remaining_unique(
        self,
        start_nodes: list[str],
        root_id: str,
        max_depth: int,
        max_children: int,
        current_depth: int,
        visited_global: set[str],
        allowed_tech_ids: set[str] | None = None,
    ) -> int:
        if not start_nodes:
            return 0
        stack = []
        for n in start_nodes:
            stack.append((n, current_depth + 1))
        local_seen: set[str] = set()
        while stack:
            node_id, depth = stack.pop()
            if not self._is_tech_allowed(node_id, allowed_tech_ids):
                continue
            if node_id in visited_global or node_id in local_seen:
                continue
            local_seen.add(node_id)
            if depth >= max_depth:
                continue
            tech = self.all_technologies.get(node_id)
            if not tech:
                continue
            children = self._get_sorted_children(tech, allowed_tech_ids)
            if depth > 0 and max_children > 0:
                if node_id != root_id and len(children) > max_children:
                    children = children[:max_children]
            for cid in children:
                stack.append((cid, depth + 1))
        return len(local_seen)

    def _create_render_context(
        self,
        root_id: str,
        max_depth: int,
        max_children: int,
        max_nodes: int,
        lang_code: str,
        display_overrides: dict[str, str] | None = None,
        allowed_tech_ids: set[str] | None = None,
        suppress_overflow_line: bool = False,
    ) -> RenderContext:
        strings = self.localization_strings.get(
            lang_code, self.localization_strings["english"]
        )
        return RenderContext(
            root_id=root_id,
            max_depth=max_depth,
            max_children=max_children,
            max_nodes=max_nodes,
            lang_code=lang_code,
            display_overrides=display_overrides,
            allowed_tech_ids=allowed_tech_ids,
            suppress_overflow_line=suppress_overflow_line,
            already_shown_text=strings.get("already_shown", "already shown"),
            folded_more_tpl=strings.get("folded_more", "({count} more)"),
            global_overflow_tpl=strings.get(
                "global_overflow_reached", "(and {count} more)"
            ),
        )

    def _get_sorted_children(
        self, tech: Technology, allowed_tech_ids: set[str] | None = None
    ) -> list[str]:
        children = [
            cid
            for cid in tech.unlocked_tech_ids
            if self._is_tech_allowed(cid, allowed_tech_ids)
        ]
        return sorted(
            children,
            key=lambda cid: (
                self.all_technologies.get(cid, Technology(cid)).tier_level,
                cid,
            ),
        )

    def _apply_children_limit(
        self, children: list[str], is_root: bool, max_children: int
    ) -> tuple[list[str], bool]:
        if (not is_root) and max_children > 0 and len(children) > max_children:
            return children[:max_children], True
        return children, False

    def _check_node_overflow(
        self,
        ctx: RenderContext,
        state: RenderState,
        display_children: list[str],
        idx: int,
        parent_depth: int,
        prefix_bars: list[bool],
    ) -> bool:
        if ctx.max_nodes > 0 and len(state.visited_unique) >= ctx.max_nodes:
            remaining_nodes = display_children[idx:]
            more = self._count_remaining_unique(
                remaining_nodes,
                ctx.root_id,
                ctx.max_depth,
                ctx.max_children,
                parent_depth,
                state.visited_unique,
                ctx.allowed_tech_ids,
            )
            state.overflow = True
            if not ctx.suppress_overflow_line:
                prefix_parts = [
                    self.TREE_BAR if keep else self.TREE_EMPTY for keep in prefix_bars
                ]
                state.lines.append(
                    "".join(prefix_parts)
                    + self.TREE_BRANCH
                    + self.ELLIPSIS
                    + ctx.global_overflow_tpl.format(count=more)
                )
            return True
        return False

    def _render_single_child(
        self,
        ctx: RenderContext,
        state: RenderState,
        parent_id: str,
        child_id: str,
        parent_depth: int,
        prefix_bars: list[bool],
        has_more_siblings: bool,
    ) -> None:
        line = self._format_tech_tree_entry(
            child_id,
            prefix_bars + [has_more_siblings],
            parent_id,
            ctx.lang_code,
            display_overrides=ctx.display_overrides,
            allowed_tech_ids=ctx.allowed_tech_ids,
        )
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
                self._render_children(
                    ctx,
                    state,
                    child_id,
                    self._get_sorted_children(child_tech, ctx.allowed_tech_ids),
                    parent_depth + 1,
                    False,
                    prefix_bars + [has_more_siblings],
                )

    def _append_truncation_message(
        self,
        ctx: RenderContext,
        state: RenderState,
        hidden: int,
        prefix_bars: list[bool],
    ) -> None:
        if hidden <= 0:
            return
        prefix_parts = [
            self.TREE_BAR if keep else self.TREE_EMPTY for keep in prefix_bars
        ]
        state.lines.append(
            "".join(prefix_parts)
            + self.TREE_BRANCH
            + self.ELLIPSIS
            + ctx.folded_more_tpl.format(count=hidden)
        )

    def _render_children(
        self,
        ctx: RenderContext,
        state: RenderState,
        parent_id: str,
        children: list[str],
        parent_depth: int,
        is_root: bool,
        prefix_bars: list[bool],
    ) -> None:
        if state.overflow:
            return
        if parent_depth >= ctx.max_depth:
            return
        display_children, truncated = self._apply_children_limit(
            children, is_root, ctx.max_children
        )
        for idx, cid in enumerate(display_children):
            if state.overflow:
                break
            if self._check_node_overflow(
                ctx, state, display_children, idx, parent_depth, prefix_bars
            ):
                break
            has_more_siblings = (idx < len(display_children) - 1) or (
                truncated and not state.overflow
            )
            self._render_single_child(
                ctx, state, parent_id, cid, parent_depth, prefix_bars, has_more_siblings
            )
        if not state.overflow and truncated:
            hidden = len(children) - len(display_children)
            self._append_truncation_message(ctx, state, hidden, prefix_bars)

    def _render_tree_with_limits(
        self,
        root_id: str,
        max_depth: int,
        max_children: int,
        max_nodes: int,
        lang_code: str,
        display_overrides: dict[str, str] | None = None,
        allowed_tech_ids: set[str] | None = None,
        suppress_overflow_line: bool = False,
    ) -> tuple[list[str], bool]:
        if root_id not in self.all_technologies:
            return [], False
        ctx = self._create_render_context(
            root_id,
            max_depth,
            max_children,
            max_nodes,
            lang_code,
            display_overrides,
            allowed_tech_ids,
            suppress_overflow_line,
        )
        state = RenderState()
        root = self.all_technologies[root_id]
        root_children = self._get_sorted_children(root, allowed_tech_ids)
        self._render_children(
            ctx,
            state,
            root_id,
            root_children,
            parent_depth=0,
            is_root=True,
            prefix_bars=[],
        )
        return state.lines, state.overflow

    def _check_root_overflow(
        self,
        tech_id: str,
        max_nodes: int,
        allowed_tech_ids: set[str] | None = None,
    ) -> bool:
        root = self.all_technologies[tech_id]
        root_children_count = len(self._get_sorted_children(root, allowed_tech_ids))
        if max_nodes > 0 and root_children_count > max_nodes:
            if self.overlong_tech_ids is not None:
                self.overlong_tech_ids.add(tech_id)
            return True
        return False

    def _format_root_overflow_message(self, header: str, lang_code: str) -> str:
        strings = self.localization_strings.get(
            lang_code, self.localization_strings["english"]
        )
        msg = strings.get("root_children_exceed_limit", "Root children exceed limit")
        content = f"{header}\n{self.TREE_BRANCH}§R{msg}§!"
        return content.replace("\n", "\\n")

    def _get_raw_render_params(
        self, tech_id: str, allowed_tech_ids: set[str] | None = None
    ) -> tuple[int, int]:
        max_tree_depth = self.display_config.max_tree_depth
        raw_depth = (
            max_tree_depth
            if max_tree_depth > 0
            else self._compute_actual_max_depth(tech_id, allowed_tech_ids)
        )
        if raw_depth <= 0:
            raw_depth = 1
        raw_children = self.display_config.max_children_per_node
        return raw_depth, raw_children

    def _finalize_tree_content(
        self,
        header: str,
        tech_id: str,
        max_depth: int,
        max_children: int,
        max_nodes: int,
        lang_code: str,
        display_overrides: dict[str, str] | None = None,
        allowed_tech_ids: set[str] | None = None,
    ) -> str:
        lines_stage_final, _ = self._render_tree_with_limits(
            tech_id,
            max_depth,
            max_children,
            max_nodes,
            lang_code,
            display_overrides=display_overrides,
            allowed_tech_ids=allowed_tech_ids,
            suppress_overflow_line=False,
        )
        if not lines_stage_final:
            content = f"{header}\n§Y$tech_tree_max_level$§!"
        else:
            content = header + "\n" + "\n".join(lines_stage_final)
        return content.replace("\n", "\\n")

    def _render_with_optimized_params(
        self,
        header: str,
        tech_id: str,
        max_nodes: int,
        lang_code: str,
        display_overrides: dict[str, str] | None = None,
        allowed_tech_ids: set[str] | None = None,
    ) -> str:
        chosen = self._choose_best_xy_for_root(tech_id, allowed_tech_ids)
        if chosen is None:
            return self._format_root_overflow_message(header, lang_code)
        best_depth, best_children, _ = chosen
        return self._finalize_tree_content(
            header,
            tech_id,
            best_depth,
            best_children,
            max_nodes,
            lang_code,
            display_overrides,
            allowed_tech_ids,
        )

    def generate_tech_tree_content(
        self,
        tech_id: str,
        lang_code: str = "simp_chinese",
        display_overrides: dict[str, str] | None = None,
        allowed_tech_ids: set[str] | None = None,
    ) -> str:
        if tech_id not in self.all_technologies:
            return ""
        header = "\\n\\n§H$technology_tree_title$§!"
        max_nodes = self.display_config.max_display_nodes
        if self._check_root_overflow(tech_id, max_nodes, allowed_tech_ids):
            return self._format_root_overflow_message(header, lang_code)

        raw_depth, raw_children = self._get_raw_render_params(tech_id, allowed_tech_ids)
        _, overflow_stage_probe = self._render_tree_with_limits(
            tech_id,
            raw_depth,
            raw_children,
            max_nodes,
            lang_code,
            display_overrides=display_overrides,
            allowed_tech_ids=allowed_tech_ids,
            suppress_overflow_line=True,
        )
        if not overflow_stage_probe or max_nodes == 0:
            return self._finalize_tree_content(
                header,
                tech_id,
                raw_depth,
                raw_children,
                max_nodes,
                lang_code,
                display_overrides,
                allowed_tech_ids,
            )

        return self._render_with_optimized_params(
            header,
            tech_id,
            max_nodes,
            lang_code,
            display_overrides,
            allowed_tech_ids,
        )
