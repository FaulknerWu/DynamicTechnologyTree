from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class PathConfig:
    """File system paths for game and mod locations."""
    base_game_path: str
    mod_folder_path: str
    local_mod_folder_path: str = ""
    dlc_load_json_path: str = ""


@dataclass(frozen=True)
class LocalizationConfig:
    """Localization settings."""
    target_language_code: str = "simp_chinese"
    priority_localization_mod_ids: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class DisplayConfig:
    """Tree rendering display limits."""
    max_children_per_node: int = 0
    max_tree_depth: int = 0
    max_display_nodes: int = 0


@dataclass(frozen=True)
class TechConfig:
    """Technology-specific settings (hardcoded, not configurable)."""
    # Format: (trigger_name, expected_value)
    # Boolean triggers use "yes", parameterized triggers use specific value
    variant_triggers: List[Tuple[str, str]] = field(default_factory=lambda: [
        # Boolean triggers
        ("is_wilderness_empire", "yes"),
        ("country_uses_bio_ships", "yes"),
        ("is_beastmasters_empire", "yes"),
        ("is_gestalt", "yes"),
        ("is_tankbound_empire", "yes"),
        ("is_reanimator", "yes"),
        ("is_hive_empire", "yes"),
        ("is_robot_empire", "yes"),
        ("is_machine_empire", "yes"),
        ("is_cloning_authority", "yes"),
        # Parameterized triggers
        ("has_ascension_perk", "ap_weather_control"),
        ("has_origin", "origin_shroud_forged"),
        ("has_origin", "origin_overtuned"),
        ("is_situation_type", "situation_voidworm_plague"),
    ])
    polity_description_suffixes: List[str] = field(
        default_factory=lambda: ["corporate", "machine_intelligence", "hive_mind"]
    )


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


@dataclass
class EnabledModIds:
    """Mod IDs parsed from dlc_load.json."""
    workshop_ids: List[str] = field(default_factory=list)
    local_ids: List[str] = field(default_factory=list)

    @property
    def all_ids(self) -> List[str]:
        return self.workshop_ids + self.local_ids
