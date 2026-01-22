from pathlib import Path
from typing import Dict, Set

from models import Technology
from config import EnabledModIds, GeneratorConfig
from mixins.config_mixin import ConfigAndLocalizationMixin
from mixins.parser_mixin import ParserMixin
from mixins.render_mixin import RenderMixin
from mixins.cycle_mixin import CycleMixin
from mixins.stats_mixin import StatsMixin
from mixins.output_mixin import OutputMixin
from mixins.relations_mixin import RelationsMixin


class TechTreeGenerator(
    ConfigAndLocalizationMixin,
    ParserMixin,
    RenderMixin,
    CycleMixin,
    StatsMixin,
    OutputMixin,
    RelationsMixin,
):
    def __init__(self, config_path: str):
        self.all_technologies: Dict[str, Technology] = {}
        self.base_game_tech_ids = set()
        self.tech_descriptions = {}
        self.variant_tech_ids: Set[str] = set()
        self.variant_trigger_overrides: Dict[str, Dict[str, str]] = {}
        self.polity_variant_map: Dict[str, Set[str]] = {}
        self.config: GeneratorConfig = self._load_configuration(config_path)
        self.current_mod_folder_name = Path(__file__).resolve().parents[1].name
        self.enabled_mods: EnabledModIds = self._load_enabled_mod_ids_from_dlc_load()
        self.overlong_tech_ids = set()

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
