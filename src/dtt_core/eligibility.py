"""Strict save-profile eligibility filtering for technology trees.

Potential evaluation targets a single empire profile (typically save-derived).
Unknown potential results are treated as excluded and reported explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from config import (
    DEFAULT_ELIGIBILITY_SAMPLE_SIZE,
    DEFAULT_ELIGIBILITY_UNKNOWN_WARNING_THRESHOLD,
)
from dtt_core.tech_merge import MergedTechDefinition
from dtt_core.trigger_evaluator import (
    EmpireProfile,
    TriggerEvaluationResult,
    TriggerEvaluator,
)
from models import Technology


@dataclass(frozen=True)
class FalseExclusionDetail:
    reason: str
    reason_trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnknownExclusionDetail:
    unknown_predicates: tuple[str, ...]
    reason_trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class PrerequisiteExclusionDetail:
    missing_prereq_ids: tuple[str, ...]


@dataclass(frozen=True)
class UnknownPredicateFrequency:
    count: int
    example_tech_ids: tuple[str, ...]


@dataclass(frozen=True)
class UnknownExclusionExample:
    tech_id: str
    unknown_predicates: tuple[str, ...]
    reason_trace: tuple[str, ...]


@dataclass(frozen=True)
class PrerequisiteExclusionExample:
    tech_id: str
    missing_prereq_ids: tuple[str, ...]


@dataclass
class EligibilityReport:
    sample_size: int = DEFAULT_ELIGIBILITY_SAMPLE_SIZE
    excluded_by_false: dict[str, FalseExclusionDetail] = field(default_factory=dict)
    excluded_by_unknown: dict[str, UnknownExclusionDetail] = field(default_factory=dict)
    excluded_by_prereq: dict[str, PrerequisiteExclusionDetail] = field(
        default_factory=dict
    )
    unknown_predicate_frequency: dict[str, UnknownPredicateFrequency] = field(
        default_factory=dict
    )
    warning: str | None = None

    @property
    def excluded_by_false_count(self) -> int:
        return len(self.excluded_by_false)

    @property
    def excluded_by_unknown_count(self) -> int:
        return len(self.excluded_by_unknown)

    @property
    def excluded_by_prereq_count(self) -> int:
        return len(self.excluded_by_prereq)

    @property
    def excluded_by_unknown_examples(self) -> tuple[UnknownExclusionExample, ...]:
        return tuple(
            UnknownExclusionExample(
                tech_id=tech_id,
                unknown_predicates=self.excluded_by_unknown[tech_id].unknown_predicates,
                reason_trace=self.excluded_by_unknown[tech_id].reason_trace,
            )
            for tech_id in self._sample_keys(self.excluded_by_unknown)
        )

    @property
    def excluded_by_prereq_examples(self) -> tuple[PrerequisiteExclusionExample, ...]:
        return tuple(
            PrerequisiteExclusionExample(
                tech_id=tech_id,
                missing_prereq_ids=self.excluded_by_prereq[tech_id].missing_prereq_ids,
            )
            for tech_id in self._sample_keys(self.excluded_by_prereq)
        )

    def _sample_keys(self, mapping: Mapping[str, object]) -> list[str]:
        if self.sample_size <= 0:
            return []
        return sorted(mapping)[: self.sample_size]


def _pick_reason(result: TriggerEvaluationResult, fallback: str) -> str:
    if result.reason_trace:
        return result.reason_trace[-1]
    return fallback


def _sorted_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if value}))


def _apply_prerequisite_closure(
    all_technologies: Mapping[str, Technology],
    allowed_ids: set[str],
    excluded_by_prereq: dict[str, PrerequisiteExclusionDetail],
) -> set[str]:
    closed_allowed_ids = set(allowed_ids)
    while True:
        removals: list[tuple[str, tuple[str, ...]]] = []
        for tech_id in sorted(closed_allowed_ids):
            tech = all_technologies.get(tech_id)
            if tech is None:
                continue

            missing_prereqs = _sorted_unique(
                prereq_id
                for prereq_id in tech.prerequisite_tech_ids
                if prereq_id not in closed_allowed_ids
            )
            if missing_prereqs:
                removals.append((tech_id, missing_prereqs))

        if not removals:
            return closed_allowed_ids

        for tech_id, missing_prereqs in removals:
            closed_allowed_ids.remove(tech_id)
            excluded_by_prereq[tech_id] = PrerequisiteExclusionDetail(
                missing_prereq_ids=missing_prereqs
            )


def _build_unknown_predicate_frequency(
    unknown_predicates_by_tech_id: Mapping[str, UnknownExclusionDetail],
    *,
    sample_size: int,
) -> dict[str, UnknownPredicateFrequency]:
    unknown_to_tech_ids: dict[str, set[str]] = {}
    for tech_id in sorted(unknown_predicates_by_tech_id):
        unknown_predicates = unknown_predicates_by_tech_id[tech_id].unknown_predicates
        for predicate in unknown_predicates:
            unknown_to_tech_ids.setdefault(predicate, set()).add(tech_id)

    frequency: dict[str, UnknownPredicateFrequency] = {}
    for predicate in sorted(unknown_to_tech_ids):
        tech_ids = sorted(unknown_to_tech_ids[predicate])
        frequency[predicate] = UnknownPredicateFrequency(
            count=len(tech_ids),
            example_tech_ids=tuple(tech_ids[:sample_size]),
        )
    return frequency


def build_allowed_tech_ids_for_empire(
    all_technologies: Mapping[str, Technology],
    profile: EmpireProfile,
    merged_tech_definitions: Mapping[str, MergedTechDefinition] | None = None,
    *,
    evaluator: TriggerEvaluator | None = None,
    sample_size: int = DEFAULT_ELIGIBILITY_SAMPLE_SIZE,
    unknown_warning_threshold: int = DEFAULT_ELIGIBILITY_UNKNOWN_WARNING_THRESHOLD,
) -> tuple[set[str], EligibilityReport]:
    normalized_sample_size = max(sample_size, 0)
    merged_lookup = merged_tech_definitions or {}
    trigger_evaluator = evaluator if evaluator is not None else TriggerEvaluator()

    report = EligibilityReport(sample_size=normalized_sample_size)
    allowed_ids: set[str] = set()

    for tech_id in sorted(all_technologies):
        merged = merged_lookup.get(tech_id)
        potential = merged.potential if merged is not None else None
        result = trigger_evaluator.evaluate_potential(potential, profile)

        if result.value is True:
            allowed_ids.add(tech_id)
            continue

        if result.value is False:
            report.excluded_by_false[tech_id] = FalseExclusionDetail(
                reason=_pick_reason(result, "potential resolved to false"),
                reason_trace=tuple(result.reason_trace),
            )
            continue

        reason_trace = (
            tuple(result.reason_trace)
            if result.reason_trace
            else ("potential resolved to unknown",)
        )
        report.excluded_by_unknown[tech_id] = UnknownExclusionDetail(
            unknown_predicates=_sorted_unique(result.unknown_predicates),
            reason_trace=reason_trace,
        )

    allowed_ids = _apply_prerequisite_closure(
        all_technologies,
        allowed_ids,
        report.excluded_by_prereq,
    )

    report.unknown_predicate_frequency = _build_unknown_predicate_frequency(
        report.excluded_by_unknown,
        sample_size=normalized_sample_size,
    )

    if (
        unknown_warning_threshold > 0
        and report.excluded_by_unknown_count >= unknown_warning_threshold
    ):
        report.warning = (
            "Potential evaluation excluded "
            f"{report.excluded_by_unknown_count} technologies as unknown; "
            "review unknown_predicate_frequency for unsupported predicates."
        )

    return allowed_ids, report
