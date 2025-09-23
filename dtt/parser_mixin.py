import re
from pathlib import Path
from typing import Dict, List, Optional

from .models import Technology
from .localization import LOCALIZATION_STRINGS  # may be used in future extensions


class ParserMixin:
    # Regex patterns (copied from original script)
    TECH_DEFINITION_REGEX = re.compile(r'(?m)^(\w+)\s*=\s*\{')
    PREREQUISITES_REGEX = re.compile(r'prerequisites\s*=\s*\{')
    COST_REGEX = re.compile(r'cost\s*=\s*([@\w\d]+)')
    CATEGORY_REGEX = re.compile(r'category\s*=\s*\{')
    POTENTIAL_REGEX = re.compile(r'(?:potential|starting_potential)\s*=\s*\{')
    DANGEROUS_TECH_REGEX = re.compile(r'is_dangerous\s*=\s*yes')
    REPEATABLE_TECH_REGEX = re.compile(r'is_repeatable\s*=\s*yes')
    RESEARCH_AREA_REGEX = re.compile(r'area\s*=\s*(\w+)')
    TIER_REGEX = re.compile(r'tier\s*=\s*(\d+)')
    STARTING_TECH_REGEX = re.compile(r'start_tech\s*=\s*yes')
    TECH_ID_REGEX = re.compile(r'"([^"]+)"|(\w+)')
    WORD_REGEX = re.compile(r'[\w_]+')
    DESCRIPTION_LOCALIZATION_REGEX = re.compile(r'^\s*([a-zA-Z0-9_]+_desc):(?:\d+)?\s*"([^"]*(?:\\.[^"]*)*)"', re.IGNORECASE)
    WHITESPACE_CLEANUP_REGEX = re.compile(r'\s+')

    def scan_all_technology_files(self):
        self._scan_technology_path(Path(self.base_game_path) / "common" / "technology")
        self.base_game_tech_ids = set(self.all_technologies.keys())

        # Scan workshop mods
        workshop_root = Path(self.mod_folder_path)
        local_root = Path(self.local_mod_folder_path) if getattr(self, 'local_mod_folder_path', '') else None
        scanned_count = 0
        missing_mod_dirs: List[str] = []
        missing_tech_dirs: List[str] = []

        def scan_root(root: Path, mod_ids: List[str]):
            nonlocal scanned_count
            if not root or not root.exists():
                return
            for mod_id in mod_ids:
                if mod_id == self.current_mod_folder_name:
                    continue
                mod_dir = root / mod_id
                if not mod_dir.is_dir():
                    missing_mod_dirs.append(mod_id)
                    continue
                tech_path = mod_dir / "common" / "technology"
                if not tech_path.exists():
                    missing_tech_dirs.append(mod_id)
                    continue
                new_techs = self._scan_technology_path(tech_path)
                if new_techs > 0:
                    scanned_count += 1

        # Attributes set in configuration loader
        workshop_ids = getattr(self, 'workshop_mod_ids', [])
        local_ids = getattr(self, 'local_mod_ids', [])
        scan_root(workshop_root, workshop_ids)
        scan_root(local_root, local_ids)
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
        tech.is_dangerous_tech = tech.is_dangerous_tech or bool(self.DANGEROUS_TECH_REGEX.search(content))
        tech.is_repeatable_tech = tech.is_repeatable_tech or bool(self.REPEATABLE_TECH_REGEX.search(content))

    # Description scanning
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
        scanned_priority = set()
        if mod_folder.exists() and self.priority_localization_mod_ids:
            for mod_id in self.priority_localization_mod_ids:
                if mod_id not in self.enabled_mod_ids:
                    continue
                if mod_id == self.current_mod_folder_name:
                    continue
                mod_dir = mod_folder / mod_id / 'localisation'
                if mod_dir.exists():
                    for yml_file in mod_dir.rglob(pattern):
                        try:
                            self._parse_description_file_generic(yml_file, lang_code, found_tracker)
                        except Exception:
                            pass
                    scanned_priority.add(mod_id)

        def scan_loc(root: Path, mod_ids: List[str]):
            if not root or not root.exists():
                return
            for mod_id in mod_ids:
                if mod_id in scanned_priority:
                    continue
                if mod_id == self.current_mod_folder_name:
                    continue
                mod_dir = root / mod_id / 'localisation'
                if mod_dir.exists():
                    for yml_file in mod_dir.rglob(pattern):
                        try:
                            self._parse_description_file_generic(yml_file, lang_code, found_tracker)
                        except Exception:
                            pass

        # First the remaining workshop mods
        scan_loc(mod_folder, getattr(self, 'workshop_mod_ids', []))
        # Then local mods
        scan_loc(local_mod_folder, getattr(self, 'local_mod_ids', []))

    def _parse_description_file_generic(self, filepath: Path, lang_code: str, found_tracker: Optional[dict]):
        content = self._read_file_with_encoding(filepath)
        if not content:
            return
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = self.DESCRIPTION_LOCALIZATION_REGEX.match(line)
            if not match:
                continue
            desc_key = match.group(1)
            description = self._clean_description_text(match.group(2))
            tech_id = desc_key.replace('_desc', '')
            if tech_id in self.all_technologies:
                if found_tracker is not None and tech_id in found_tracker:
                    continue
                if tech_id not in self.tech_descriptions:
                    self.tech_descriptions[tech_id] = {}
                self.tech_descriptions[tech_id][lang_code] = description
                if found_tracker is not None:
                    found_tracker[tech_id] = True

    def _clean_description_text(self, description: str) -> str:
        description = description.replace('\\"', '"').replace('\\n', ' ').replace('\\t', ' ')
        return self.WHITESPACE_CLEANUP_REGEX.sub(' ', description).strip()
