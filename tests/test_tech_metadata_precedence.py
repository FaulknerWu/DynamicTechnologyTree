# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

from config import DisplayConfig, GeneratorConfig, LocalizationConfig, PathConfig, TechConfig
from dtt_core.ingestion_pipeline import IntegratedIngestionPipeline
from dtt_core.tech_merge import MergedTechDefinition


def _build_pipeline(tmp_path: Path) -> IntegratedIngestionPipeline:
    config = GeneratorConfig(
        paths=PathConfig(
            base_game_path=str(tmp_path),
            mod_folder_path=str(tmp_path),
        ),
        localization=LocalizationConfig(target_language_code="english"),
        display=DisplayConfig(),
        tech=TechConfig(),
    )
    return IntegratedIngestionPipeline(
        config=config,
        localize=lambda key, **kwargs: key,
        all_technologies={},
        base_game_tech_ids=set(),
        tech_descriptions={},
        merged_tech_definitions={},
    )


def test_explicit_repeatable_false_overrides_heuristics(tmp_path: Path) -> None:
    pipeline = _build_pipeline(tmp_path)

    merged = MergedTechDefinition(
        tech_id="repeatable_test_tech",
        levels=-1,
        is_repeatable=False,
    )
    tech = pipeline._create_runtime_technology(merged)

    assert tech.is_repeatable_tech is False


def test_explicit_dangerous_false_overrides_heuristics(tmp_path: Path) -> None:
    pipeline = _build_pipeline(tmp_path)

    merged = MergedTechDefinition(
        tech_id="tech_colossus",
        is_dangerous=False,
    )
    tech = pipeline._create_runtime_technology(merged)

    assert tech.is_dangerous_tech is False

