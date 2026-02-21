# pyright: reportMissingImports=false

from __future__ import annotations

import pytest

from dtt_core.clausewitz_parser import Assignment, Block, parse
from dtt_core.swap_resolver import (
    SwapResolutionCollisionError,
    resolve_display_overrides_for_profile,
)
from dtt_core.tech_extractor import TechnologySwap
from dtt_core.tech_merge import MergedTechDefinition
from dtt_core.trigger_evaluator import EmpireProfile


def _parse_trigger_block(block_body: str) -> Block:
    parsed = parse(f"""
trigger = {{
{block_body}
}}
""")
    assert parsed.diagnostics == []

    assignments = [item for item in parsed.root.items if isinstance(item, Assignment)]
    assert len(assignments) == 1

    trigger_assignment = assignments[0]
    assert trigger_assignment.key.value == "trigger"
    assert isinstance(trigger_assignment.value, Block)
    return trigger_assignment.value


def _swap(name: str, trigger_body: str | None) -> TechnologySwap:
    return TechnologySwap(
        name=name,
        trigger=(
            _parse_trigger_block(trigger_body) if trigger_body is not None else None
        ),
    )


def test_first_true_swap_wins_in_source_order() -> None:
    merged_defs = {
        "tech_base": MergedTechDefinition(
            tech_id="tech_base",
            technology_swaps=[
                _swap("tech_variant_primary", None),
                _swap("tech_variant_secondary", "always = yes"),
            ],
        )
    }

    display_overrides, report = resolve_display_overrides_for_profile(
        merged_defs,
        EmpireProfile.auto("regular"),
    )

    assert display_overrides == {"tech_base": "tech_variant_primary"}
    assert list(report.chosen_swaps) == ["tech_base"]
    assert report.chosen_swaps["tech_base"].swap_name == "tech_variant_primary"
    assert report.chosen_swaps["tech_base"].swap_index == 0
    assert report.ambiguities == {}
    assert report.collisions == {}


def test_unknown_swap_stops_resolution_and_forces_base_fallback() -> None:
    merged_defs = {
        "tech_base": MergedTechDefinition(
            tech_id="tech_base",
            technology_swaps=[
                _swap("tech_variant_unknown", "future_swap_gate = yes"),
                _swap("tech_variant_later_true", "always = yes"),
            ],
        )
    }

    display_overrides, report = resolve_display_overrides_for_profile(
        merged_defs,
        EmpireProfile.auto("regular"),
    )

    assert display_overrides == {}
    assert report.chosen_swaps == {}
    assert list(report.ambiguities) == ["tech_base"]
    ambiguity = report.ambiguities["tech_base"]
    assert ambiguity.swap_index == 0
    assert ambiguity.unknown_predicates == ("future_swap_gate",)
    assert ambiguity.error is None
    assert any("future_swap_gate" in reason for reason in ambiguity.reason_trace)
    assert report.collisions == {}


def test_all_false_swaps_keep_base_display_id() -> None:
    merged_defs = {
        "tech_base": MergedTechDefinition(
            tech_id="tech_base",
            technology_swaps=[
                _swap("tech_variant_a", "always = no"),
                _swap("tech_variant_b", "is_machine_empire = yes"),
            ],
        )
    }

    display_overrides, report = resolve_display_overrides_for_profile(
        merged_defs,
        EmpireProfile.auto("regular"),
    )

    assert display_overrides == {}
    assert report.chosen_swaps == {}
    assert report.ambiguities == {}
    assert report.collisions == {}


def test_collision_raises_and_exposes_collision_details() -> None:
    merged_defs = {
        "tech_base_a": MergedTechDefinition(
            tech_id="tech_base_a",
            technology_swaps=[_swap("tech_shared_variant", "always = yes")],
        ),
        "tech_base_b": MergedTechDefinition(
            tech_id="tech_base_b",
            technology_swaps=[_swap("tech_shared_variant", "always = yes")],
        ),
    }

    with pytest.raises(SwapResolutionCollisionError) as exc:
        resolve_display_overrides_for_profile(
            merged_defs,
            EmpireProfile.auto("regular"),
        )

    assert exc.value.code == "technology_swap_collision"
    assert exc.value.details_dict()["collisions"] == (
        "tech_shared_variant: tech_base_a, tech_base_b"
    )
    assert "tech_shared_variant" in str(exc.value)
    assert "tech_base_a" in str(exc.value)
    assert "tech_base_b" in str(exc.value)

    report = exc.value.report
    assert list(report.collisions) == ["tech_shared_variant"]
    assert report.collisions["tech_shared_variant"].base_tech_ids == (
        "tech_base_a",
        "tech_base_b",
    )
    assert report.chosen_swaps["tech_base_a"].swap_name == "tech_shared_variant"
    assert report.chosen_swaps["tech_base_b"].swap_name == "tech_shared_variant"
