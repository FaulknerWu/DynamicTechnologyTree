from __future__ import annotations

from typing import Any, ClassVar

from pydantic import (  # pyright: ignore[reportMissingImports]
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

from config import (
    DEFAULT_DECODE_FALLBACK_ENCODINGS,
    DEFAULT_DECODE_PREFERRED_ENCODINGS,
    DEFAULT_DECODE_REPLACEMENT_ENCODING,
    DEFAULT_DISPLAY_MAX_CHILDREN_PER_NODE,
    DEFAULT_DISPLAY_MAX_DISPLAY_NODES,
    DEFAULT_DISPLAY_MAX_PREREQ_DISPLAY,
    DEFAULT_DISPLAY_MAX_TREE_DEPTH,
    DEFAULT_ELIGIBILITY_SAMPLE_SIZE,
    DEFAULT_ELIGIBILITY_UNKNOWN_WARNING_THRESHOLD,
    DEFAULT_INGESTION_DIAGNOSTIC_EXAMPLE_LIMIT,
    DEFAULT_LOCALISATION_GLOB,
    DEFAULT_LOCALISATION_REPLACE_PREFIX,
    DEFAULT_LOCALISATION_ROOT,
    DEFAULT_MULTI_ACTIVE_PLAYSET_SELECTION_POLICY,
    DEFAULT_OUTPUT_ON_EXISTING_FILE,
    DEFAULT_OUTPUT_ON_WRITE_ERROR,
    DEFAULT_OUTPUT_REPORT_ENCODING,
    DEFAULT_OUTPUT_YML_ENCODING,
    DEFAULT_OVERLONG_TREE_ROOT_LOG_LIMIT,
    DEFAULT_SAVE_READER_MAX_MEMBER_UNCOMPRESSED_SIZE_BYTES,
    DEFAULT_SAVE_READER_MAX_PARSE_DIAGNOSTICS_PER_MEMBER,
    DEFAULT_SAVE_READER_MAX_TOTAL_UNCOMPRESSED_SIZE_BYTES,
    DEFAULT_TECHNOLOGY_GLOB,
    DEFAULT_TECHNOLOGY_ROOT,
    DEFAULT_YML_OUTPUT_TARGETS,
    DecodeFailurePolicy,
    ExistingFilePolicy,
    MultiActivePlaysetSelectionPolicy,
    OutputWriteErrorPolicy,
)
from localization import (
    DEFAULT_LANGUAGE_CODE,
    SUPPORTED_LANGUAGE_CODES,
    require_supported_language_code,
)


def _ui_meta(*, tab: str, group: str, label_key: str, help_key: str) -> dict[str, Any]:
    return {
        "tab": tab,
        "group": group,
        "label_key": label_key,
        "help_key": help_key,
    }


def _normalize_encoding_list(value: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in value:
        encoding = str(raw).strip().lower()
        if not encoding:
            raise ValueError(f"{field_name} entries must be non-empty")
        if encoding in seen:
            continue
        seen.add(encoding)
        normalized.append(encoding)
    return normalized


def _normalize_relative_scan_path(
    value: str,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> str:
    text = str(value).replace("\\", "/").strip()
    if not text:
        if allow_empty:
            return ""
        raise ValueError(f"{field_name} must be non-empty")

    while text.startswith("./"):
        text = text[2:]
    text = text.strip("/")

    if not text:
        if allow_empty:
            return ""
        raise ValueError(f"{field_name} must be non-empty")

    first_part = text.split("/", 1)[0]
    if ":" in first_part:
        raise ValueError(f"{field_name} must be a relative path")

    return text


def _normalize_glob_pattern(value: str, *, field_name: str) -> str:
    text = str(value).replace("\\", "/").strip()
    if not text:
        raise ValueError(f"{field_name} must be non-empty")
    return text


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathsSettings(_StrictModel):
    base_game_path: str = Field(
        default="",
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="paths",
            label_key="ui_label_base_game_path",
            help_key="ui_help_base_game_path",
        ),
    )
    mod_folder_path: str = Field(
        default="",
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="paths",
            label_key="ui_label_workshop_path",
            help_key="ui_help_workshop_path",
        ),
    )
    launcher_db_path: str = Field(
        default="",
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="paths",
            label_key="ui_label_paths_launcher_db_path",
            help_key="ui_help_paths_launcher_db_path",
        ),
    )
    local_mod_folder_path: str = Field(
        default="",
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="paths",
            label_key="ui_label_local_mod_path_optional",
            help_key="ui_help_local_mod_path",
        ),
    )
    steam_app_id: str = Field(
        default="281990",
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="autodetect",
            label_key="ui_label_paths_steam_app_id",
            help_key="ui_help_paths_steam_app_id",
        ),
    )
    game_directory_name: str = Field(
        default="Stellaris",
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="autodetect",
            label_key="ui_label_paths_game_directory_name",
            help_key="ui_help_paths_game_directory_name",
        ),
    )
    user_data_subpath_components: list[str] = Field(
        default_factory=lambda: ["Paradox Interactive", "Stellaris"],
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="autodetect",
            label_key="ui_label_paths_user_data_subpath_components",
            help_key="ui_help_paths_user_data_subpath_components",
        ),
    )
    launcher_db_filename: str = Field(
        default="launcher-v2.sqlite",
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="autodetect",
            label_key="ui_label_paths_launcher_db_filename",
            help_key="ui_help_paths_launcher_db_filename",
        ),
    )
    local_mod_directory_name: str = Field(
        default="mod",
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="autodetect",
            label_key="ui_label_paths_local_mod_directory_name",
            help_key="ui_help_paths_local_mod_directory_name",
        ),
    )


