# pyright: reportMissingImports=false

from __future__ import annotations

from dtt_core.clausewitz_parser import Assignment, Atom, Block
from dtt_core.tech_extractor import TechExtractor
from dtt_core.tech_merge import merge_fragments


def _only_tech(fragments, tech_id: str):
    return [frag for frag in fragments if frag.tech_id == tech_id]


def test_merge_field_level_last_wins_and_provenance() -> None:
    vanilla_text = """
tech_a = {
  area = physics
  tier = 1
  prerequisites = { tech_b tech_c }
  potential = { always = yes }
}
"""
    mod_text = """
tech_a = {
  area = society
}
"""

    extractor = TechExtractor()
    vanilla_frags = extractor.extract_from_text(vanilla_text, source="vanilla.txt")
    mod_frags = extractor.extract_from_text(mod_text, source="mod_a.txt")
    merged = merge_fragments(_only_tech(vanilla_frags + mod_frags, "tech_a"))

    assert merged.definition_source == "mod_a.txt"

    assert merged.area == "society"
    assert merged.provenance.area == "mod_a.txt"

    assert merged.tier == 1
    assert merged.provenance.tier == "vanilla.txt"

    assert merged.prerequisites == ["tech_b", "tech_c"]
    assert merged.provenance.prerequisites == "vanilla.txt"

    assert isinstance(merged.potential, Block)
    assert merged.provenance.potential == "vanilla.txt"


def test_merge_multiple_mods_override_same_field() -> None:
    vanilla_text = """
tech_x = { tier = 1 }
"""
    mod1_text = """
tech_x = { tier = 2 }
"""
    mod2_text = """
tech_x = { tier = 3 }
"""

    extractor = TechExtractor()
    frags = []
    frags.extend(extractor.extract_from_text(vanilla_text, source="vanilla.txt"))
    frags.extend(extractor.extract_from_text(mod1_text, source="mod1.txt"))
    frags.extend(extractor.extract_from_text(mod2_text, source="mod2.txt"))
    merged = merge_fragments(_only_tech(frags, "tech_x"))

    assert merged.tier == 3
    assert merged.provenance.tier == "mod2.txt"


def test_prerequisites_cleared_by_start_tech_yes() -> None:
    vanilla_text = """
tech_start = { prerequisites = { tech_req } }
"""
    mod_text = """
tech_start = { start_tech = yes }
"""

    extractor = TechExtractor()
    frags = []
    frags.extend(extractor.extract_from_text(vanilla_text, source="vanilla.txt"))
    frags.extend(extractor.extract_from_text(mod_text, source="mod_start.txt"))
    merged = merge_fragments(_only_tech(frags, "tech_start"))

    assert merged.start_tech is True
    assert merged.provenance.start_tech == "mod_start.txt"

    assert merged.prerequisites == []
    assert merged.provenance.prerequisites == "mod_start.txt"


def test_prerequisites_cleared_by_empty_block() -> None:
    vanilla_text = """
tech_clear = { prerequisites = { tech_a tech_b } }
"""
    mod_text = """
tech_clear = { prerequisites = { } }
"""

    extractor = TechExtractor()
    frags = []
    frags.extend(extractor.extract_from_text(vanilla_text, source="vanilla.txt"))
    frags.extend(extractor.extract_from_text(mod_text, source="mod_clear.txt"))
    merged = merge_fragments(_only_tech(frags, "tech_clear"))

    assert merged.prerequisites == []
    assert merged.provenance.prerequisites == "mod_clear.txt"


def test_technology_swap_parsing_preserves_order_and_ast_blocks() -> None:
    text = """
tech_swap = {
  technology_swap = {
    name = tech_variant_1
    trigger = { always = yes }
    area = physics
    inherit_icon = yes
    inherit_effects = no
  }
  technology_swap = {
    name = tech_variant_2
    trigger = { always = no }
    category = engineering
  }
}
"""

    extractor = TechExtractor()
    frag = _only_tech(
        extractor.extract_from_text(text, source="swaps.txt"), "tech_swap"
    )[0]

    assert frag.technology_swaps is not None
    assert [swap.name for swap in frag.technology_swaps] == [
        "tech_variant_1",
        "tech_variant_2",
    ]

    first, second = frag.technology_swaps
    assert isinstance(first.trigger, Block)
    assert isinstance(second.trigger, Block)

    assert first.area == "physics"
    assert first.category is None
    assert first.inherit_icon is True
    assert first.inherit_effects is False

    assert second.area is None
    assert second.category == "engineering"
    assert second.inherit_icon is None
    assert second.inherit_effects is None


def test_potential_extraction_is_ast_block() -> None:
    text = """
tech_potential = {
  potential = {
    always = yes
  }
}
"""

    extractor = TechExtractor()
    frag = _only_tech(
        extractor.extract_from_text(text, source="potential.txt"), "tech_potential"
    )[0]

    assert isinstance(frag.potential, Block)
    assigns = [item for item in frag.potential.items if isinstance(item, Assignment)]
    assert len(assigns) == 1
    assert assigns[0].key.value == "always"
    assert isinstance(assigns[0].value, Atom)
    assert assigns[0].value.token.value == "yes"
