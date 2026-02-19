from dataclasses import dataclass


@dataclass(frozen=True)
class PathConfig:
    """File system paths for game and mod locations."""

    base_game_path: str
    mod_folder_path: str
    local_mod_folder_path: str = ""
    launcher_db_path: str = ""


@dataclass(frozen=True)
class LocalizationConfig:
    """Localization settings."""

    target_language_code: str = "simp_chinese"


@dataclass(frozen=True)
class DisplayConfig:
    """Tree rendering display limits."""

    max_children_per_node: int = 12
    max_tree_depth: int = 4
    max_display_nodes: int = 128


@dataclass(frozen=True)
class TechConfig:
    """Technology-specific settings (hardcoded, not configurable)."""

    pass


@dataclass(frozen=True)
class GeneratorConfig:
    """Complete configuration for TechTreeGenerator."""

    paths: PathConfig
    localization: LocalizationConfig
    display: DisplayConfig
    tech: TechConfig

    @property
    def target_lang_key(self) -> str:
        return f"l_{self.localization.target_language_code}"
