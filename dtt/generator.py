import os
import sys
from pathlib import Path
from typing import Dict

from .models import Technology
from .config_mixin import ConfigAndLocalizationMixin
from .parser_mixin import ParserMixin
from .render_mixin import RenderMixin
from .cycle_mixin import CycleMixin
from .stats_mixin import StatsMixin
from .output_mixin import OutputMixin
from .relations_mixin import RelationsMixin
from .localization import LOCALIZATION_STRINGS


class TechTreeGenerator(ConfigAndLocalizationMixin, ParserMixin, RenderMixin, CycleMixin, StatsMixin, OutputMixin, RelationsMixin):
    def __init__(self, config_path: str):
        self.all_technologies: Dict[str, Technology] = {}
        self.base_game_tech_ids = set()
        self.tech_descriptions = {}
        (self.base_game_path,
         self.mod_folder_path,
         self.dlc_load_json_path,
         self.priority_localization_mod_ids,
         self.target_language_code,
         self.max_children_per_node,
         self.max_tree_depth,
         self.max_display_nodes,
         self.local_mod_folder_path) = self._load_configuration(config_path)
        self.target_lang_key = f"l_{self.target_language_code}"
        self.current_mod_folder_name = Path(__file__).parent.parent.name
        self.enabled_mod_ids = self._load_enabled_mod_ids_from_dlc_load()
        self.overlong_tech_ids = set()
        self.MAX_PREREQ_DISPLAY = 2
        self.ELLIPSIS = "…"

    def run_generation_process(self):
        try:
            print(self._l("msg_start_generation"))
            self.scan_all_technology_files()
            self.build_technology_tree_relationships()
            self.scan_all_tech_descriptions()
            print(self._l("msg_counting_tree"))
            self._precompute_overlong_trees()
            self.report_circular_dependencies()
            self.display_generation_statistics()
            self.generate_all_yml_files()
            print(self._l("msg_generation_done"))
        except Exception as e:
            # Localized error message
            try:
                print(self._l("error_generation_exception", error=e))
            except Exception:
                print(f"Generation error: {e}")
            import traceback
            traceback.print_exc()
