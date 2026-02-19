# pyright: reportMissingImports=false

from __future__ import annotations

from config import DisplayConfig
from dtt_core.clausewitz_parser import Assignment, Block, parse
from dtt_core.eligibility import EligibilityReport, build_allowed_tech_ids_for_empire
from dtt_core.render import TreeRenderer
from dtt_core.save_context import SaveEmpireFacts
from dtt_core.tech_merge import MergedTechDefinition
from dtt_core.trigger_evaluator import EmpireProfile
from models import Technology


def _parse_potential_block(block_body: str) -> Block:
    parsed = parse(
        f"""
potential = {{
{block_body}
}}
"""
    )
    assert parsed.diagnostics == []
    assignments = [item for item in parsed.root.items if isinstance(item, Assignment)]
    assert len(assignments) == 1
    potential = assignments[0]
    assert isinstance(potential.value, Block)
    return potential.value


def _build_profile() -> EmpireProfile:
    return EmpireProfile.from_save_empire_facts(
        SaveEmpireFacts(
            country_id=1,
            country_name="Deterministic Research Union",
            is_gestalt=False,
            is_machine_empire=False,
            is_hive_empire=False,
            is_regular_empire=True,
            is_individual_machine=False,
            authority="auth_democratic",
        )
    )


def _build_techs() -> dict[str, Technology]:
    root = Technology("tech_root", research_area="physics", tier_level=1)
    allowed = Technology(
        "tech_allowed",
        research_area="physics",
        tier_level=2,
        prerequisite_tech_ids=["tech_root"],
    )
    false_gate = Technology(
        "tech_false_gate",
        research_area="engineering",
        tier_level=2,
        prerequisite_tech_ids=["tech_root"],
    )
    unknown_alpha = Technology(
        "tech_unknown_alpha",
        research_area="society",
        tier_level=2,
        prerequisite_tech_ids=["tech_root"],
    )
    unknown_zeta = Technology(
        "tech_unknown_zeta",
        research_area="society",
        tier_level=2,
        prerequisite_tech_ids=["tech_root"],
    )
    dual_prereq = Technology(
        "tech_dual_prereq",
        research_area="engineering",
        tier_level=3,
        prerequisite_tech_ids=["tech_allowed", "tech_false_gate"],
    )

    root.unlocked_tech_ids = [
        "tech_allowed",
        "tech_false_gate",
        "tech_unknown_alpha",
        "tech_unknown_zeta",
    ]
    allowed.unlocked_tech_ids = ["tech_dual_prereq"]
    false_gate.unlocked_tech_ids = ["tech_dual_prereq"]

    return {
        root.tech_id: root,
        allowed.tech_id: allowed,
        false_gate.tech_id: false_gate,
        unknown_alpha.tech_id: unknown_alpha,
        unknown_zeta.tech_id: unknown_zeta,
        dual_prereq.tech_id: dual_prereq,
    }


def _build_merged_defs() -> dict[str, MergedTechDefinition]:
    return {
        "tech_false_gate": MergedTechDefinition(
            tech_id="tech_false_gate",
            potential=_parse_potential_block("is_machine_empire = yes"),
        ),
        "tech_unknown_alpha": MergedTechDefinition(
            tech_id="tech_unknown_alpha",
            potential=_parse_potential_block("alpha_gate = yes"),
        ),
        "tech_unknown_zeta": MergedTechDefinition(
            tech_id="tech_unknown_zeta",
            potential=_parse_potential_block("zeta_gate = yes"),
        ),
    }


def _evaluate() -> tuple[dict[str, Technology], set[str], EligibilityReport]:
    techs = _build_techs()
    allowed_tech_ids, report = build_allowed_tech_ids_for_empire(
        techs,
        _build_profile(),
        _build_merged_defs(),
        unknown_warning_threshold=2,
    )
    return techs, allowed_tech_ids, report


def test_unknown_exclusion_is_strict_and_reported_deterministically() -> None:
    _, allowed_tech_ids, report = _evaluate()

    assert "tech_unknown_alpha" not in allowed_tech_ids
    assert "tech_unknown_zeta" not in allowed_tech_ids
    assert report.excluded_by_unknown_count == 2
    assert report.warning is not None

    unknown_examples = report.excluded_by_unknown_examples
    assert [example.tech_id for example in unknown_examples] == [
        "tech_unknown_alpha",
        "tech_unknown_zeta",
    ]
    assert unknown_examples[0].unknown_predicates == ("alpha_gate",)
    assert unknown_examples[1].unknown_predicates == ("zeta_gate",)

    assert list(report.unknown_predicate_frequency) == ["alpha_gate", "zeta_gate"]
    assert report.unknown_predicate_frequency["alpha_gate"].count == 1
    assert report.unknown_predicate_frequency["alpha_gate"].example_tech_ids == (
        "tech_unknown_alpha",
    )


def test_prerequisite_closure_excludes_when_any_prereq_is_missing() -> None:
    _, allowed_tech_ids, report = _evaluate()

    assert "tech_false_gate" not in allowed_tech_ids
    assert "tech_dual_prereq" not in allowed_tech_ids
    assert report.excluded_by_prereq_count == 1
    assert "tech_dual_prereq" in report.excluded_by_prereq
    assert report.excluded_by_prereq["tech_dual_prereq"].missing_prereq_ids == (
        "tech_false_gate",
    )
    assert report.excluded_by_prereq_examples[0].tech_id == "tech_dual_prereq"


def test_renderer_never_emits_excluded_tech_ids() -> None:
    techs, allowed_tech_ids, report = _evaluate()

    renderer = TreeRenderer(
        all_technologies=techs,
        display_config=DisplayConfig(
            max_children_per_node=12,
            max_tree_depth=5,
            max_display_nodes=128,
        ),
    )
    tree_content = renderer.generate_tech_tree_content(
        "tech_root",
        "english",
        allowed_tech_ids=allowed_tech_ids,
    )

    excluded_ids = (
        set(report.excluded_by_false)
        | set(report.excluded_by_unknown)
        | set(report.excluded_by_prereq)
    )
    for excluded_id in sorted(excluded_ids):
        assert excluded_id not in tree_content

    assert "tech_allowed" in tree_content
    assert "tech_false_gate" not in tree_content
    assert "tech_dual_prereq" not in tree_content
    assert "tech_unknown_alpha" not in tree_content
