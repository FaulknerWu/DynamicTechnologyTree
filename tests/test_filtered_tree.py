# pyright: reportMissingImports=false

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from config import (
    DisplayConfig,
    GeneratorConfig,
    LocalizationConfig,
    PathConfig,
)
from dtt_core.clausewitz_parser import Assignment, Block, parse
from dtt_core.eligibility import build_allowed_tech_ids_for_empire
from dtt_core.output import OutputWriter
from dtt_core.render import TreeRenderer
from dtt_core.settings_snapshot import require_settings_snapshot
from dtt_core.tech_merge import MergedTechDefinition
from dtt_core.trigger_evaluator import EmpireProfile
from models import Technology
from settings import Settings


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
    assert isinstance(potential.value, Block)
    return potential.value


def _build_techs() -> dict[str, Technology]:
    root = Technology("tech_root", research_area="physics", tier_level=1)
    regular_only = Technology(
        "tech_regular_only",
        research_area="physics",
        tier_level=2,
        prerequisite_tech_ids=["tech_root"],
    )
    machine_only = Technology(
        "tech_machine_only",
        research_area="engineering",
        tier_level=2,
        prerequisite_tech_ids=["tech_root"],
    )
    machine_child = Technology(
        "tech_machine_child",
        research_area="engineering",
        tier_level=3,
        prerequisite_tech_ids=["tech_machine_only"],
    )
    unknown_gate = Technology(
        "tech_unknown_gate",
        research_area="society",
        tier_level=2,
        prerequisite_tech_ids=["tech_root"],
    )

    root.unlocked_tech_ids = [
        "tech_regular_only",
        "tech_machine_only",
        "tech_unknown_gate",
    ]
    machine_only.unlocked_tech_ids = ["tech_machine_child"]

    return {
        root.tech_id: root,
        regular_only.tech_id: regular_only,
        machine_only.tech_id: machine_only,
        machine_child.tech_id: machine_child,
        unknown_gate.tech_id: unknown_gate,
    }


def _build_merged_defs() -> dict[str, MergedTechDefinition]:
    return {
        "tech_regular_only": MergedTechDefinition(
            tech_id="tech_regular_only",
            potential=_parse_potential_block("is_regular_empire = yes"),
        ),
        "tech_machine_only": MergedTechDefinition(
            tech_id="tech_machine_only",
            potential=_parse_potential_block("is_machine_empire = yes"),
        ),
        "tech_unknown_gate": MergedTechDefinition(
            tech_id="tech_unknown_gate",
            potential=_parse_potential_block("future_polity_gate = yes"),
        ),
    }


def _build_allowed_ids(
    techs: dict[str, Technology],
    merged: dict[str, MergedTechDefinition],
    profile_mode: str,
):
    return build_allowed_tech_ids_for_empire(
        techs,
        EmpireProfile.auto(profile_mode),
        merged,
    )


def _line_for_key(content: str, key: str) -> str:
    needle = f' {key}:0 "'
    for line in content.splitlines():
        if line.startswith(needle):
            return line
    raise AssertionError(f"missing key line: {key}")


def _build_config() -> GeneratorConfig:
    return GeneratorConfig(
        paths=PathConfig(base_game_path=".", mod_folder_path="."),
        localization=LocalizationConfig(target_language_code="english"),
        display=DisplayConfig(
            max_children_per_node=12, max_tree_depth=5, max_display_nodes=128
        ),
    )


def _build_settings_config(
    *,
    eligibility_sample_size: int,
    eligibility_unknown_warning_threshold: int = 1,
) -> GeneratorConfig:
    settings = Settings()
    settings.localization.target_language_code = "english"
    settings.output.eligibility_sample_size = eligibility_sample_size
    settings.output.eligibility_unknown_warning_threshold = (
        eligibility_unknown_warning_threshold
    )
    return require_settings_snapshot(settings).generator_config


def test_filtered_tree_module_file_is_removed() -> None:
    module_path = (
        Path(__file__).resolve().parents[1] / "src" / "dtt_core" / "filtered_tree.py"
    )
    assert not module_path.exists()