class FileIndexingSettings(_StrictModel):
    technology_root: str = Field(
        default=DEFAULT_TECHNOLOGY_ROOT,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="file_indexing",
            label_key="ui_label_file_indexing_technology_root",
            help_key="ui_help_file_indexing_technology_root",
        ),
    )
    technology_glob: str = Field(
        default=DEFAULT_TECHNOLOGY_GLOB,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="file_indexing",
            label_key="ui_label_file_indexing_technology_glob",
            help_key="ui_help_file_indexing_technology_glob",
        ),
    )
    localisation_root: str = Field(
        default=DEFAULT_LOCALISATION_ROOT,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="file_indexing",
            label_key="ui_label_file_indexing_localisation_root",
            help_key="ui_help_file_indexing_localisation_root",
        ),
    )
    localisation_glob: str = Field(
        default=DEFAULT_LOCALISATION_GLOB,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="file_indexing",
            label_key="ui_label_file_indexing_localisation_glob",
            help_key="ui_help_file_indexing_localisation_glob",
        ),
    )
    localisation_replace_prefix: str = Field(
        default=DEFAULT_LOCALISATION_REPLACE_PREFIX,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="file_indexing",
            label_key="ui_label_file_indexing_localisation_replace_prefix",
            help_key="ui_help_file_indexing_localisation_replace_prefix",
        ),
    )

    @field_validator("technology_root", "localisation_root")
    @classmethod
    def _validate_roots(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        field_name = info.field_name or "root"
        return _normalize_relative_scan_path(value, field_name=field_name)

    @field_validator("localisation_replace_prefix")
    @classmethod
    def _validate_localisation_replace_prefix(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        field_name = info.field_name or "localisation_replace_prefix"
        return _normalize_relative_scan_path(
            value,
            field_name=field_name,
            allow_empty=True,
        )

    @field_validator("technology_glob", "localisation_glob")
    @classmethod
    def _validate_globs(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        field_name = info.field_name or "glob"
        return _normalize_glob_pattern(value, field_name=field_name)


class LoadOrderSettings(_StrictModel):
    multi_active_playset_selection_policy: MultiActivePlaysetSelectionPolicy = Field(
        default=DEFAULT_MULTI_ACTIVE_PLAYSET_SELECTION_POLICY,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="load_order",
            label_key="ui_label_load_order_multi_active_playset_selection_policy",
            help_key="ui_help_load_order_multi_active_playset_selection_policy",
        ),
    )


class LocalizationSettings(_StrictModel):
    target_language_code: str = Field(
        default=DEFAULT_LANGUAGE_CODE,
        json_schema_extra={
            **_ui_meta(
                tab="ui_tab_localization",
                group="localization",
                label_key="ui_label_language",
                help_key="ui_help_language",
            ),
            "enum": list(SUPPORTED_LANGUAGE_CODES),
        },
    )

    @field_validator("target_language_code")
    @classmethod
    def _validate_target_language_code(cls, value: str) -> str:
        return require_supported_language_code(value, field_name="target_language_code")


class DisplaySettings(_StrictModel):
    max_children_per_node: int = Field(
        default=DEFAULT_DISPLAY_MAX_CHILDREN_PER_NODE,
        ge=0,
        le=999,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="display",
            label_key="ui_label_max_children",
            help_key="ui_help_max_children",
        ),
    )
    max_tree_depth: int = Field(
        default=DEFAULT_DISPLAY_MAX_TREE_DEPTH,
        ge=0,
        le=99,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="display",
            label_key="ui_label_max_depth",
            help_key="ui_help_max_depth",
        ),
    )
    max_display_nodes: int = Field(
        default=DEFAULT_DISPLAY_MAX_DISPLAY_NODES,
        ge=0,
        le=9999,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="display",
            label_key="ui_label_max_nodes",
            help_key="ui_help_max_nodes",
        ),
    )
    max_prereq_display: int = Field(
        default=DEFAULT_DISPLAY_MAX_PREREQ_DISPLAY,
        ge=0,
        le=99,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="display",
            label_key="ui_label_display_max_prereq_display",
            help_key="ui_help_display_max_prereq_display",
        ),
    )


