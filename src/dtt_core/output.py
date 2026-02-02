from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from localization import LOCALIZATION_STRINGS
from models import Technology


@dataclass
class VariantInfo:
    """Information about a variant technology."""

    variant_id: str
    trigger: Optional[str]
    suffix_label: Optional[str]
    base_tech_id: str


class OutputWriter:
    def __init__(
        self,
        *,
        all_technologies: Dict[str, Technology],
        tech_descriptions: Dict[str, Dict[str, str]],
        config,
        localize: Callable[..., str],
        generate_tech_tree_content: Callable[..., str],
        variant_trigger_overrides: Optional[Dict[str, Dict[str, str]]] = None,
        polity_variant_map: Optional[Dict[str, Set[str]]] = None,
    ) -> None:
        self.all_technologies = all_technologies
        self.tech_descriptions = tech_descriptions
        self.config = config
        self._localize = localize
        self.generate_tech_tree_content = generate_tech_tree_content
        self.variant_trigger_overrides = (
            variant_trigger_overrides if variant_trigger_overrides is not None else {}
        )
        self.polity_variant_map = (
            polity_variant_map if polity_variant_map is not None else {}
        )

    def _get_variant_display_overrides(self, trigger: str) -> Dict[str, str]:
        mapping = self.variant_trigger_overrides
        if not mapping:
            return {}
        overrides = mapping.get(trigger)
        if not overrides:
            return {}
        return dict(overrides)

    def _build_polity_display_overrides(self, suffix: Optional[str]) -> Dict[str, str]:
        mapping = self.polity_variant_map
        overrides: Dict[str, str] = {}
        for base_id, variants in mapping.items():
            candidate = f"{base_id}_{suffix}"
            if candidate in variants:
                overrides[base_id] = candidate
        return overrides

    def _collect_variant_infos(self, tech: Technology) -> List[VariantInfo]:
        """Collect all variant infos (trigger + polity) for a technology."""
        variants: List[VariantInfo] = []

        for trigger, variant_id in sorted(
            tech.variants.items(), key=lambda item: item[1] or ""
        ):
            if variant_id and variant_id not in self.all_technologies:
                variants.append(
                    VariantInfo(
                        variant_id=variant_id,
                        trigger=trigger,
                        suffix_label=None,
                        base_tech_id=tech.tech_id,
                    )
                )

        polity_variant_map = self.polity_variant_map
        polity_variants = polity_variant_map.get(tech.tech_id, set())
        for variant_id in sorted(polity_variants):
            if variant_id not in self.all_technologies and variant_id.startswith(
                f"{tech.tech_id}_"
            ):
                suffix_label = variant_id[len(tech.tech_id) + 1 :]
                variants.append(
                    VariantInfo(
                        variant_id=variant_id,
                        trigger=None,
                        suffix_label=suffix_label,
                        base_tech_id=tech.tech_id,
                    )
                )

        return variants

    def _generate_variant_tree(
        self,
        variant: VariantInfo,
        base_tree: str,
        lang_code: str,
        processed_ids: Set[str],
    ) -> Optional[str]:
        """Generate tree content for a variant, or None if already processed."""
        if variant.variant_id in processed_ids:
            return None
        processed_ids.add(variant.variant_id)

        if variant.trigger is not None:
            overrides = self._get_variant_display_overrides(variant.trigger)
            if not overrides:
                return base_tree
        else:
            overrides = self._build_polity_display_overrides(variant.suffix_label)
            if variant.base_tech_id not in overrides:
                overrides[variant.base_tech_id] = variant.variant_id

        return self.generate_tech_tree_content(
            variant.base_tech_id,
            lang_code,
            display_overrides=overrides,
        )

    def _generate_variant_description(
        self,
        variant: VariantInfo,
        base_desc: str,
        tier_text: str,
        lang_code: str,
        processed_ids: Set[str],
    ) -> Optional[Tuple[str, str]]:
        """Generate description for a variant. Returns (key, content) or None."""
        if variant.trigger is not None:
            if variant.variant_id in processed_ids:
                return None
            processed_ids.add(variant.variant_id)
            desc_key = f"{variant.variant_id}_desc"
        else:
            variant_desc_key = f"{variant.base_tech_id}_desc_{variant.suffix_label}"
            if variant_desc_key in processed_ids:
                return None
            processed_ids.add(variant_desc_key)
            desc_key = variant_desc_key

        variant_desc_text = ""
        if (
            variant.variant_id in self.tech_descriptions
            and lang_code in self.tech_descriptions[variant.variant_id]
        ):
            variant_desc_text = self.tech_descriptions[variant.variant_id][lang_code]
        if not variant_desc_text:
            variant_desc_text = base_desc
        variant_tree_content = f"${variant.variant_id}_techtree$"
        if variant_desc_text:
            variant_full_desc = (
                f"{variant_desc_text}({tier_text}){variant_tree_content}"
            )
        else:
            variant_full_desc = f"({tier_text}){variant_tree_content}"

        return desc_key, variant_full_desc

    def _get_output_file_paths(self, lang_code: str, filename: str):
        base = Path("localisation")
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
        file_paths = self._get_output_file_paths(
            lang_code,
            f"zztechtreemain_l_{lang_code}.yml",
        )
        lang_config = LOCALIZATION_STRINGS.get(
            lang_code, LOCALIZATION_STRINGS["english"]
        )
        lines = [
            f"{lang_key}:",
            f' technology_tree_title:0 "{lang_config["title"]}"',
            f' tech_tree_max_level:0 "{lang_config["top_level"]}"',
        ]
        variant_tree_ids: Set[str] = set()
        for tech_id in sorted(self.all_technologies.keys()):
            tech = self.all_technologies[tech_id]
            tree_content = self.generate_tech_tree_content(tech_id, lang_code)
            if not tree_content:
                continue
            lines.append(f' {tech_id}_techtree:0 "{tree_content}"')
            for variant in self._collect_variant_infos(tech):
                variant_tree = self._generate_variant_tree(
                    variant,
                    tree_content,
                    lang_code,
                    variant_tree_ids,
                )
                if variant_tree is None:
                    continue
                lines.append(f' {variant.variant_id}_techtree:0 "{variant_tree}"')
        content = "\n".join(lines)
        for file_path in file_paths:
            try:
                file_path.write_text(content, encoding="utf-8-sig")
            except (OSError, PermissionError) as e:
                print(self._localize("warn_write_file_failed", file=file_path, error=e))

    def _generate_tech_description_replacement_file(
        self, lang_code: str, lang_key: str
    ):
        file_paths = self._get_output_file_paths(
            lang_code,
            f"zztechtreereplaced_l_{lang_code}.yml",
        )
        lines = [f"{lang_key}:"]
        missing_descriptions = []
        lang_config = LOCALIZATION_STRINGS.get(
            lang_code, LOCALIZATION_STRINGS["english"]
        )
        variant_desc_ids: Set[str] = set()
        for tech_id, tech in sorted(self.all_technologies.items()):
            tech_desc = ""
            if (
                tech_id in self.tech_descriptions
                and lang_code in self.tech_descriptions[tech_id]
            ):
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
            for variant in self._collect_variant_infos(tech):
                variant_desc = self._generate_variant_description(
                    variant,
                    tech_desc,
                    tier_text,
                    lang_code,
                    variant_desc_ids,
                )
                if not variant_desc:
                    continue
                variant_desc_key, variant_full_desc = variant_desc
                lines.append(f' {variant_desc_key}:0 "{variant_full_desc}"')
        if missing_descriptions and len(missing_descriptions) > 0:
            print(
                self._localize(
                    "warn_missing_descriptions",
                    lang=lang_code,
                    count=len(missing_descriptions),
                )
            )
        content = "\n".join(lines)
        for file_path in file_paths:
            try:
                file_path.write_text(content, encoding="utf-8-sig")
            except (OSError, PermissionError) as e:
                print(self._localize("warn_write_file_failed", file=file_path, error=e))

    def generate_all_yml_files(self):
        output_dir = Path("localisation")
        output_dir.mkdir(parents=True, exist_ok=True)
        lang_code = self.config.localization.target_language_code
        self._generate_localization_files_for_language(
            lang_code, self.config.target_lang_key
        )
