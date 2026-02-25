from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError  # pyright: ignore[reportMissingImports]

from config import (
    DecodeConfig,
    DiagnosticsConfig,
    DisplayConfig,
    FileIndexConfig,
    GeneratorConfig,
    IngestionConfig,
    LoadOrderConfig,
    LocalizationConfig,
    OutputConfig,
    PathConfig,
)
from dtt_core.sav_reader import SaveReaderLimits
from settings import Settings


@dataclass(frozen=True)
class ProgressMilestones:
    """生成流程各阶段的进度百分比里程碑。"""

    save_parse_start: int
    save_parse_parse: int
    load_order: int
    relations: int
    ingest_l10n: int
    render: int
    cycles: int
    write_output: int
    done: int


@dataclass(frozen=True)
class RunSettingsSnapshot:
    """一次生成任务的不可变配置快照（核心仅依赖该对象，不依赖 Settings）。"""

    generator_config: GeneratorConfig
    progress_milestones: ProgressMilestones
    save_reader_limits: SaveReaderLimits

    @property
    def ui_language_code(self) -> str:
        return self.generator_config.localization.target_language_code


def require_settings_snapshot(
    settings: Settings | RunSettingsSnapshot | None,
) -> RunSettingsSnapshot:
    """将用户 Settings 转换为核心运行所需的快照，并在此边界做最终校验。"""

    if settings is None:
        raise ValueError("settings 不能为空")

    if isinstance(settings, RunSettingsSnapshot):
        return settings

    payload = settings.model_dump(mode="python", round_trip=True)
    try:
        validated = Settings.model_validate(payload, strict=True)
    except ValidationError as exc:
        raise ValueError(_format_settings_validation_error(exc)) from exc

    return _snapshot_from_validated_settings(validated)


def _snapshot_from_validated_settings(settings: Settings) -> RunSettingsSnapshot:
    config = GeneratorConfig(
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
            multi_active_playset_selection_policy=settings.load_order.multi_active_playset_selection_policy,
        ),
        localization=LocalizationConfig(
            target_language_code=settings.localization.target_language_code,
        ),
        display=DisplayConfig(
            max_children_per_node=settings.display.max_children_per_node,
            max_tree_depth=settings.display.max_tree_depth,
            max_display_nodes=settings.display.max_display_nodes,
            max_prereq_display=settings.display.max_prereq_display,
        ),
        diagnostics=DiagnosticsConfig(
            overlong_tree_roots_log_limit=settings.diagnostics.overlong_tree_roots_log_limit,
        ),
        ingestion=IngestionConfig(
            diagnostic_example_limit=settings.ingestion.diagnostic_example_limit,
        ),
        output=OutputConfig(
            yml_targets=tuple(settings.output.yml_targets),
            yml_encoding=settings.output.yml_encoding,
            report_encoding=settings.output.report_encoding,
            on_write_error=settings.output.on_write_error,
            on_existing_file=settings.output.on_existing_file,
            eligibility_sample_size=settings.output.eligibility_sample_size,
            eligibility_unknown_warning_threshold=settings.output.eligibility_unknown_warning_threshold,
        ),
        decode=DecodeConfig(
            preferred_encodings=tuple(settings.decode.preferred_encodings),
            fallback_encodings=tuple(settings.decode.fallback_encodings),
            replacement_encoding=settings.decode.replacement_encoding,
            on_failure=settings.decode.on_failure,
        ),
    )

    progress = ProgressMilestones(
        save_parse_start=settings.progress_milestones.save_parse_start,
        save_parse_parse=settings.progress_milestones.save_parse_parse,
        load_order=settings.progress_milestones.load_order,
        relations=settings.progress_milestones.relations,
        ingest_l10n=settings.progress_milestones.ingest_l10n,
        render=settings.progress_milestones.render,
        cycles=settings.progress_milestones.cycles,
        write_output=settings.progress_milestones.write_output,
        done=settings.progress_milestones.done,
    )

    save_reader_limits = SaveReaderLimits(
        max_member_uncompressed_size_bytes=settings.save_reader.max_member_uncompressed_size_bytes,
        max_total_uncompressed_size_bytes=settings.save_reader.max_total_uncompressed_size_bytes,
        max_parse_diagnostics_per_member=settings.save_reader.max_parse_diagnostics_per_member,
    )

    return RunSettingsSnapshot(
        generator_config=config,
        progress_milestones=progress,
        save_reader_limits=save_reader_limits,
    )


def _format_settings_validation_error(exc: ValidationError) -> str:
    """将 Pydantic 的错误压缩为一条稳定、可读的错误消息。"""

    errors = exc.errors(include_url=False)
    if not errors:
        return "settings 无效：未知校验错误"

    first: dict[str, Any] = errors[0]
    loc = first.get("loc", ())
    if isinstance(loc, tuple) and loc:
        location = ".".join(str(part) for part in loc)
    else:
        location = "settings"
    message = str(first.get("msg", "")).strip()
    if message:
        return f"{location} 无效：{message}"
    return f"{location} 无效"


__all__ = [
    "ProgressMilestones",
    "RunSettingsSnapshot",
    "require_settings_snapshot",
]
