from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from localization import DEFAULT_LANGUAGE_CODE

DEFAULT_YML_OUTPUT_TARGETS: tuple[str, ...] = (
    "",
    "{lang_code}",
    "replace",
    "{lang_code}/replace",
    "zzz_tech_trees/replace",
)

DEFAULT_DECODE_PREFERRED_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "utf-8")
DEFAULT_DECODE_FALLBACK_ENCODINGS: tuple[str, ...] = ("cp1252", "latin-1")
DEFAULT_DECODE_REPLACEMENT_ENCODING = "utf-8"
DEFAULT_INGESTION_DIAGNOSTIC_EXAMPLE_LIMIT = 10
DEFAULT_OVERLONG_TREE_ROOT_LOG_LIMIT = 50
DEFAULT_ELIGIBILITY_SAMPLE_SIZE = 5
DEFAULT_ELIGIBILITY_UNKNOWN_WARNING_THRESHOLD = 1
DEFAULT_DISPLAY_MAX_CHILDREN_PER_NODE = 12
DEFAULT_DISPLAY_MAX_TREE_DEPTH = 4
DEFAULT_DISPLAY_MAX_DISPLAY_NODES = 128
DEFAULT_DISPLAY_MAX_PREREQ_DISPLAY = 2
DEFAULT_SAVE_READER_MAX_MEMBER_UNCOMPRESSED_SIZE_BYTES = 256 * 1024 * 1024
DEFAULT_SAVE_READER_MAX_TOTAL_UNCOMPRESSED_SIZE_BYTES = 512 * 1024 * 1024
DEFAULT_SAVE_READER_MAX_PARSE_DIAGNOSTICS_PER_MEMBER = 20
DEFAULT_PROGRESS_SAVE_PARSE_START = 5
DEFAULT_PROGRESS_SAVE_PARSE_PARSE = 10
DEFAULT_PROGRESS_LOAD_ORDER = 20
DEFAULT_PROGRESS_RELATIONS = 35
DEFAULT_PROGRESS_INGEST_L10N = 45
DEFAULT_PROGRESS_RENDER = 50
DEFAULT_PROGRESS_CYCLES = 60
DEFAULT_PROGRESS_WRITE_OUTPUT = 80
DEFAULT_PROGRESS_DONE = 100


DEFAULT_TECHNOLOGY_ROOT = "common/technology"
DEFAULT_TECHNOLOGY_GLOB = "*.txt"
DEFAULT_LOCALISATION_ROOT = "localisation"
DEFAULT_LOCALISATION_GLOB = "**/*.yml"
DEFAULT_LOCALISATION_REPLACE_PREFIX = "localisation/replace"

DEFAULT_OUTPUT_YML_ENCODING = "utf-8-sig"
DEFAULT_OUTPUT_REPORT_ENCODING = "utf-8"

OutputWriteErrorPolicy = Literal["warn_and_continue", "fail_fast"]
ExistingFilePolicy = Literal["overwrite", "skip", "fail"]
DecodeFailurePolicy = Literal["replace", "strict"]

DEFAULT_OUTPUT_ON_WRITE_ERROR: OutputWriteErrorPolicy = "warn_and_continue"
DEFAULT_OUTPUT_ON_EXISTING_FILE: ExistingFilePolicy = "overwrite"
DEFAULT_DECODE_FAILURE_POLICY: DecodeFailurePolicy = "replace"

MultiActivePlaysetSelectionPolicy = Literal[
    "latest_created_then_name_then_id",
    "name_then_id",
]

DEFAULT_MULTI_ACTIVE_PLAYSET_SELECTION_POLICY: MultiActivePlaysetSelectionPolicy = (
    "latest_created_then_name_then_id"
)


@dataclass(frozen=True)
class OutputConfig:
    yml_targets: tuple[str, ...] = DEFAULT_YML_OUTPUT_TARGETS
    yml_encoding: str = DEFAULT_OUTPUT_YML_ENCODING
    report_encoding: str = DEFAULT_OUTPUT_REPORT_ENCODING
    on_write_error: OutputWriteErrorPolicy = DEFAULT_OUTPUT_ON_WRITE_ERROR
    on_existing_file: ExistingFilePolicy = DEFAULT_OUTPUT_ON_EXISTING_FILE
    eligibility_sample_size: int = DEFAULT_ELIGIBILITY_SAMPLE_SIZE
    eligibility_unknown_warning_threshold: int = (
        DEFAULT_ELIGIBILITY_UNKNOWN_WARNING_THRESHOLD
    )


@dataclass(frozen=True)
class DecodeConfig:
    preferred_encodings: tuple[str, ...] = DEFAULT_DECODE_PREFERRED_ENCODINGS
    fallback_encodings: tuple[str, ...] = DEFAULT_DECODE_FALLBACK_ENCODINGS
    replacement_encoding: str = DEFAULT_DECODE_REPLACEMENT_ENCODING
    on_failure: DecodeFailurePolicy = DEFAULT_DECODE_FAILURE_POLICY


@dataclass(frozen=True)
class IngestionConfig:
    diagnostic_example_limit: int = DEFAULT_INGESTION_DIAGNOSTIC_EXAMPLE_LIMIT


@dataclass(frozen=True)
class FileIndexConfig:
    technology_root: str = DEFAULT_TECHNOLOGY_ROOT
    technology_glob: str = DEFAULT_TECHNOLOGY_GLOB
    localisation_root: str = DEFAULT_LOCALISATION_ROOT
    localisation_glob: str = DEFAULT_LOCALISATION_GLOB
    localisation_replace_prefix: str = DEFAULT_LOCALISATION_REPLACE_PREFIX


@dataclass(frozen=True)
class PathConfig:
    """File system paths for game and mod locations."""

    base_game_path: str
    mod_folder_path: str
    local_mod_folder_path: str = ""
    launcher_db_path: str = ""


@dataclass(frozen=True)
class LoadOrderConfig:
    multi_active_playset_selection_policy: MultiActivePlaysetSelectionPolicy = (
        DEFAULT_MULTI_ACTIVE_PLAYSET_SELECTION_POLICY
    )


@dataclass(frozen=True)
class LocalizationConfig:
    """本地化设置。"""

    target_language_code: str = DEFAULT_LANGUAGE_CODE


@dataclass(frozen=True)
class DisplayConfig:
    """科技树渲染的显示限制。"""

    max_children_per_node: int = DEFAULT_DISPLAY_MAX_CHILDREN_PER_NODE
    max_tree_depth: int = DEFAULT_DISPLAY_MAX_TREE_DEPTH
    max_display_nodes: int = DEFAULT_DISPLAY_MAX_DISPLAY_NODES
    max_prereq_display: int = DEFAULT_DISPLAY_MAX_PREREQ_DISPLAY


@dataclass(frozen=True)
class DiagnosticsConfig:
    overlong_tree_roots_log_limit: int = DEFAULT_OVERLONG_TREE_ROOT_LOG_LIMIT


@dataclass(frozen=True)
class GeneratorConfig:
    """TechTreeGenerator 的完整运行时配置。"""

    paths: PathConfig
    localization: LocalizationConfig
    display: DisplayConfig
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)
    file_indexing: FileIndexConfig = field(default_factory=FileIndexConfig)
    load_order: LoadOrderConfig = field(default_factory=LoadOrderConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    decode: DecodeConfig = field(default_factory=DecodeConfig)
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)

    @property
    def target_lang_key(self) -> str:
        return f"l_{self.localization.target_language_code}"
