from pathlib import Path
from typing import List, Set

from .localization import LOCALIZATION_STRINGS


class OutputMixin:
    def _get_output_file_paths(self, lang_code: str, filename: str):
        base = Path("output/localisation/")
        candidates = [
            base / filename,
            base / lang_code / filename,
            base / "replace" / filename,
            base / lang_code / "replace" / filename,
            base / "zzz_tech_trees" / "replace" / filename,
        ]
        unique = []
        seen: Set[Path] = set()
        for p in candidates:
            if p not in seen:
                unique.append(p)
                seen.add(p)
        for path in unique:
            path.parent.mkdir(parents=True, exist_ok=True)
        return unique

    def _generate_localization_files_for_language(self, lang_code: str, lang_key: str):
        self._generate_main_tech_tree_file(lang_code, lang_key)
        self._generate_tech_description_replacement_file(lang_code, lang_key)

    def _generate_main_tech_tree_file(self, lang_code: str, lang_key: str):
        file_paths = self._get_output_file_paths(lang_code, f"zztechtreemain_l_{lang_code}.yml")
        lang_config = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english'])
        lines = [
            f"{lang_key}:",
            f' technology_tree_title:0 "{lang_config["title"]}"',
            f' tech_tree_max_level:0 "{lang_config["top_level"]}"'
        ]
        for tech_id in sorted(self.all_technologies.keys()):
            tree_content = self.generate_tech_tree_content(tech_id, lang_code)
            if tree_content:
                lines.append(f' {tech_id}_techtree:0 "{tree_content}"')
        content = '\n'.join(lines)
        for file_path in file_paths:
            try:
                file_path.write_text(content, encoding='utf-8-sig')
            except (OSError, PermissionError) as e:
                print(self._l("warn_write_file_failed", file=file_path, error=e))

    def _generate_tech_description_replacement_file(self, lang_code: str, lang_key: str):
        file_paths = self._get_output_file_paths(lang_code, f"zztechtreereplaced_l_{lang_code}.yml")
        lines = [f"{lang_key}:"]
        missing_descriptions = []
        lang_config = LOCALIZATION_STRINGS.get(lang_code, LOCALIZATION_STRINGS['english'])
        for tech_id, tech in sorted(self.all_technologies.items()):
            tech_desc = ""
            if tech_id in self.tech_descriptions and lang_code in self.tech_descriptions[tech_id]:
                tech_desc = self.tech_descriptions[tech_id][lang_code]
            if not tech_desc:
                missing_descriptions.append(tech_id)
                tech_desc = ""
            tree_content = f"${tech_id}_techtree$"
            if tech_desc:
                full_desc = f"{tech_desc}({lang_config['tier_label']}{tech.tier_level}){tree_content}"
            else:
                full_desc = f"({lang_config['tier_label']}{tech.tier_level}){tree_content}"
            lines.append(f' {tech_id}_desc:0 "{full_desc}"')
        if missing_descriptions and len(missing_descriptions) > 0:
            print(self._l("warn_missing_descriptions", lang=lang_code, count=len(missing_descriptions)))
        content = '\n'.join(lines)
        for file_path in file_paths:
            try:
                file_path.write_text(content, encoding='utf-8-sig')
            except (OSError, PermissionError) as e:
                print(self._l("warn_write_file_failed", file=file_path, error=e))

    def generate_all_yml_files(self):
        output_dir = Path("output/localisation")
        output_dir.mkdir(parents=True, exist_ok=True)
        self._generate_localization_files_for_language(self.target_language_code, self.target_lang_key)
