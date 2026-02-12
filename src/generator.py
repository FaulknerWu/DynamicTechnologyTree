from pathlib import Path
from typing import Dict, Set

from config import EnabledModIds, GeneratorConfig
from dtt_core.config_loader import ConfigLoader
from dtt_core.cycle import CycleDetector
from dtt_core.output import OutputWriter
from dtt_core.relations import RelationsBuilder
from dtt_core.render import TreeRenderer
from dtt_core.scan_parse import ScanParseCore
from dtt_core.stats import StatsReporter
from localization import LOCALIZATION_STRINGS, RESEARCH_AREA_ICONS
from models import Technology


class TechTreeGenerator:
    def __init__(self, config_path: str):
        self.all_technologies: Dict[str, Technology] = {}
        self.base_game_tech_ids = set()
        self.tech_descriptions = {}
        self.variant_tech_ids: Set[str] = set()
        self.variant_trigger_overrides: Dict[str, Dict[str, str]] = {}
        self.polity_variant_map: Dict[str, Set[str]] = {}
        self.current_mod_folder_name = Path(__file__).resolve().parents[1].name
        self.overlong_tech_ids = set()

        self._config_loader = ConfigLoader(LOCALIZATION_STRINGS)
        self.config: GeneratorConfig = self._config_loader.load_configuration(
            config_path
        )
        self._config_loader.set_config(self.config)
        self.enabled_mods: EnabledModIds = (
            self._config_loader.load_enabled_mod_ids_from_dlc_load()
        )

        self._scan_parse = ScanParseCore(
            config=self.config,
            enabled_mods=self.enabled_mods,
            current_mod_folder_name=self.current_mod_folder_name,
            localize=self._l,
            all_technologies=self.all_technologies,
            base_game_tech_ids=self.base_game_tech_ids,
            tech_descriptions=self.tech_descriptions,
            variant_trigger_overrides=self.variant_trigger_overrides,
            polity_variant_map=self.polity_variant_map,
            variant_tech_ids=self.variant_tech_ids,
        )
        self._relations_builder = RelationsBuilder(
            self.all_technologies,
            self.overlong_tech_ids,
            self.config.display,
        )
        self._tree_renderer = TreeRenderer(
            self.all_technologies,
            self.config.display,
            localization_strings=LOCALIZATION_STRINGS,
            research_area_icons=RESEARCH_AREA_ICONS,
            overlong_tech_ids=self.overlong_tech_ids,
        )
        self._cycle_detector = CycleDetector(self.all_technologies, self._l)
        self._output_writer = OutputWriter(
            all_technologies=self.all_technologies,
            tech_descriptions=self.tech_descriptions,
            config=self.config,
            localize=self._l,
            generate_tech_tree_content=self.generate_tech_tree_content,
            variant_trigger_overrides=self.variant_trigger_overrides,
            polity_variant_map=self.polity_variant_map,
        )
        self._stats_reporter = StatsReporter(
            self.all_technologies,
            self.base_game_tech_ids,
            self.tech_descriptions,
            self.overlong_tech_ids,
            self.config,
            self._l,
            self._print_overlong_tree_roots,
        )

    def _l(self, key: str, **kwargs) -> str:
        return self._config_loader.l(key, **kwargs)

    def scan_all_technology_files(self) -> None:
        self._scan_parse.scan_all_technology_files()

    def build_technology_tree_relationships(self) -> None:
        self._relations_builder.build_technology_tree_relationships()

    def scan_all_tech_descriptions(self) -> None:
        self._scan_parse.scan_all_tech_descriptions()

    def _precompute_overlong_trees(self) -> None:
        self._relations_builder.precompute_overlong_trees()

    def report_circular_dependencies(self) -> None:
        self._cycle_detector.report_circular_dependencies()

    def display_generation_statistics(self) -> None:
        self._stats_reporter.display_generation_statistics()

    def _print_overlong_tree_roots(self, limit: int = 50) -> None:
        T = self.config.display.max_display_nodes
        if T <= 0:
            return
        roots = sorted(self.overlong_tech_ids)
        if not roots:
            return
        print(self._l("overbreadth_list_header"))
        for idx, tid in enumerate(roots):
            if idx >= limit:
                remaining = len(roots) - limit
                print(self._l("overbreadth_truncated", remaining=remaining))
                break
            tech = self.all_technologies.get(tid)
            child_cnt = len(tech.unlocked_tech_ids) if tech else 0
            print(
                self._l(
                    "overbreadth_entry",
                    tech_id=tid,
                    child_count=child_cnt,
                    threshold=T,
                )
            )

    def generate_tech_tree_content(
        self,
        tech_id: str,
        lang_code: str = "simp_chinese",
        display_overrides: Dict[str, str] | None = None,
    ) -> str:
        return self._tree_renderer.generate_tech_tree_content(
            tech_id, lang_code, display_overrides
        )

    def _get_output_file_paths(self, lang_code: str, filename: str):
        return self._output_writer._get_output_file_paths(lang_code, filename)

    def generate_all_yml_files(self) -> None:
        self._output_writer.generate_all_yml_files()

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