class DecodeSettings(_StrictModel):
    preferred_encodings: list[str] = Field(
        default_factory=lambda: list(DEFAULT_DECODE_PREFERRED_ENCODINGS),
        json_schema_extra={
            **_ui_meta(
                tab="ui_tab_output",
                group="decode",
                label_key="ui_label_decode_preferred_encodings",
                help_key="ui_help_decode_preferred_encodings",
            ),
            "title": "Preferred encodings",
        },
    )
    fallback_encodings: list[str] = Field(
        default_factory=lambda: list(DEFAULT_DECODE_FALLBACK_ENCODINGS),
        json_schema_extra={
            **_ui_meta(
                tab="ui_tab_output",
                group="decode",
                label_key="ui_label_decode_fallback_encodings",
                help_key="ui_help_decode_fallback_encodings",
            ),
            "title": "Fallback encodings",
        },
    )
    replacement_encoding: str = Field(
        default=DEFAULT_DECODE_REPLACEMENT_ENCODING,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="decode",
            label_key="ui_label_decode_replacement_encoding",
            help_key="ui_help_decode_replacement_encoding",
        ),
    )
    on_failure: DecodeFailurePolicy = Field(
        default="replace",
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="decode",
            label_key="ui_label_decode_on_failure",
            help_key="ui_help_decode_on_failure",
        ),
    )

    @field_validator("preferred_encodings", "fallback_encodings")
    @classmethod
    def _validate_encoding_lists(
        cls,
        value: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        field_name = info.field_name or "encodings"
        return _normalize_encoding_list(value, field_name=field_name)

    @field_validator("replacement_encoding")
    @classmethod
    def _validate_replacement_encoding(cls, value: str) -> str:
        encoding = str(value).strip().lower()
        if not encoding:
            raise ValueError("replacement_encoding must be non-empty")
        return encoding

_MAX_INT32 = (2**31) - 1


class SaveReaderSettings(_StrictModel):
    max_member_uncompressed_size_bytes: int = Field(
        default=DEFAULT_SAVE_READER_MAX_MEMBER_UNCOMPRESSED_SIZE_BYTES,
        ge=0,
        le=_MAX_INT32,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="save_reader",
            label_key="ui_label_save_reader_max_member_uncompressed_size_bytes",
            help_key="ui_help_save_reader_max_member_uncompressed_size_bytes",
        ),
    )
    max_total_uncompressed_size_bytes: int = Field(
        default=DEFAULT_SAVE_READER_MAX_TOTAL_UNCOMPRESSED_SIZE_BYTES,
        ge=0,
        le=_MAX_INT32,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="save_reader",
            label_key="ui_label_save_reader_max_total_uncompressed_size_bytes",
            help_key="ui_help_save_reader_max_total_uncompressed_size_bytes",
        ),
    )
    max_parse_diagnostics_per_member: int = Field(
        default=DEFAULT_SAVE_READER_MAX_PARSE_DIAGNOSTICS_PER_MEMBER,
        ge=0,
        le=1000,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="save_reader",
            label_key="ui_label_save_reader_max_parse_diagnostics_per_member",
            help_key="ui_help_save_reader_max_parse_diagnostics_per_member",
        ),
    )

    @field_validator("max_total_uncompressed_size_bytes")
    @classmethod
    def _validate_total_ge_member(
        cls,
        value: int,
        info: ValidationInfo,
    ) -> int:
        member = info.data.get("max_member_uncompressed_size_bytes")
        if isinstance(member, int) and value < member:
            raise ValueError(
                "must be greater than or equal to 'max_member_uncompressed_size_bytes'"
            )
        return value