def test_filtered_tree_module_is_not_importable() -> None:
    sys.modules.pop("dtt_core.filtered_tree", None)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("dtt_core.filtered_tree")


def test_active_eligibility_flow_filters_per_profile() -> None:
    techs = _build_techs()
    merged = _build_merged_defs()

    regular_allowed, regular_report = _build_allowed_ids(
        techs,
        merged,
        "regular",
    )
    machine_allowed, machine_report = _build_allowed_ids(
        techs,
        merged,
        "machine",
    )

    assert "tech_regular_only" in regular_allowed
    assert "tech_machine_only" not in regular_allowed
    assert "tech_machine_child" not in regular_allowed
    assert "tech_unknown_gate" in regular_report.excluded_by_unknown
    assert "future_polity_gate" in regular_report.unknown_predicate_frequency

    assert "tech_machine_only" in machine_allowed
    assert "tech_machine_child" in machine_allowed
    assert "tech_regular_only" not in machine_allowed
    assert "tech_unknown_gate" in machine_report.excluded_by_unknown


def test_renderer_hides_excluded_nodes_and_subtrees() -> None:
    techs = _build_techs()
    merged = _build_merged_defs()
    regular_allowed, _ = _build_allowed_ids(techs, merged, "regular")
    machine_allowed, _ = _build_allowed_ids(techs, merged, "machine")

    renderer = TreeRenderer(
        all_technologies=techs,
        display_config=DisplayConfig(
            max_children_per_node=12, max_tree_depth=5, max_display_nodes=128
        ),
    )

    regular_tree = renderer.generate_tech_tree_content(
        "tech_root",
        "english",
        allowed_tech_ids=regular_allowed,
    )
    machine_tree = renderer.generate_tech_tree_content(
        "tech_root",
        "english",
        allowed_tech_ids=machine_allowed,
    )

    assert "tech_regular_only" in regular_tree
    assert "tech_machine_only" not in regular_tree
    assert "tech_machine_child" not in regular_tree
    assert "tech_unknown_gate" not in regular_tree

    assert "tech_machine_only" in machine_tree
    assert "tech_machine_child" in machine_tree
    assert "tech_regular_only" not in machine_tree
    assert "tech_unknown_gate" not in machine_tree


def test_output_writer_emits_single_context_keys_and_save_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    techs = _build_techs()
    merged = _build_merged_defs()
    descriptions = {
        "tech_root": {"english": "Root description."},
        "tech_regular_only": {"english": "Regular node."},
        "tech_machine_only": {"english": "Machine node."},
        "tech_unknown_gate": {"english": "Unknown node."},
    }

    renderer = TreeRenderer(
        all_technologies=techs,
        display_config=DisplayConfig(
            max_children_per_node=12, max_tree_depth=5, max_display_nodes=128
        ),
    )
    writer = OutputWriter(
        all_technologies=techs,
        tech_descriptions=descriptions,
        config=_build_config(),
        localize=lambda key, **kwargs: key,
        generate_tech_tree_content=renderer.generate_tech_tree_content,
        merged_tech_definitions=merged,
    )

    monkeypatch.chdir(tmp_path)
    write_result = writer.generate_all_yml_files()
    report = write_result.eligibility_report

    assert "tech_machine_only" in report.excluded_by_false
    assert "tech_unknown_gate" in report.excluded_by_unknown
    assert "tech_machine_child" in report.excluded_by_prereq

    main_file = tmp_path / "localisation" / "zztechtreemain_l_english.yml"
    replaced_file = tmp_path / "localisation" / "zztechtreereplaced_l_english.yml"
    save_report_file = tmp_path / "localisation" / "dtt-save-report.txt"

    main_text = main_file.read_text(encoding="utf-8-sig")
    replaced_text = replaced_file.read_text(encoding="utf-8-sig")
    save_report_text = save_report_file.read_text(encoding="utf-8")

    assert " tech_root_techtree:0 " in main_text
    assert " tech_root_machine_intelligence_techtree:0 " not in main_text
    assert "_corporate_techtree" not in main_text
    assert "_hive_mind_techtree" not in main_text
    assert "_machine_intelligence_techtree" not in main_text
    assert "_desc_corporate" not in replaced_text
    assert "_desc_hive_mind" not in replaced_text
    assert "_desc_machine_intelligence" not in replaced_text

    regular_root_line = _line_for_key(main_text, "tech_root_techtree")
    assert "tech_machine_only" not in regular_root_line
    assert "tech_machine_child" not in regular_root_line
    assert "tech_unknown_gate" not in regular_root_line

    root_desc_line = _line_for_key(replaced_text, "tech_root_desc")
    assert "$tech_root_techtree$" in root_desc_line

    assert "excluded_by_false: 1" in save_report_text
    assert "excluded_by_unknown: 1" in save_report_text
    assert "excluded_by_prereq: 1" in save_report_text
    assert "unknown_predicate_frequency_top:" in save_report_text
    assert "future_polity_gate" in save_report_text
    assert "swap_ambiguities:" in save_report_text


