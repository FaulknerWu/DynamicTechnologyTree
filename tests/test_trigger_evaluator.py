# pyright: reportMissingImports=false

from __future__ import annotations

import pytest

from dtt_core.clausewitz_parser import Assignment, Block, parse
from dtt_core.trigger_evaluator import (
    SUPPORTED_MEMBERSHIP_PREDICATES,
    EmpireProfile,
    TriggerEvaluator,
)

_MEMBERSHIP_CASES = (
    (
        "has_origin",
        "origin_prosperous_unification",
        "origin_void_dwellers",
    ),
    (
        "has_ascension_perk",
        "ap_engineered_evolution",
        "ap_mind_over_matter",
    ),
    (
        "has_ethic",
        "ethic_fanatic_materialist",
        "ethic_fanatic_spiritualist",
    ),
    ("has_civic", "civic_meritocracy", "civic_technocracy"),
    ("has_authority", "auth_democratic", "auth_imperial"),
    ("has_country_flag", "dtt_story_flag", "dtt_other_flag"),
    ("has_dlc", "utopia", "federations"),
)


def test_membership_cases_cover_supported_predicates() -> None:
    assert {predicate for predicate, _, _ in _MEMBERSHIP_CASES} == (
        SUPPORTED_MEMBERSHIP_PREDICATES
    )


def _parse_potential_block(block_body: str) -> Block:
    parsed = parse(f"""
potential = {{
{block_body}
}}
""")
    assert parsed.diagnostics == []

    assignments = [item for item in parsed.root.items if isinstance(item, Assignment)]
    assert len(assignments) == 1

    potential = assignments[0]
    assert potential.key.value == "potential"
    assert isinstance(potential.value, Block)
    return potential.value


def test_auto_contexts_cover_expected_polities() -> None:
    contexts = EmpireProfile.auto_contexts()
    assert set(contexts) == {"regular", "corporate", "hive", "machine"}


def test_machine_only_tech_excluded_in_regular_context() -> None:
    evaluator = TriggerEvaluator()
    potential = _parse_potential_block("is_machine_empire = yes")

    result = evaluator.evaluate_potential(potential, EmpireProfile.auto("regular"))

    assert result.value is False
    assert result.error is None
    assert any("is_machine_empire" in reason for reason in result.reason_trace)


def test_regular_only_tech_excluded_in_machine_context() -> None:
    evaluator = TriggerEvaluator()
    potential = _parse_potential_block("is_regular_empire = yes")

    result = evaluator.evaluate_potential(potential, EmpireProfile.auto("machine"))

    assert result.value is False
    assert result.error is None
    assert any("is_regular_empire" in reason for reason in result.reason_trace)


def test_unknown_predicates_differ_between_auto_and_profile_modes() -> None:
    evaluator = TriggerEvaluator()
    potential = _parse_potential_block("future_polity_gate = yes")

    auto_result = evaluator.evaluate_potential(
        potential, EmpireProfile.auto("corporate")
    )
    assert auto_result.value is None
    assert auto_result.error is None
    assert auto_result.unknown_predicates == ("future_polity_gate",)

    profile = EmpireProfile.profile(
        {
            "is_gestalt": False,
            "is_machine_empire": False,
            "is_hive_empire": False,
            "is_regular_empire": True,
            "is_individual_machine": False,
        },
        name="custom_regular",
    )
    profile_result = evaluator.evaluate_potential(potential, profile)
    assert profile_result.value is None
    assert profile_result.error is not None
    assert "future_polity_gate" in profile_result.error


def test_not_propagates_unknown() -> None:
    evaluator = TriggerEvaluator()
    potential = _parse_potential_block("""
NOT = {
  unknown_gate = yes
}
""")

    result = evaluator.evaluate_potential(potential, EmpireProfile.auto("regular"))

    assert result.value is None
    assert result.error is None
    assert result.unknown_predicates == ("unknown_gate",)
    assert any("NOT" in reason for reason in result.reason_trace)


