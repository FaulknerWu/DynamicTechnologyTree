import configparser
from typing import Optional

from config import (
    DisplayConfig,
    GeneratorConfig,
    LocalizationConfig,
    PathConfig,
    TechConfig,
)


class ConfigLoader:
    def __init__(
        self, localization_strings: dict, config: Optional[GeneratorConfig] = None
    ) -> None:
        self._localization_strings = localization_strings
        self._config = config

    def set_config(self, config: Optional[GeneratorConfig]) -> None:
        self._config = config

    def load_configuration(self, config_path: str) -> GeneratorConfig:
        config = configparser.ConfigParser()
        config.read(config_path, encoding="utf-8")

        if config.has_section("paths") and config.has_option("paths", "dlc_load_path"):
            raise ValueError(
                "Error: [paths] dlc_load_path is no longer supported; "
                "use launcher_db_path and point it to launcher-v2.sqlite"
            )

        default_loc = LocalizationConfig()
        default_display = DisplayConfig()
        try:
            base_path = config.get("paths", "base_game_path")
            workshop_mod_path = config.get("paths", "mod_folder_path")
            local_mod_path = config.get(
                "paths", "local_mod_folder_path", fallback=""
            ).strip()
            launcher_db_path = config.get("paths", "launcher_db_path").strip()
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            fallback_lang = "english"
            msg_template = self._localization_strings.get(fallback_lang, {}).get(
                "error_missing_required_entries",
                "Error: required configuration entries missing: {error}",
            )
            raise ValueError(msg_template.format(error=e))

        if not launcher_db_path:
            raise ValueError(
                "Error: [paths] launcher_db_path is required and must point to "
                "launcher-v2.sqlite"
            )

        if not config.has_section("localization"):
            fallback_lang = "english"
            msg_template = self._localization_strings.get(fallback_lang, {}).get(
                "error_missing_localization_section",
                "Error: missing [localization] section",
            )
            raise ValueError(msg_template)

        if config.has_option("localization", "priority_mods"):
            raise ValueError(
                "Error: [localization] priority_mods has been removed; "
                "delete this key from config.ini"
            )

        language_code = (
            config.get(
                "localization",
                "language",
                fallback=default_loc.target_language_code,
            ).strip()
            or default_loc.target_language_code
        )
        if language_code not in self._localization_strings:
            language_code = "english"
        max_children_per_node = default_display.max_children_per_node
        max_tree_depth = default_display.max_tree_depth
        max_display_nodes = default_display.max_display_nodes
        if config.has_section("display"):
            try:
                max_children_per_node = config.getint(
                    "display",
                    "max_children_per_node",
                    fallback=default_display.max_children_per_node,
                )
            except ValueError:
                pass
            try:
                max_tree_depth = config.getint(
                    "display",
                    "max_tree_depth",
                    fallback=default_display.max_tree_depth,
                )
            except ValueError:
                pass
            try:
                max_display_nodes = config.getint(
                    "display",
                    "max_display_nodes",
                    fallback=default_display.max_display_nodes,
                )
            except ValueError:
                pass
        return GeneratorConfig(
            paths=PathConfig(
                base_game_path=base_path,
                mod_folder_path=workshop_mod_path,
                local_mod_folder_path=local_mod_path,
                launcher_db_path=launcher_db_path,
            ),
            localization=LocalizationConfig(
                target_language_code=language_code,
            ),
            display=DisplayConfig(
                max_children_per_node=max_children_per_node,
                max_tree_depth=max_tree_depth,
                max_display_nodes=max_display_nodes,
            ),
            tech=TechConfig(),
        )

    def l(self, key: str, **kwargs) -> str:
        config = self._config
        lang_code = (
            config.localization.target_language_code
            if config is not None
            else "english"
        )
        lang_dict = self._localization_strings.get(
            lang_code, self._localization_strings.get("english", {})
        )
        base = lang_dict.get(key)
        if base is None:
            base = self._localization_strings.get("english", {}).get(key, key)
        try:
            return base.format(**kwargs)
        except Exception:
            return base