class IngestionSettings(_StrictModel):
    diagnostic_example_limit: int = Field(
        default=DEFAULT_INGESTION_DIAGNOSTIC_EXAMPLE_LIMIT,
        ge=0,
        le=999,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="ingestion",
            label_key="ui_label_ingestion_diagnostic_example_limit",
            help_key="ui_help_ingestion_diagnostic_example_limit",
        ),
    )


class DiagnosticsSettings(_StrictModel):
    overlong_tree_roots_log_limit: int = Field(
        default=DEFAULT_OVERLONG_TREE_ROOT_LOG_LIMIT,
        ge=0,
        le=9999,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="diagnostics",
            label_key="ui_label_diagnostics_overlong_tree_roots_log_limit",
            help_key="ui_help_diagnostics_overlong_tree_roots_log_limit",
        ),
    )

class OutputSettings(_StrictModel):
    yml_targets: list[str] = Field(
        default_factory=lambda: list(DEFAULT_YML_OUTPUT_TARGETS),
        json_schema_extra={
            **_ui_meta(
                tab="ui_tab_output",
                group="output",
                label_key="ui_label_yml_targets",
                help_key="ui_help_yml_targets",
            ),
            "title": "YML output targets",
        },
    )
    yml_encoding: str = Field(
        default=DEFAULT_OUTPUT_YML_ENCODING,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="output",
            label_key="ui_label_yml_encoding",
            help_key="ui_help_yml_encoding",
        ),
    )
    report_encoding: str = Field(
        default=DEFAULT_OUTPUT_REPORT_ENCODING,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="output",
            label_key="ui_label_report_encoding",
            help_key="ui_help_report_encoding",
        ),
    )
    eligibility_sample_size: int = Field(
        default=DEFAULT_ELIGIBILITY_SAMPLE_SIZE,
        ge=0,
        le=999,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="eligibility",
            label_key="ui_label_output_eligibility_sample_size",
            help_key="ui_help_output_eligibility_sample_size",
        ),
    )
    eligibility_unknown_warning_threshold: int = Field(
        default=DEFAULT_ELIGIBILITY_UNKNOWN_WARNING_THRESHOLD,
        ge=0,
        le=9999,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="eligibility",
            label_key="ui_label_output_eligibility_unknown_warning_threshold",
            help_key="ui_help_output_eligibility_unknown_warning_threshold",
        ),
    )
    on_write_error: OutputWriteErrorPolicy = Field(
        default=DEFAULT_OUTPUT_ON_WRITE_ERROR,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="output",
            label_key="ui_label_on_write_error",
            help_key="ui_help_on_write_error",
        ),
    )
    on_existing_file: ExistingFilePolicy = Field(
        default=DEFAULT_OUTPUT_ON_EXISTING_FILE,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="output",
            label_key="ui_label_on_existing_file",
            help_key="ui_help_on_existing_file",
        ),
    )

    @field_validator("yml_targets")
    @classmethod
    def _validate_yml_targets(cls, value: list[str]) -> list[str]:
        # Allow empty string (means localisation/<filename>), but normalize whitespace.
        normalized: list[str] = []
        for item in value:
            normalized.append(str(item).strip())
        return normalized

