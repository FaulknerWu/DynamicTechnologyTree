import json
import configparser
from pathlib import Path
from typing import List, Optional
import re

from config import (
    DisplayConfig,
    EnabledModIds,
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

        default_loc = LocalizationConfig()
        default_display = DisplayConfig()
        try:
            base_path = config.get("paths", "base_game_path")
            workshop_mod_path = config.get("paths", "mod_folder_path")
            local_mod_path = config.get(
                "paths", "local_mod_folder_path", fallback=""
            ).strip()
            dlc_path_cfg = config.get("paths", "dlc_load_path", fallback="").strip()
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            fallback_lang = "english"
            msg_template = self._localization_strings.get(fallback_lang, {}).get(
                "error_missing_required_entries",
                "Error: required configuration entries missing: {error}",
            )
            raise ValueError(msg_template.format(error=e))
        if not dlc_path_cfg:
            dlc_path = str(
                Path.home()
                / "Documents"
                / "Paradox Interactive"
                / "Stellaris"
                / "dlc_load.json"
            )
        else:
            dlc_path = dlc_path_cfg
        if not config.has_section("localization"):
            fallback_lang = "english"
            msg_template = self._localization_strings.get(fallback_lang, {}).get(
                "error_missing_localization_section",
                "Error: missing [localization] section",
            )
            raise ValueError(msg_template)

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
        priority_mods_default = ",".join(default_loc.priority_localization_mod_ids)
        priority_mods_str = config.get(
            "localization",
            "priority_mods",
            fallback=priority_mods_default,
        ).strip()
        priority_mods: List[str] = [
            m.strip() for m in priority_mods_str.split(",") if m.strip()
        ]
        if priority_mods:
            print(
                self._localization_strings["english"]
                .get(
                    "msg_priority_localization_mods",
                    "Priority localization MODs: {count}",
                )
                .format(count=len(priority_mods))
            )
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
                dlc_load_json_path=dlc_path,
            ),
            localization=LocalizationConfig(
                target_language_code=language_code,
                priority_localization_mod_ids=priority_mods,
            ),
            display=DisplayConfig(
                max_children_per_node=max_children_per_node,
                max_tree_depth=max_tree_depth,
                max_display_nodes=max_display_nodes,
            ),
            tech=TechConfig(),
        )

    def load_enabled_mod_ids_from_dlc_load(
        self,
        dlc_load_json_path: Optional[str] = None,
        local_mod_folder_path: Optional[str] = None,
    ) -> EnabledModIds:
        try:
            dlc_path_value = ""
            local_mod_root = ""
            if self._config is not None:
                dlc_path_value = self._config.paths.dlc_load_json_path
                local_mod_root = self._config.paths.local_mod_folder_path
            else:
                dlc_path_value = dlc_load_json_path or ""
                local_mod_root = local_mod_folder_path or ""
            if dlc_path_value:
                dlc_json_path = Path(dlc_path_value)
            else:
                return EnabledModIds()
            if not dlc_json_path.exists():
                print(self.l("warn_missing_dlc_load", path=dlc_json_path))
                return EnabledModIds()
            data = json.loads(dlc_json_path.read_text(encoding="utf-8"))
            enabled = data.get("enabled_mods", [])
            workshop_ids: List[str] = []
            local_ids: List[str] = []
            seen_w = set()
            seen_l = set()
            path_pattern = re.compile(r'path\s*=\s*"([^"\n]+)"')
            local_root = local_mod_root or str(
                Path.home() / "Documents" / "Paradox Interactive" / "Stellaris" / "mod"
            )
            local_root_path = Path(local_root)
            for entry in enabled:
                name = Path(entry).name
                if not name.endswith(".mod"):
                    continue
                if name.startswith("ugc_"):
                    num_part = name[len("ugc_") : -len(".mod")]
                    if num_part.isdigit() and num_part not in seen_w:
                        workshop_ids.append(num_part)
                        seen_w.add(num_part)
                else:
                    descriptor_path = local_root_path / name
                    local_dir_name = ""
                    try:
                        if descriptor_path.exists():
                            text = descriptor_path.read_text(
                                encoding="utf-8", errors="ignore"
                            )
                            m = path_pattern.search(text)
                            if m:
                                candidate = Path(m.group(1).strip().strip("/")).name
                                if candidate:
                                    local_dir_name = candidate
                        if not local_dir_name:
                            local_dir_name = Path(name).stem
                    except Exception:
                        local_dir_name = Path(name).stem
                    if local_dir_name and local_dir_name not in seen_l:
                        local_ids.append(local_dir_name)
                        seen_l.add(local_dir_name)
            enabled_mods = EnabledModIds(workshop_ids=workshop_ids, local_ids=local_ids)
            print(self.l("msg_enabled_mods_count", count=len(enabled_mods.all_ids)))
            return enabled_mods
        except Exception as e:
            print(self.l("warn_read_dlc_load_failed", error=e))
            return EnabledModIds()

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
