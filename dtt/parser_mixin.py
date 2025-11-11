import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .models import Technology
from .localization import LOCALIZATION_STRINGS


class ParserMixin:
    TECH_DEFINITION_REGEX = re.compile(r'(?m)^(\w+)\s*=\s*\{')
    PREREQUISITES_REGEX = re.compile(r'prerequisites\s*=\s*\{')
    COST_REGEX = re.compile(r'cost\s*=\s*([@\w\d]+)')
    CATEGORY_REGEX = re.compile(r'category\s*=\s*\{')
    POTENTIAL_REGEX = re.compile(r'(?:potential|starting_potential)\s*=\s*\{')
    DANGEROUS_TECH_REGEX = re.compile(r'is_dangerous\s*=\s*yes')
    REPEATABLE_TECH_REGEX = re.compile(r'is_repeatable\s*=\s*yes')
    TECH_SWAP_REGEX = re.compile(r'technology_swap\s*=\s*\{')
    SWAP_NAME_REGEX = re.compile(r'name\s*=\s*(?:"([^"\n]+)"|([@\w\.]+))')
    SWAP_TRIGGER_REGEX = re.compile(r'trigger\s*=\s*\{')
    RESEARCH_AREA_REGEX = re.compile(r'area\s*=\s*(\w+)')
    TIER_REGEX = re.compile(r'tier\s*=\s*(\d+)')
    STARTING_TECH_REGEX = re.compile(r'start_tech\s*=\s*yes')
    TECH_ID_REGEX = re.compile(r'"([^"]+)"|(\w+)')
    WORD_REGEX = re.compile(r'[\w_]+')
    DESCRIPTION_LOCALIZATION_REGEX = re.compile(r'^\s*([a-zA-Z0-9_]+_desc(?:_[a-zA-Z0-9_]+)*):(?:\d+)?\s*"([^"]*(?:\\.[^"]*)*)"', re.IGNORECASE)
    WHITESPACE_CLEANUP_REGEX = re.compile(r'\s+')
    LEVELS_REGEX = re.compile(r'levels\s*=\s*(-?\d+)')
    COST_PER_LEVEL_REGEX = re.compile(r'cost_per_level\s*=\s*([@\w\.\-]+)')
    WEIGHT_REGEX = re.compile(r'\bweight\s*=\s*([@\w\.\-]+)')
    GATEWAY_REGEX = re.compile(r'\bgateway\s*=\s*(?:"([^"\n]+)"|([@\w\.]+))')
    FEATURE_FLAGS_REGEX = re.compile(r'feature_flags\s*=\s*\{')
    WEIGHT_GROUPS_REGEX = re.compile(r'weight_groups\s*=\s*\{')
    MOD_WEIGHT_GROUP_REGEX = re.compile(r'mod_weight_if_group_picked\s*=\s*\{')
    WEIGHT_MODIFIER_REGEX = re.compile(r'weight_modifier\s*=\s*\{')
    AI_WEIGHT_REGEX = re.compile(r'ai_weight\s*=\s*\{')

    def _collect_mod_subdirs(
        self,
        mod_ids: List[str],
        root: Optional[Path],
        subpath: Tuple[str, ...],
        *,
        skip_current: bool = True,
        skip_ids: Optional[Set[str]] = None,
    ) -> Tuple[List[Tuple[str, Path]], List[str], List[str]]:
        existing: List[Tuple[str, Path]] = []
        missing_mods: List[str] = []
        missing_subdirs: List[str] = []
        if not root or not root.exists():
            return existing, missing_mods, missing_subdirs
        skip_lookup = set(skip_ids or [])
        for mod_id in mod_ids:
            if skip_current and mod_id == self.current_mod_folder_name:
                continue
            if skip_lookup and mod_id in skip_lookup:
                continue
            mod_dir = root / mod_id
            if not mod_dir.is_dir():
                missing_mods.append(mod_id)
                continue
            target_dir = mod_dir
            for part in subpath:
                target_dir = target_dir / part
            if not target_dir.exists():
                missing_subdirs.append(mod_id)
                continue
            existing.append((mod_id, target_dir))
        return existing, missing_mods, missing_subdirs

    def scan_all_technology_files(self):
        self._scan_technology_path(Path(self.base_game_path) / "common" / "technology")
        self.base_game_tech_ids = set(self.all_technologies.keys())

        workshop_root = Path(self.mod_folder_path)
        local_root = Path(self.local_mod_folder_path) if getattr(self, 'local_mod_folder_path', '') else None
        scanned_count = 0
        missing_mod_dirs: List[str] = []
        missing_tech_dirs: List[str] = []

        def process_mod_roots(mod_ids: List[str], root: Optional[Path]):
            nonlocal scanned_count
            paths, missing_mods, missing_subs = self._collect_mod_subdirs(mod_ids, root, ("common", "technology"))
            missing_mod_dirs.extend(missing_mods)
            missing_tech_dirs.extend(missing_subs)
            for _, tech_path in paths:
                new_techs = self._scan_technology_path(tech_path)
                if new_techs > 0:
                    scanned_count += 1

        workshop_ids = getattr(self, 'workshop_mod_ids', [])
        local_ids = getattr(self, 'local_mod_ids', [])
        process_mod_roots(workshop_ids, workshop_root)
        process_mod_roots(local_ids, local_root)
        if missing_mod_dirs:
            print(self._l("msg_missing_mod_dirs", count=len(missing_mod_dirs)))
        print(self._l("msg_mods_with_new_techs", count=scanned_count))

    def _scan_technology_path(self, path: Path) -> int:
        if not path.exists():
            return 0
        before_count = len(self.all_technologies)
        for file_path in path.glob("*.txt"):
            try:
                self._parse_single_tech_file(file_path)
            except Exception:
                pass
        return len(self.all_technologies) - before_count

    def _parse_single_tech_file(self, filepath: Path):
        content = self._read_file_with_encoding(filepath)
        if not content:
            return
        content = self._remove_comments_from_content(content)
        for match in self.TECH_DEFINITION_REGEX.finditer(content):
            tech_id = match.group(1)
            tech_block = self._extract_braced_block(content, match.end())
            if tech_block and tech_id not in self.all_technologies:
                self.all_technologies[tech_id] = Technology(tech_id)
                self._parse_tech_block_content(self.all_technologies[tech_id], tech_block)

    def _read_file_with_encoding(self, filepath: Path) -> str:
        try:
            return filepath.read_text(encoding='utf-8-sig', errors='ignore')
        except Exception:
            try:
                return filepath.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                return ""

    def _remove_comments_from_content(self, content: str) -> str:
        lines = []
        for line in content.splitlines():
            if line.lstrip().startswith('#'):
                continue
            if '#' in line:
                line = line.split('#', 1)[0]
            lines.append(line)
        return '\n'.join(lines)

    def _extract_braced_block(self, content: str, start_pos: int) -> str:
        brace_depth = 1
        for i, char in enumerate(content[start_pos:], start_pos):
            if char == '{':
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
                if brace_depth == 0:
                    return content[start_pos:i]
        return ""

    def _parse_variant_swaps(self, tech: Technology, content: str) -> None:
        triggers = getattr(self, 'variant_triggers', [])
        if not triggers:
            return
        compiled_patterns = {
            trigger: re.compile(rf"\b{re.escape(trigger)}\b\s*=\s*(?:yes|1)", re.IGNORECASE)
            for trigger in triggers
        }
        search_pos = 0
        while True:
            match = self.TECH_SWAP_REGEX.search(content, search_pos)
            if not match:
                break
            brace_index = content.find('{', match.start())
            if brace_index == -1:
                break
            block = self._extract_braced_block(content, brace_index + 1)
            if not block:
                search_pos = brace_index + 1
                continue
            name_match = self.SWAP_NAME_REGEX.search(block)
            if not name_match:
                search_pos = brace_index + len(block) + 1
                continue
            swap_name = name_match.group(1) or name_match.group(2)
            trigger_match = self.SWAP_TRIGGER_REGEX.search(block)
            trigger_block = ''
            if trigger_match:
                trig_brace_index = block.find('{', trigger_match.start())
                if trig_brace_index != -1:
                    trigger_block = self._extract_braced_block(block, trig_brace_index + 1)
            if not trigger_block or not swap_name:
                search_pos = brace_index + len(block) + 1
                continue
            for trigger, pattern in compiled_patterns.items():
                if trigger in tech.variants:
                    continue
                if pattern.search(trigger_block):
                    tech.variants[trigger] = swap_name
                    if swap_name:
                        variant_ids = getattr(self, 'variant_tech_ids', None)
                        if variant_ids is None:
                            variant_ids = set()
                            setattr(self, 'variant_tech_ids', variant_ids)
                        variant_ids.add(swap_name)
                        trigger_overrides = getattr(self, 'variant_trigger_overrides', None)
                        if trigger_overrides is not None:
                            trigger_overrides.setdefault(trigger, {})[tech.tech_id] = swap_name
            search_pos = brace_index + len(block) + 1

    def _parse_tech_block_content(self, tech: Technology, content: str):
        if area_match := self.RESEARCH_AREA_REGEX.search(content):
            tech.research_area = area_match.group(1)
        if tier_match := self.TIER_REGEX.search(content):
            tech.tier_level = int(tier_match.group(1))
        if m := self.PREREQUISITES_REGEX.search(content):
            block = self._extract_braced_block(content, m.end())
            tech_matches = self.TECH_ID_REGEX.findall(block)
            tech.prerequisite_tech_ids = [m_id if m_id else w_id for m_id, w_id in tech_matches]
        if self.STARTING_TECH_REGEX.search(content):
            tech.prerequisite_tech_ids = []
        if cost_match := self.COST_REGEX.search(content):
            tech.research_cost = cost_match.group(1)
        if cat_m := self.CATEGORY_REGEX.search(content):
            cat_block = self._extract_braced_block(content, cat_m.end())
            tech.tech_categories = [c for c in self.WORD_REGEX.findall(cat_block)]
        if pot_m := self.POTENTIAL_REGEX.search(content):
            pot_block = self._extract_braced_block(content, pot_m.end())
            tech.unlock_conditions = [p for p in self.WORD_REGEX.findall(pot_block)]
        if levels_match := self.LEVELS_REGEX.search(content):
            try:
                tech.levels = int(levels_match.group(1))
            except ValueError:
                tech.levels = None
            if tech.levels == -1:
                tech.is_repeatable_tech = True
        if cpl_match := self.COST_PER_LEVEL_REGEX.search(content):
            tech.cost_per_level = cpl_match.group(1)
        if weight_match := self.WEIGHT_REGEX.search(content):
            tech.weight = weight_match.group(1)
        if gateway_match := self.GATEWAY_REGEX.search(content):
            tech.gateway = gateway_match.group(1) or gateway_match.group(2) or ""
        if wg_match := self.WEIGHT_GROUPS_REGEX.search(content):
            wg_block = self._extract_braced_block(content, wg_match.end())
            if wg_block:
                tech.weight_groups = self.WORD_REGEX.findall(wg_block)
        if mw_match := self.MOD_WEIGHT_GROUP_REGEX.search(content):
            mw_block = self._extract_braced_block(content, mw_match.end())
            if mw_block:
                tech.mod_weight_if_group_picked = self._parse_simple_assignment_block(mw_block)
        if ff_match := self.FEATURE_FLAGS_REGEX.search(content):
            ff_block = self._extract_braced_block(content, ff_match.end())
            if ff_block:
                tech.feature_flags = self.WORD_REGEX.findall(ff_block)
        if wm_match := self.WEIGHT_MODIFIER_REGEX.search(content):
            wm_block = self._extract_braced_block(content, wm_match.end())
            if wm_block:
                tech.weight_modifier_script = self._clean_script_block(wm_block)
        if ai_match := self.AI_WEIGHT_REGEX.search(content):
            ai_block = self._extract_braced_block(content, ai_match.end())
            if ai_block:
                tech.ai_weight_script = self._clean_script_block(ai_block)
        tech.is_dangerous_tech = tech.is_dangerous_tech or bool(self.DANGEROUS_TECH_REGEX.search(content))
        tech.is_repeatable_tech = tech.is_repeatable_tech or bool(self.REPEATABLE_TECH_REGEX.search(content))
        self._parse_variant_swaps(tech, content)

    def scan_all_tech_descriptions(self):
        self._scan_language_descriptions(self.target_language_code)

    def _scan_language_descriptions(self, lang_code: str):
        lang_key_prefix = f"l_{lang_code}"
        pattern = f"*{lang_key_prefix}*.yml"
        found_tracker = {}
        base_loc_path = Path(self.base_game_path) / 'localisation'
        if base_loc_path.exists():
            for yml_file in base_loc_path.rglob(pattern):
                try:
                    self._parse_description_file_generic(yml_file, lang_code, found_tracker)
                except Exception:
                    pass
        mod_folder = Path(self.mod_folder_path)
        local_mod_folder = Path(self.local_mod_folder_path) if getattr(self, 'local_mod_folder_path', '') else None
        scanned_priority: Set[str] = set()

        def scan_localisation_dirs(paths: List[Tuple[str, Path]]):
            for _, loc_dir in paths:
                for yml_file in loc_dir.rglob(pattern):
                    try:
                        self._parse_description_file_generic(yml_file, lang_code, found_tracker)
                    except Exception:
                        pass

        if self.priority_localization_mod_ids:
            priority_ids = [
                mod_id for mod_id in self.priority_localization_mod_ids
                if mod_id in self.enabled_mod_ids
            ]
            priority_paths, _, _ = self._collect_mod_subdirs(priority_ids, mod_folder, ("localisation",))
            scan_localisation_dirs(priority_paths)
            scanned_priority.update(mod_id for mod_id, _ in priority_paths)

        workshop_paths, _, _ = self._collect_mod_subdirs(
            getattr(self, 'workshop_mod_ids', []),
            mod_folder,
            ("localisation",),
            skip_ids=scanned_priority,
        )
        scan_localisation_dirs(workshop_paths)

        local_paths, _, _ = self._collect_mod_subdirs(
            getattr(self, 'local_mod_ids', []),
            local_mod_folder,
            ("localisation",),
            skip_ids=scanned_priority,
        )
        scan_localisation_dirs(local_paths)

    def _parse_description_file_generic(self, filepath: Path, lang_code: str, found_tracker: Optional[dict]):
        content = self._read_file_with_encoding(filepath)
        if not content:
            return
        polity_suffixes = getattr(self, 'polity_description_suffixes', [])
        variant_set = getattr(self, 'variant_tech_ids', None)
        polity_variant_map = getattr(self, 'polity_variant_map', None)
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = self.DESCRIPTION_LOCALIZATION_REGEX.match(line)
            if not match:
                continue
            desc_key = match.group(1)
            description = self._clean_description_text(match.group(2))
            base_tech_id = ''
            suffix_label = None
            for suffix in polity_suffixes:
                suffix_token = f'_desc_{suffix}'
                if desc_key.endswith(suffix_token):
                    base_tech_id = desc_key[:-len(suffix_token)]
                    suffix_label = suffix
                    break
            if not base_tech_id:
                if desc_key.endswith('_desc'):
                    base_tech_id = desc_key[:-len('_desc')]
                else:
                    continue
            if not base_tech_id:
                continue
            target_tech_id = base_tech_id if suffix_label is None else f"{base_tech_id}_{suffix_label}"
            if base_tech_id not in self.all_technologies:
                if variant_set is None or target_tech_id not in variant_set:
                    continue
            if found_tracker is not None and target_tech_id in found_tracker:
                continue
            if target_tech_id not in self.tech_descriptions:
                self.tech_descriptions[target_tech_id] = {}
            self.tech_descriptions[target_tech_id][lang_code] = description
            if found_tracker is not None:
                found_tracker[target_tech_id] = True
            if variant_set is not None:
                variant_set.add(target_tech_id)
            if suffix_label and polity_variant_map is not None:
                polity_variant_map.setdefault(base_tech_id, set()).add(target_tech_id)

    def _parse_simple_assignment_block(self, block: str) -> Dict[str, str]:
        assignments: Dict[str, str] = {}
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            assignments[key] = value
        return assignments

    def _clean_script_block(self, block: str) -> str:
        parts = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            parts.append(line)
        return ' '.join(parts)

    def _clean_description_text(self, description: str) -> str:
        description = description.replace('\\"', '"').replace('\\n', ' ').replace('\\t', ' ')
        return self.WHITESPACE_CLEANUP_REGEX.sub(' ', description).strip()
