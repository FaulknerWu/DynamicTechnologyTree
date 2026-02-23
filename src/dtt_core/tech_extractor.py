from __future__ import annotations

from dataclasses import dataclass

from dtt_core.clausewitz_parser import Assignment, Atom, Block, ClausewitzNode, parse
from dtt_core.clausewitz_text import _atom_text


@dataclass(frozen=True)
class TechnologySwap:
    name: str
    trigger: Block | None
    area: str | None = None
    category: str | None = None
    inherit_icon: bool | None = None
    inherit_effects: bool | None = None


@dataclass(frozen=True)
class TechDefinitionFragment:
    tech_id: str
    source: str = ""

    area: str | None = None
    tier: int | None = None
    prerequisites: list[str] | None = None
    levels: int | None = None
    start_tech: bool | None = None
    is_dangerous: bool | None = None
    is_repeatable: bool | None = None
    potential: Block | None = None
    technology_swaps: list[TechnologySwap] | None = None


class TechExtractor:
    def extract_from_text(
        self, text: str, *, source: str = ""
    ) -> list[TechDefinitionFragment]:
        res = parse(text, path=source or None)
        return self.extract_from_root(res.root, source=source)

    def extract_from_root(
        self, root: Block, *, source: str = ""
    ) -> list[TechDefinitionFragment]:
        fragments: list[TechDefinitionFragment] = []
        for item in root.items:
            if not isinstance(item, Assignment):
                continue
            if not isinstance(item.value, Block):
                continue
            tech_id = item.key.value
            if not tech_id or tech_id.startswith("@"):
                continue

            fragments.append(
                self._extract_tech_block(tech_id, item.value, source=source)
            )
        return fragments

    def _extract_tech_block(
        self, tech_id: str, block: Block, *, source: str
    ) -> TechDefinitionFragment:
        area: str | None = None
        tier: int | None = None
        prerequisites: list[str] | None = None
        levels: int | None = None
        start_tech: bool | None = None
        is_dangerous: bool | None = None
        is_repeatable: bool | None = None
        potential: Block | None = None
        swaps: list[TechnologySwap] = []
        saw_swaps = False

        for item in block.items:
            if not isinstance(item, Assignment):
                continue
            key = item.key.value

            if key == "area":
                if (value := _atom_text(item.value)) is not None:
                    area = value
            elif key == "tier":
                if (value := _atom_int(item.value)) is not None:
                    tier = value
            elif key == "prerequisites":
                if isinstance(item.value, Block):
                    prerequisites = _block_atom_list(item.value)
            elif key == "levels":
                if (value := _atom_int(item.value)) is not None:
                    levels = value
            elif key == "start_tech":
                if (value := _atom_bool(item.value)) is not None:
                    start_tech = value
            elif key == "is_dangerous":
                if (value := _atom_bool(item.value)) is not None:
                    is_dangerous = value
            elif key == "is_repeatable":
                if (value := _atom_bool(item.value)) is not None:
                    is_repeatable = value
            elif key == "potential":
                if isinstance(item.value, Block):
                    potential = item.value
            elif key == "technology_swap":
                if isinstance(item.value, Block):
                    saw_swaps = True
                    swaps.append(_extract_technology_swap(item.value))

        return TechDefinitionFragment(
            tech_id=tech_id,
            source=source,
            area=area,
            tier=tier,
            prerequisites=prerequisites,
            levels=levels,
            start_tech=start_tech,
            is_dangerous=is_dangerous,
            is_repeatable=is_repeatable,
            potential=potential,
            technology_swaps=swaps if saw_swaps else None,
        )


def _atom_int(node: ClausewitzNode) -> int | None:
    text = _atom_text(node)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _atom_bool(node: ClausewitzNode) -> bool | None:
    text = _atom_text(node)
    if text is None:
        return None
    lowered = text.strip().casefold()
    if lowered == "yes":
        return True
    if lowered == "no":
        return False
    return None


def _block_atom_list(block: Block) -> list[str]:
    out: list[str] = []
    for item in block.items:
        if isinstance(item, Atom):
            if item.token.value:
                out.append(item.token.value)
    return out


def _extract_technology_swap(block: Block) -> TechnologySwap:
    name = ""
    trigger: Block | None = None
    area: str | None = None
    category: str | None = None
    inherit_icon: bool | None = None
    inherit_effects: bool | None = None

    for item in block.items:
        if not isinstance(item, Assignment):
            continue
        key = item.key.value

        if key == "name":
            if (value := _atom_text(item.value)) is not None:
                name = value
        elif key == "trigger":
            if isinstance(item.value, Block):
                trigger = item.value
        elif key == "area":
            if (value := _atom_text(item.value)) is not None:
                area = value
        elif key == "category":
            if (value := _atom_text(item.value)) is not None:
                category = value
        elif key == "inherit_icon":
            if (value := _atom_bool(item.value)) is not None:
                inherit_icon = value
        elif key == "inherit_effects":
            if (value := _atom_bool(item.value)) is not None:
                inherit_effects = value

    return TechnologySwap(
        name=name,
        trigger=trigger,
        area=area,
        category=category,
        inherit_icon=inherit_icon,
        inherit_effects=inherit_effects,
    )
