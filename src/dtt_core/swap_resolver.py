from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable, Mapping

from dtt_core.tech_extractor import TechnologySwap
from dtt_core.tech_merge import MergedTechDefinition
from dtt_core.trigger_evaluator import (
    EmpireProfile,
    TriggerEvaluationResult,
    TriggerEvaluator,
)
from dtt_core.eligibility import _sorted_unique
from dtt_core.typed_error import TypedCoreError


@dataclass(frozen=True)
class ChosenSwap:
    swap_name: str
    swap_index: int


@dataclass(frozen=True)
class SwapAmbiguity:
    swap_index: int
    unknown_predicates: tuple[str, ...] = ()
    reason_trace: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class SwapCollision:
    base_tech_ids: tuple[str, ...]


@dataclass
class SwapResolutionReport:
    chosen_swaps: dict[str, ChosenSwap] = field(default_factory=dict)
    ambiguities: dict[str, SwapAmbiguity] = field(default_factory=dict)
    collisions: dict[str, SwapCollision] = field(default_factory=dict)

    @property
    def has_collisions(self) -> bool:
        return bool(self.collisions)


class SwapResolutionCollisionError(TypedCoreError):
    def __init__(self, report: SwapResolutionReport) -> None:
        self.report = report
        details = "; ".join(
            f"{active_display_id}: {', '.join(collision.base_tech_ids)}"
            for active_display_id, collision in sorted(report.collisions.items())
        )
        suffix = details if details else "unknown collisions"
        super().__init__(
            code="technology_swap_collision",
            details=(
                ("collisions", suffix),
            ),
        )

    def __str__(self) -> str:  # pragma: no cover - exercised via GUI/event messages
        collisions = self.details_dict().get("collisions", "").strip()
        if not collisions:
            return self.code
        return (
            "technology_swap resolution produced colliding active display ids: "
            f"{collisions}"
        )


def resolve_display_overrides_for_profile(
    merged_tech_definitions: Mapping[str, MergedTechDefinition],
    profile: EmpireProfile,
    *,
    evaluator: TriggerEvaluator | None = None,
    raise_on_collision: bool = True,
) -> tuple[dict[str, str], SwapResolutionReport]:
    trigger_evaluator = evaluator if evaluator is not None else TriggerEvaluator()
    display_overrides: dict[str, str] = {}
    report = SwapResolutionReport()

    ordered_tech_ids = sorted(merged_tech_definitions)
    for tech_id in ordered_tech_ids:
        merged = merged_tech_definitions[tech_id]
        swaps = merged.technology_swaps
        if not swaps:
            continue

        _resolve_tech_swaps(
            tech_id=tech_id,
            swaps=swaps,
            profile=profile,
            evaluator=trigger_evaluator,
            display_overrides=display_overrides,
            report=report,
        )

    _collect_collisions(
        ordered_tech_ids=ordered_tech_ids,
        display_overrides=display_overrides,
        report=report,
    )

    if raise_on_collision and report.has_collisions:
        raise SwapResolutionCollisionError(report)

    return display_overrides, report


def _resolve_tech_swaps(
    *,
    tech_id: str,
    swaps: Iterable[TechnologySwap],
    profile: EmpireProfile,
    evaluator: TriggerEvaluator,
    display_overrides: dict[str, str],
    report: SwapResolutionReport,
) -> None:
    for swap_index, swap in enumerate(swaps):
        result = evaluator.evaluate_potential(swap.trigger, profile)

        if result.error is not None or result.value is None:
            report.ambiguities[tech_id] = SwapAmbiguity(
                swap_index=swap_index,
                unknown_predicates=_sorted_unique(result.unknown_predicates),
                reason_trace=_ambiguity_reason_trace(result),
                error=result.error,
            )
            return

        if result.value is True:
            chosen_name = (swap.name or "").strip()
            report.chosen_swaps[tech_id] = ChosenSwap(
                swap_name=chosen_name,
                swap_index=swap_index,
            )
            if chosen_name and chosen_name != tech_id:
                display_overrides[tech_id] = chosen_name
            return


def _collect_collisions(
    *,
    ordered_tech_ids: Iterable[str],
    display_overrides: Mapping[str, str],
    report: SwapResolutionReport,
) -> None:
    active_to_base_ids: dict[str, list[str]] = {}
    for base_tech_id in ordered_tech_ids:
        active_display_id = display_overrides.get(base_tech_id, base_tech_id)
        active_to_base_ids.setdefault(active_display_id, []).append(base_tech_id)

    for active_display_id in sorted(active_to_base_ids):
        base_tech_ids = tuple(active_to_base_ids[active_display_id])
        if len(base_tech_ids) < 2:
            continue
        report.collisions[active_display_id] = SwapCollision(
            base_tech_ids=base_tech_ids
        )


def _ambiguity_reason_trace(result: TriggerEvaluationResult) -> tuple[str, ...]:
    if result.reason_trace:
        return tuple(result.reason_trace)
    if result.error is not None:
        return (result.error,)
    return ("technology_swap trigger resolved to unknown",)
