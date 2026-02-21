from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable

from dtt_core.clausewitz_parser import Block
from dtt_core.tech_extractor import TechDefinitionFragment, TechnologySwap


@dataclass
class TechFieldProvenance:
    area: str | None = None
    tier: str | None = None
    prerequisites: str | None = None
    levels: str | None = None
    start_tech: str | None = None
    is_dangerous: str | None = None
    is_repeatable: str | None = None
    potential: str | None = None
    technology_swaps: str | None = None


@dataclass
class MergedTechDefinition:
    tech_id: str
    definition_source: str | None = None
    area: str | None = None
    tier: int | None = None
    prerequisites: list[str] = field(default_factory=list)
    levels: int | None = None
    start_tech: bool | None = None
    is_dangerous: bool | None = None
    is_repeatable: bool | None = None
    potential: Block | None = None
    technology_swaps: list[TechnologySwap] = field(default_factory=list)
    provenance: TechFieldProvenance = field(default_factory=TechFieldProvenance)


def merge_fragments(fragments: list[TechDefinitionFragment]) -> MergedTechDefinition:
    if not fragments:
        raise ValueError("merge_fragments() requires at least one fragment")

    tech_id = fragments[0].tech_id
    merged = MergedTechDefinition(tech_id=tech_id)

    for frag in fragments:
        if frag.tech_id != tech_id:
            raise ValueError(
                "merge_fragments() requires fragments for a single tech_id"
            )

        merged.definition_source = frag.source or None

        if frag.area is not None:
            merged.area = frag.area
            merged.provenance.area = frag.source

        if frag.tier is not None:
            merged.tier = frag.tier
            merged.provenance.tier = frag.source

        if frag.prerequisites is not None:
            merged.prerequisites = list(frag.prerequisites)
            merged.provenance.prerequisites = frag.source

        if frag.levels is not None:
            merged.levels = frag.levels
            merged.provenance.levels = frag.source

        if frag.is_dangerous is not None:
            merged.is_dangerous = frag.is_dangerous
            merged.provenance.is_dangerous = frag.source

        if frag.is_repeatable is not None:
            merged.is_repeatable = frag.is_repeatable
            merged.provenance.is_repeatable = frag.source

        if frag.potential is not None:
            merged.potential = frag.potential
            merged.provenance.potential = frag.source

        if frag.technology_swaps is not None:
            merged.technology_swaps = list(frag.technology_swaps)
            merged.provenance.technology_swaps = frag.source

        if frag.start_tech is not None:
            merged.start_tech = frag.start_tech
            merged.provenance.start_tech = frag.source
            if frag.start_tech is True:
                merged.prerequisites = []
                merged.provenance.prerequisites = frag.source

    return merged


def merge_all_fragments(
    fragments: Iterable[TechDefinitionFragment],
) -> dict[str, MergedTechDefinition]:
    ordered: dict[str, list[TechDefinitionFragment]] = {}
    for frag in fragments:
        ordered.setdefault(frag.tech_id, []).append(frag)
    return {tech_id: merge_fragments(frags) for tech_id, frags in ordered.items()}
