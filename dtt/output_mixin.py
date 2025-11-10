from pathlib import Path
from typing import Dict, List, Set

from .localization import LOCALIZATION_STRINGS


class OutputMixin:
    def _get_variant_display_overrides(self, trigger: str) -> Dict[str, str]:
        mapping = getattr(self, 'variant_trigger_overrides', None)
        if not mapping:
            return {}
        overrides = mapping.get(trigger)
        if not overrides:
            return {}
        return dict(overrides)

    def _build_polity_display_overrides(self, suffix: str) -> Dict[str, str]:
        mapping = getattr(self, 'polity_variant_map', {})
        overrides: Dict[str, str] = {}
        for base_id, variants in mapping.items():
            candidate = f"{base_id}_{suffix}"
            if candidate in variants:
                overrides[base_id] = candidate
        return overrides

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
        polity_variant_map = getattr(self, 'polity_variant_map', {})
        variant_tree_ids: Set[str] = set()
        for tech_id in sorted(self.all_technologies.keys()):
            tech = self.all_technologies[tech_id]
            tree_content = self.generate_tech_tree_content(tech_id, lang_code)
            if not tree_content:
                continue
            lines.append(f' {tech_id}_techtree:0 "{tree_content}"')
            variant_entries = [(trigger, variant) for trigger, variant in tech.variants.items() if variant]
            for trigger, variant_id in sorted(variant_entries, key=lambda item: item[1]):
                if variant_id in self.all_technologies or variant_id in variant_tree_ids:
                    continue
                overrides = self._get_variant_display_overrides(trigger)
                variant_tree = tree_content if not overrides else self.generate_tech_tree_content(tech_id, lang_code, display_overrides=overrides)
                lines.append(f' {variant_id}_techtree:0 "{variant_tree}"')
                variant_tree_ids.add(variant_id)
            polity_variants = polity_variant_map.get(tech_id, set())
            for variant_id in sorted(polity_variants):
                if variant_id in self.all_technologies or variant_id in variant_tree_ids:
                    continue
                if not variant_id.startswith(f"{tech_id}_"):
                    continue
                suffix_label = variant_id[len(tech_id) + 1:]
                overrides = self._build_polity_display_overrides(suffix_label)
                if tech_id not in overrides:
                    overrides[tech_id] = variant_id
                variant_tree = self.generate_tech_tree_content(tech_id, lang_code, display_overrides=overrides)
                lines.append(f' {variant_id}_techtree:0 "{variant_tree}"')
                variant_tree_ids.add(variant_id)
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
        polity_variant_map = getattr(self, 'polity_variant_map', {})
        variant_desc_ids: Set[str] = set()
        for tech_id, tech in sorted(self.all_technologies.items()):
            tech_desc = ""
            if tech_id in self.tech_descriptions and lang_code in self.tech_descriptions[tech_id]:
                tech_desc = self.tech_descriptions[tech_id][lang_code]
            if not tech_desc:
                missing_descriptions.append(tech_id)
                tech_desc = ""
            tree_content = f"${tech_id}_techtree$"
            tier_text = f"{lang_config['tier_label']}{tech.tier_level}"
            if tech_desc:
                full_desc = f"{tech_desc}({tier_text}){tree_content}"
            else:
                full_desc = f"({tier_text}){tree_content}"
            lines.append(f' {tech_id}_desc:0 "{full_desc}"')
            variant_entries = [(trigger, variant) for trigger, variant in tech.variants.items() if variant]
            for _, variant_id in sorted(variant_entries, key=lambda item: item[1]):
                if variant_id in self.all_technologies or variant_id in variant_desc_ids:
                    continue
                variant_desc_text = ""
                if variant_id in self.tech_descriptions and lang_code in self.tech_descriptions[variant_id]:
                    variant_desc_text = self.tech_descriptions[variant_id][lang_code]
                if not variant_desc_text:
                    variant_desc_text = tech_desc
                variant_tree_content = f"${variant_id}_techtree$"
                if variant_desc_text:
                    variant_full_desc = f"{variant_desc_text}({tier_text}){variant_tree_content}"
                else:
                    variant_full_desc = f"({tier_text}){variant_tree_content}"
                lines.append(f' {variant_id}_desc:0 "{variant_full_desc}"')
                variant_desc_ids.add(variant_id)
            polity_variants = polity_variant_map.get(tech_id, set())
            for variant_id in sorted(polity_variants):
                if variant_id in self.all_technologies:
                    continue
                if not variant_id.startswith(f"{tech_id}_"):
                    continue
                suffix_label = variant_id[len(tech_id) + 1:]
                variant_desc_key = f"{tech_id}_desc_{suffix_label}"
                if variant_desc_key in variant_desc_ids:
                    continue
                variant_desc_text = ""
                if variant_id in self.tech_descriptions and lang_code in self.tech_descriptions[variant_id]:
                    variant_desc_text = self.tech_descriptions[variant_id][lang_code]
                if not variant_desc_text:
                    variant_desc_text = tech_desc
                variant_tree_content = f"${variant_id}_techtree$"
                if variant_desc_text:
                    variant_full_desc = f"{variant_desc_text}({tier_text}){variant_tree_content}"
                else:
                    variant_full_desc = f"({tier_text}){variant_tree_content}"
                lines.append(f' {variant_desc_key}:0 "{variant_full_desc}"')
                variant_desc_ids.add(variant_desc_key)
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