def test_nor_propagates_unknown() -> None:
    evaluator = TriggerEvaluator()
    potential = _parse_potential_block("""
NOR = {
  unknown_gate = yes
}
""")

    result = evaluator.evaluate_potential(potential, EmpireProfile.auto("regular"))

    assert result.value is None
    assert result.error is None
    assert result.unknown_predicates == ("unknown_gate",)
    assert any("NOR" in reason for reason in result.reason_trace)


@pytest.mark.parametrize(
    ("predicate", "present_token", "absent_token"),
    _MEMBERSHIP_CASES,
)
def test_membership_predicates_true_false_unknown(
    predicate: str,
    present_token: str,
    absent_token: str,
) -> None:
    evaluator = TriggerEvaluator()
    profile_with_membership = EmpireProfile.profile(
        {},
        name="save_like_profile",
        memberships={predicate: [present_token]},
    )

    true_result = evaluator.evaluate_potential(
        _parse_potential_block(f"{predicate} = {present_token}"),
        profile_with_membership,
    )
    assert true_result.value is True
    assert true_result.error is None
    assert true_result.unknown_predicates == ()

    false_result = evaluator.evaluate_potential(
        _parse_potential_block(f"{predicate} = {absent_token}"),
        profile_with_membership,
    )
    assert false_result.value is False
    assert false_result.error is None
    assert false_result.unknown_predicates == ()
    assert any(predicate in reason for reason in false_result.reason_trace)

    unknown_result = evaluator.evaluate_potential(
        _parse_potential_block(f"{predicate} = {present_token}"),
        EmpireProfile.auto("regular"),
    )
    assert unknown_result.value is None
    assert unknown_result.error is None
    assert unknown_result.unknown_predicates == (predicate,)
    assert any(predicate in reason for reason in unknown_result.reason_trace)


@pytest.mark.parametrize(("predicate", "present_token", "_"), _MEMBERSHIP_CASES)
def test_membership_predicates_require_atom_values(
    predicate: str,
    present_token: str,
    _: str,
) -> None:
    evaluator = TriggerEvaluator()
    result = evaluator.evaluate_potential(
        _parse_potential_block(f"""
{predicate} = {{
  always = yes
}}
"""),
        EmpireProfile.profile(
            {},
            name="save_like_profile",
            memberships={predicate: [present_token]},
        ),
    )

    assert result.value is None
    assert result.error is not None
    assert result.unknown_predicates == (predicate,)
    assert any("expects an atom value" in reason for reason in result.reason_trace)


@pytest.mark.parametrize(("predicate", "present_token", "_"), _MEMBERSHIP_CASES)
def test_membership_predicates_support_query_and_negation_operators(
    predicate: str,
    present_token: str,
    _: str,
) -> None:
    evaluator = TriggerEvaluator()
    profile_with_membership = EmpireProfile.profile(
        {},
        name="save_like_profile",
        memberships={predicate: [present_token]},
    )

    query_result = evaluator.evaluate_potential(
        _parse_potential_block(f"{predicate} ?= {present_token}"),
        profile_with_membership,
    )
    assert query_result.value is True
    assert query_result.error is None

    negation_result = evaluator.evaluate_potential(
        _parse_potential_block(f"{predicate} != {present_token}"),
        profile_with_membership,
    )
    assert negation_result.value is False
    assert negation_result.error is None
    assert any(predicate in reason for reason in negation_result.reason_trace)


def test_membership_predicate_unsupported_operator_is_unknown() -> None:
    evaluator = TriggerEvaluator()
    result = evaluator.evaluate_potential(
        _parse_potential_block("has_dlc > utopia"),
        EmpireProfile.auto("regular"),
    )

    assert result.value is None
    assert result.error is None
    assert result.unknown_predicates == ("has_dlc",)
    assert any("unsupported operator" in reason for reason in result.reason_trace)