def test_output_writer_eligibility_custom_sample_changes_report_content_deterministically(
    tmp_path: Path,
) -> None:
    root = Technology("tech_root", research_area="physics", tier_level=1)
    unknown_ids = ["tech_unknown_a", "tech_unknown_b", "tech_unknown_c"]
    techs = {root.tech_id: root}
    descriptions = {"tech_root": {"english": "Root description."}}

    merged: dict[str, MergedTechDefinition] = {}
    for tech_id in unknown_ids:
        techs[tech_id] = Technology(
            tech_id,
            research_area="society",
            tier_level=2,
            prerequisite_tech_ids=["tech_root"],
        )
        descriptions[tech_id] = {"english": f"{tech_id} description."}
        merged[tech_id] = MergedTechDefinition(
            tech_id=tech_id,
            potential=_parse_potential_block("future_polity_gate = yes"),
        )
    root.unlocked_tech_ids = list(unknown_ids)

    renderer = TreeRenderer(
        all_technologies=techs,
        display_config=DisplayConfig(
            max_children_per_node=12,
            max_tree_depth=5,
            max_display_nodes=128,
        ),
    )

    sample_one_config = _build_settings_config(eligibility_sample_size=1)
    sample_two_config = _build_settings_config(eligibility_sample_size=2)
    assert sample_one_config.output.eligibility_sample_size == 1
    assert sample_two_config.output.eligibility_sample_size == 2

    writer_sample_one = OutputWriter(
        all_technologies=techs,
        tech_descriptions=descriptions,
        config=sample_one_config,
        localize=lambda key, **kwargs: key,
        generate_tech_tree_content=renderer.generate_tech_tree_content,
        merged_tech_definitions=merged,
        application_root=tmp_path / "sample-one",
    )
    writer_sample_two = OutputWriter(
        all_technologies=techs,
        tech_descriptions=descriptions,
        config=sample_two_config,
        localize=lambda key, **kwargs: key,
        generate_tech_tree_content=renderer.generate_tech_tree_content,
        merged_tech_definitions=merged,
        application_root=tmp_path / "sample-two",
    )

    writer_sample_one.generate_all_yml_files()
    writer_sample_two.generate_all_yml_files()

    report_one = tmp_path / "sample-one" / "localisation" / "dtt-save-report.txt"
    report_two = tmp_path / "sample-two" / "localisation" / "dtt-save-report.txt"

    line_one = next(
        line
        for line in report_one.read_text(encoding="utf-8").splitlines()
        if line.startswith("- future_polity_gate:")
    )
    line_two = next(
        line
        for line in report_two.read_text(encoding="utf-8").splitlines()
        if line.startswith("- future_polity_gate:")
    )

    assert line_one == "- future_polity_gate: count=3; examples=tech_unknown_a"
    assert (
        line_two
        == "- future_polity_gate: count=3; examples=tech_unknown_a, tech_unknown_b"
    )
    assert line_one != line_two
