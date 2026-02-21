from __future__ import annotations

from typing import cast

from config import (
    DecodeConfig,
    DecodeFailurePolicy,
    DiagnosticsConfig,
    DisplayConfig,
    ExistingFilePolicy,
    FileIndexConfig,
    GeneratorConfig,
    IngestionConfig,
    LoadOrderConfig,
    LocalizationConfig,
    MultiActivePlaysetSelectionPolicy,
    OutputConfig,
    OutputWriteErrorPolicy,
    PathConfig,
    TechConfig,
)
from settings import Settings, require_supported_language


def require_settings_snapshot(settings: Settings | None) -> Settings:
    if settings is None:
        raise ValueError("settings is required and cannot be empty")
    return settings.model_copy(deep=True)


def generator_config_from_settings(settings: Settings) -> GeneratorConfig:
    language_code = require_supported_language(settings.localization.language)

    return GeneratorConfig(
        paths=PathConfig(
            base_game_path=settings.paths.base_game_path,
            mod_folder_path=settings.paths.mod_folder_path,
            local_mod_folder_path=settings.paths.local_mod_folder_path,
            launcher_db_path=settings.paths.launcher_db_path,
        ),
        file_indexing=FileIndexConfig(
            technology_root=settings.file_indexing.technology_root,
            technology_glob=settings.file_indexing.technology_glob,
            localisation_root=settings.file_indexing.localisation_root,
            localisation_glob=settings.file_indexing.localisation_glob,
            localisation_replace_prefix=settings.file_indexing.localisation_replace_prefix,
        ),
        load_order=LoadOrderConfig(
            multi_active_playset_selection_policy=cast(
                MultiActivePlaysetSelectionPolicy,
                settings.load_order.multi_active_playset_selection_policy,
            ),
        ),
        localization=LocalizationConfig(
            target_language_code=language_code,
        ),
        display=DisplayConfig(
            max_children_per_node=settings.display.max_children_per_node,
            max_tree_depth=settings.display.max_tree_depth,
            max_display_nodes=settings.display.max_display_nodes,
            max_prereq_display=settings.display.max_prereq_display,
        ),
        diagnostics=DiagnosticsConfig(
            overlong_tree_roots_log_limit=(
                settings.diagnostics.overlong_tree_roots_log_limit
            )
        ),
        tech=TechConfig(),
        ingestion=IngestionConfig(
            diagnostic_example_limit=settings.ingestion.diagnostic_example_limit,
        ),
        output=OutputConfig(
            yml_targets=tuple(settings.output.yml_targets),
            yml_encoding=settings.output.yml_encoding,
            report_encoding=settings.output.report_encoding,
            on_write_error=cast(
                OutputWriteErrorPolicy,
                settings.output.on_write_error,
            ),
            on_existing_file=cast(
                ExistingFilePolicy,
                settings.output.on_existing_file,
            ),
            eligibility_sample_size=settings.output.eligibility_sample_size,
            eligibility_unknown_warning_threshold=(
                settings.output.eligibility_unknown_warning_threshold
            ),
        ),
        decode=DecodeConfig(
            preferred_encodings=tuple(settings.decode.preferred_encodings),
            fallback_encodings=tuple(settings.decode.fallback_encodings),
            replacement_encoding=settings.decode.replacement_encoding,
            on_failure=cast(DecodeFailurePolicy, settings.decode.on_failure),
        ),
    )


__all__ = [
    "generator_config_from_settings",
    "require_settings_snapshot",
]
