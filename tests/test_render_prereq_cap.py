# pyright: reportMissingImports=false

from __future__ import annotations

from dtt_core.render import TreeRenderer
from dtt_core.settings_snapshot import require_settings_snapshot
from models import Technology
from settings import Settings


def _build_prereq_cap_graph() -> dict[str, Technology]:
    root = Technology("tech_root", research_area="physics", tier_level=1)
    prereq_a = Technology("tech_prereq_a", research_area="physics", tier_level=1)
    prereq_b = Technology("tech_prereq_b", research_area="physics", tier_level=1)
    prereq_c = Technology("tech_prereq_c", research_area="physics", tier_level=1)
    prereq_d = Technology("tech_prereq_d", research_area="physics", tier_level=1)
    target = Technology(
        "tech_target",
        research_area="engineering",
        tier_level=2,
        prerequisite_tech_ids=[
            root.tech_id,
            prereq_a.tech_id,
            prereq_b.tech_id,
            prereq_c.tech_id,
            prereq_d.tech_id,
        ],
    )
    root.unlocked_tech_ids = [target.tech_id]

    return {
        root.tech_id: root,
        prereq_a.tech_id: prereq_a,
        prereq_b.tech_id: prereq_b,
        prereq_c.tech_id: prereq_c,
        prereq_d.tech_id: prereq_d,
        target.tech_id: target,
    }


def _extract_requires_segment(content: str) -> str:
    token = "[§RRequires§! "
    after_marker = content.split(token, 1)[1]
    return after_marker.rsplit("]", 1)[0]


def test_render_prereq_cap_custom_shows_more_items_before_ellipsis() -> None:
    techs = _build_prereq_cap_graph()

    default_settings = Settings()
    default_config = require_settings_snapshot(default_settings).generator_config
    default_renderer = TreeRenderer(
        all_technologies=techs,
        display_config=default_config.display,
    )
    default_content = default_renderer.generate_tech_tree_content(
        "tech_root", "english"
    )

    custom_settings = Settings()
    custom_settings.display.max_prereq_display = 3
    custom_config = require_settings_snapshot(custom_settings).generator_config
    custom_renderer = TreeRenderer(
        all_technologies=techs,
        display_config=custom_config.display,
    )
    custom_content = custom_renderer.generate_tech_tree_content("tech_root", "english")

    default_requires = _extract_requires_segment(default_content)
    custom_requires = _extract_requires_segment(custom_content)

    assert "$tech_prereq_a$" in default_requires
    assert "$tech_prereq_b$" in default_requires
    assert "$tech_prereq_c$" not in default_requires
    assert default_requires.endswith(TreeRenderer.ELLIPSIS)

    assert "$tech_prereq_c$" in custom_requires
    assert "$tech_prereq_d$" not in custom_requires
    assert custom_requires.endswith(TreeRenderer.ELLIPSIS)