class ProgressMilestonesSettings(_StrictModel):
    _PREVIOUS_MILESTONE: ClassVar[dict[str, str]] = {
        "save_parse_parse": "save_parse_start",
        "load_order": "save_parse_parse",
        "relations": "load_order",
        "ingest_l10n": "relations",
        "render": "ingest_l10n",
        "cycles": "render",
        "write_output": "cycles",
    }

    save_parse_start: int = Field(
        default=5,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_save_parse_start",
            help_key="ui_help_progress_milestone_save_parse_start",
        ),
    )
    save_parse_parse: int = Field(
        default=10,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_save_parse_parse",
            help_key="ui_help_progress_milestone_save_parse_parse",
        ),
    )
    load_order: int = Field(
        default=20,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_load_order",
            help_key="ui_help_progress_milestone_load_order",
        ),
    )
    relations: int = Field(
        default=35,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_relations",
            help_key="ui_help_progress_milestone_relations",
        ),
    )
    ingest_l10n: int = Field(
        default=45,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_ingest_l10n",
            help_key="ui_help_progress_milestone_ingest_l10n",
        ),
    )
    render: int = Field(
        default=50,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_render",
            help_key="ui_help_progress_milestone_render",
        ),
    )
    cycles: int = Field(
        default=60,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_cycles",
            help_key="ui_help_progress_milestone_cycles",
        ),
    )
    write_output: int = Field(
        default=80,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_write_output",
            help_key="ui_help_progress_milestone_write_output",
        ),
    )
    done: int = Field(
        default=100,
        ge=0,
        le=100,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestone_done",
            help_key="ui_help_progress_milestone_done",
        ),
    )

    @field_validator(
        "save_parse_parse",
        "load_order",
        "relations",
        "ingest_l10n",
        "render",
        "cycles",
        "write_output",
    )
    @classmethod
    def _validate_monotonic_non_decreasing(
        cls,
        value: int,
        info: ValidationInfo,
    ) -> int:
        field_name = info.field_name
        if field_name is None:
            return value
        previous_name = cls._PREVIOUS_MILESTONE.get(field_name)
        if previous_name is None:
            return value

        previous_value = info.data.get(previous_name)
        if isinstance(previous_value, int) and value < previous_value:
            raise ValueError(f"must be greater than or equal to '{previous_name}'")
        return value

    @field_validator("done")
    @classmethod
    def _validate_done_milestone(cls, value: int) -> int:
        if value != 100:
            raise ValueError("must be exactly 100")
        return value


class Settings(_StrictModel):
    schema_version: int = Field(
        default=1,
        ge=1,
        json_schema_extra=_ui_meta(
            tab="settings",
            group="schema",
            label_key="ui_label_schema_version",
            help_key="ui_help_schema_version",
        ),
    )
    paths: PathsSettings = Field(
        default_factory=PathsSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="paths",
            label_key="ui_tab_paths",
            help_key="ui_help_paths",
        ),
    )
    file_indexing: FileIndexingSettings = Field(
        default_factory=FileIndexingSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="file_indexing",
            label_key="ui_label_file_indexing",
            help_key="ui_help_file_indexing",
        ),
    )
    load_order: LoadOrderSettings = Field(
        default_factory=LoadOrderSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_paths",
            group="load_order",
            label_key="ui_label_load_order",
            help_key="ui_help_load_order",
        ),
    )
    localization: LocalizationSettings = Field(
        default_factory=LocalizationSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_localization",
            group="localization",
            label_key="ui_tab_localization",
            help_key="ui_help_localization",
        ),
    )
    display: DisplaySettings = Field(
        default_factory=DisplaySettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="display",
            label_key="ui_tab_display",
            help_key="ui_help_display",
        ),
    )
    decode: DecodeSettings = Field(
        default_factory=DecodeSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="decode",
            label_key="ui_label_decode",
            help_key="ui_help_decode",
        ),
    )
    save_reader: SaveReaderSettings = Field(
        default_factory=SaveReaderSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="save_reader",
            label_key="ui_label_save_reader",
            help_key="ui_help_save_reader",
        ),
    )
    ingestion: IngestionSettings = Field(
        default_factory=IngestionSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="ingestion",
            label_key="ui_label_ingestion",
            help_key="ui_help_ingestion",
        ),
    )
    diagnostics: DiagnosticsSettings = Field(
        default_factory=DiagnosticsSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="diagnostics",
            label_key="ui_label_diagnostics",
            help_key="ui_help_diagnostics",
        ),
    )
    output: OutputSettings = Field(
        default_factory=OutputSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_output",
            group="output",
            label_key="ui_tab_output",
            help_key="ui_help_output",
        ),
    )
    progress_milestones: ProgressMilestonesSettings = Field(
        default_factory=ProgressMilestonesSettings,
        json_schema_extra=_ui_meta(
            tab="ui_tab_display",
            group="progress_milestones",
            label_key="ui_label_progress_milestones",
            help_key="ui_help_progress_milestones",
        ),
    )


def settings_json_schema() -> dict[str, Any]:
    return Settings.model_json_schema()


__all__ = [
    "DecodeSettings",
    "DiagnosticsSettings",
    "DisplaySettings",
    "FileIndexingSettings",
    "IngestionSettings",
    "LoadOrderSettings",
    "LocalizationSettings",
    "PathsSettings",
    "ProgressMilestonesSettings",
    "OutputSettings",
    "SaveReaderSettings",
    "Settings",
    "settings_json_schema",
]
