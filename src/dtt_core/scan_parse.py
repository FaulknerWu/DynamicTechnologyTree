import re
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from models import Technology

if TYPE_CHECKING:  # pragma: no cover
    from config import EnabledModIds, GeneratorConfig


class FileReadError(RuntimeError):
    def __init__(self, path: Path, exc: BaseException) -> None:
        super().__init__(f"failed to read {path}: {type(exc).__name__}: {exc}")
        self.path = path
        self.original_exception = exc


class ScanParseCore:
    TECH_DEFINITION_REGEX = re.compile(r"(?m)^(\w+)\s*=\s*\{")
    PREREQUISITES_REGEX = re.compile(r"prerequisites\s*=\s*\{")
    DANGEROUS_TECH_REGEX = re.compile(r"is_dangerous\s*=\s*yes")
    REPEATABLE_TECH_REGEX = re.compile(r"is_repeatable\s*=\s*yes")
    TECH_SWAP_REGEX = re.compile(r"technology_swap\s*=\s*\{")
    SWAP_NAME_REGEX = re.compile(r'name\s*=\s*(?:"([^"\n]+)"|([@\w\.]+))')
    SWAP_TRIGGER_REGEX = re.compile(r"trigger\s*=\s*\{")
    RESEARCH_AREA_REGEX = re.compile(r"area\s*=\s*(\w+)")
    TIER_REGEX = re.compile(r"tier\s*=\s*(\d+)")
    STARTING_TECH_REGEX = re.compile(r"start_tech\s*=\s*yes")
    TECH_ID_REGEX = re.compile(r'"([^"]+)"|(\w+)')
    DESCRIPTION_LOCALIZATION_REGEX = re.compile(
        r'^\s*([a-zA-Z0-9_]+_desc(?:_[a-zA-Z0-9_]+)*):(?:\d+)?\s*"([^\"]*(?:\\.[^\"]*)*)"',
        re.IGNORECASE,
    )
    WHITESPACE_CLEANUP_REGEX = re.compile(r"\s+")
    LEVELS_REGEX = re.compile(r"levels\s*=\s*(-?\d+)")

    # Avoid log spam: keep only the first few failures per scan.
    _MAX_FAILURE_EXAMPLES = 10

    def __init__(
        self,
        *,
        config: "GeneratorConfig",
        enabled_mods: "EnabledModIds",
        current_mod_folder_name: str,
        localize,
        all_technologies: Dict[str, Technology],
        base_game_tech_ids: Set[str],
        tech_descriptions: Dict[str, Dict[str, str]],
        variant_trigger_overrides: Dict[str, Dict[str, str]],
        polity_variant_map: Dict[str, Set[str]],
        variant_tech_ids: Set[str],
    ) -> None:
        self.config = config
        self.enabled_mods = enabled_mods
        self.current_mod_folder_name = current_mod_folder_name
        self._l = localize

        self.all_technologies = all_technologies
        self.base_game_tech_ids = base_game_tech_ids
        self.tech_descriptions = tech_descriptions
        self.variant_trigger_overrides = variant_trigger_overrides
        self.polity_variant_map = polity_variant_map
        self.variant_tech_ids = variant_tech_ids

        self._reset_scan_reports()

    def _reset_scan_reports(self) -> None:
        # Tech scan
        self._tech_scan_total_files = 0
        self._tech_scan_ok_files = 0
        self._tech_scan_failed_files = 0
        self._tech_scan_failure_examples: list[tuple[str, str]] = []

        # Localization scan
        self._loc_scan_total_files = 0
        self._loc_scan_ok_files = 0
        self._loc_scan_failed_files = 0
        self._loc_scan_failure_examples: list[tuple[str, str]] = []

        # Shared file-read failures (reset per stage)
        self._read_failed_files = 0
        self._read_failure_examples: list[tuple[str, str]] = []

    def _record_failure(self, *, kind: str, path: Path, exc: BaseException) -> None:
        if kind == "tech":
            self._tech_scan_failed_files += 1
            examples = self._tech_scan_failure_examples
        else:
            self._loc_scan_failed_files += 1
            examples = self._loc_scan_failure_examples

        if len(examples) < self._MAX_FAILURE_EXAMPLES:
            examples.append((str(path), f"{type(exc).__name__}: {exc}"))

    def _print_scan_report(self, *, kind: str) -> None:
        if kind == "tech":
            total = self._tech_scan_total_files
            ok = self._tech_scan_ok_files
            failed = self._tech_scan_failed_files
            examples = self._tech_scan_failure_examples
            summary_key = "warn_tech_parse_summary"
            example_key = "warn_tech_parse_failure_example"
        else:
            total = self._loc_scan_total_files
            ok = self._loc_scan_ok_files
            failed = self._loc_scan_failed_files
            examples = self._loc_scan_failure_examples
            summary_key = "warn_loc_parse_summary"
            example_key = "warn_loc_parse_failure_example"

        if total:
            suppressed = max(failed - len(examples), 0)
            print(
                self._l(
                    summary_key,
                    total=total,
                    ok=ok,
                    failed=failed,
                    shown=len(examples),
                    suppressed=suppressed,
                )
            )
            for path_str, err_str in examples:
                print(self._l(example_key, path=path_str, error=err_str))

        if self._read_failed_files:
            suppressed = max(
                self._read_failed_files - len(self._read_failure_examples), 0
            )
            print(
                self._l(
                    "warn_read_file_failed_summary",
                    failed=self._read_failed_files,
                    shown=len(self._read_failure_examples),
                    suppressed=suppressed,
                )
            )
            for path_str, err_str in self._read_failure_examples:
                print(
                    self._l(
                        "warn_read_file_failed_example", path=path_str, error=err_str
                    )
                )

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
        self._reset_scan_reports()
        self._scan_technology_path(
            Path(self.config.paths.base_game_path) / "common" / "technology"
        )
        if self.base_game_tech_ids is not None:
            self.base_game_tech_ids.clear()
            self.base_game_tech_ids.update(self.all_technologies.keys())

        workshop_root = Path(self.config.paths.mod_folder_path)
        local_mod_path = self.config.paths.local_mod_folder_path
        local_root = Path(local_mod_path) if local_mod_path else None
        scanned_count = 0
        missing_mod_dirs: List[str] = []

        def process_mod_roots(mod_ids: List[str], root: Optional[Path]):
            nonlocal scanned_count
            paths, missing_mods, _ = self._collect_mod_subdirs(
                mod_ids, root, ("common", "technology")
            )
            missing_mod_dirs.extend(missing_mods)
            for _, tech_path in paths:
                new_techs = self._scan_technology_path(tech_path)
                if new_techs > 0:
                    scanned_count += 1

        workshop_ids = self.enabled_mods.workshop_ids
        local_ids = self.enabled_mods.local_ids
        process_mod_roots(workshop_ids, workshop_root)
        process_mod_roots(local_ids, local_root)
        if missing_mod_dirs:
            print(self._l("msg_missing_mod_dirs", count=len(missing_mod_dirs)))
        print(self._l("msg_mods_with_new_techs", count=scanned_count))

        self._print_scan_report(kind="tech")

    def _scan_technology_path(self, path: Path) -> int:
        if not path.exists():
            return 0
        before_count = len(self.all_technologies)
        for file_path in path.glob("*.txt"):
            self._tech_scan_total_files += 1
            try:
                self._parse_single_tech_file(file_path)
                self._tech_scan_ok_files += 1
            except Exception as exc:
                self._record_failure(kind="tech", path=file_path, exc=exc)
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
                self._parse_tech_block_content(
                    self.all_technologies[tech_id], tech_block
                )

    def _read_file_with_encoding(self, filepath: Path) -> str:
        try:
            return filepath.read_text(encoding="utf-8-sig", errors="ignore")
        except FileNotFoundError:
            # Treat as missing file; caller decides whether this matters.
            return ""
        except OSError as exc:
            # Keep going but make it observable.
            self._read_failed_files += 1
            if len(self._read_failure_examples) < self._MAX_FAILURE_EXAMPLES:
                self._read_failure_examples.append(
                    (str(filepath), f"{type(exc).__name__}: {exc}")
                )
            raise FileReadError(filepath, exc) from exc
        except Exception:
            # Fallback encoding attempt.
            try:
                return filepath.read_text(encoding="utf-8", errors="ignore")
            except Exception as exc:
                self._read_failed_files += 1
                if len(self._read_failure_examples) < self._MAX_FAILURE_EXAMPLES:
                    self._read_failure_examples.append(
                        (str(filepath), f"{type(exc).__name__}: {exc}")
                    )
                raise FileReadError(filepath, exc) from exc

    def _remove_comments_from_content(self, content: str) -> str:
        lines = []
        for line in content.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if "#" in line:
                line = line.split("#", 1)[0]
            lines.append(line)
        return "\n".join(lines)

    def _extract_braced_block(self, content: str, start_pos: int) -> str:
        brace_depth = 1
        for i, char in enumerate(content[start_pos:], start_pos):
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    return content[start_pos:i]
        return ""

    def _parse_variant_swaps(self, tech: Technology, content: str) -> None:
        triggers = self.config.tech.variant_triggers
        if not triggers:
            return
        # Build patterns for each (trigger_name, expected_value) pair
        # Key format: trigger_name for boolean, "trigger_name=value" for parameterized
        compiled_patterns = {}
        for trigger_name, expected_value in triggers:
            if expected_value.lower() == "yes":
                # Boolean trigger: match "yes" or "1"
                pattern = re.compile(
                    rf"\b{re.escape(trigger_name)}\b\s*=\s*(?:yes|1)", re.IGNORECASE
                )
                key = trigger_name
            else:
                # Parameterized trigger: match specific value
                pattern = re.compile(
                    rf"\b{re.escape(trigger_name)}\b\s*=\s*{re.escape(expected_value)}",
                    re.IGNORECASE,
                )
                key = f"{trigger_name}={expected_value}"
            compiled_patterns[key] = pattern
        search_pos = 0
        while True:
            match = self.TECH_SWAP_REGEX.search(content, search_pos)
            if not match:
                break
            brace_index = content.find("{", match.start())
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
            trigger_block = ""
            if trigger_match:
                trig_brace_index = block.find("{", trigger_match.start())
                if trig_brace_index != -1:
                    trigger_block = self._extract_braced_block(
                        block, trig_brace_index + 1
                    )
            if not trigger_block or not swap_name:
                search_pos = brace_index + len(block) + 1
                continue
            for trigger, pattern in compiled_patterns.items():
                if trigger in tech.variants:
                    continue
                if pattern.search(trigger_block):
                    tech.variants[trigger] = swap_name
                    if swap_name:
                        variant_ids = self.variant_tech_ids
                        if variant_ids is None:
                            variant_ids = set()
                            self.variant_tech_ids = variant_ids
                        variant_ids.add(swap_name)
                        trigger_overrides = self.variant_trigger_overrides
                        if trigger_overrides is not None:
                            trigger_overrides.setdefault(trigger, {})[tech.tech_id] = (
                                swap_name
                            )
            search_pos = brace_index + len(block) + 1

    def _parse_tech_block_content(self, tech: Technology, content: str):
        """Parse technology block and populate tech attributes."""
        self._parse_basic_attributes(tech, content)
        self._parse_levels_repeatable_flag(tech, content)
        self._parse_boolean_flags(tech, content)
        self._parse_variant_swaps(tech, content)

    def _parse_basic_attributes(self, tech: Technology, content: str) -> None:
        if area_match := self.RESEARCH_AREA_REGEX.search(content):
            tech.research_area = area_match.group(1)
        if tier_match := self.TIER_REGEX.search(content):
            tech.tier_level = int(tier_match.group(1))
        if m := self.PREREQUISITES_REGEX.search(content):
            block = self._extract_braced_block(content, m.end())
            tech_matches = self.TECH_ID_REGEX.findall(block)
            tech.prerequisite_tech_ids = [
                m_id if m_id else w_id for m_id, w_id in tech_matches
            ]
        if self.STARTING_TECH_REGEX.search(content):
            tech.prerequisite_tech_ids = []

    def _parse_levels_repeatable_flag(self, tech: Technology, content: str) -> None:
        if levels_match := self.LEVELS_REGEX.search(content):
            try:
                levels = int(levels_match.group(1))
            except ValueError:
                levels = None
            if levels == -1:
                tech.is_repeatable_tech = True

    def _parse_boolean_flags(self, tech: Technology, content: str) -> None:
        """Parse: is_dangerous, is_repeatable (start_tech handled in basic)."""
        tech.is_dangerous_tech = tech.is_dangerous_tech or bool(
            self.DANGEROUS_TECH_REGEX.search(content)
        )
        tech.is_repeatable_tech = tech.is_repeatable_tech or bool(
            self.REPEATABLE_TECH_REGEX.search(content)
        )

    def scan_all_tech_descriptions(self):
        self._reset_scan_reports()
        self._scan_language_descriptions(self.config.localization.target_language_code)
        self._print_scan_report(kind="loc")

    def _scan_language_descriptions(self, lang_code: str):
        lang_key_prefix = f"l_{lang_code}"
        pattern = f"*{lang_key_prefix}*.yml"
        found_tracker = {}
        base_loc_path = Path(self.config.paths.base_game_path) / "localisation"
        if base_loc_path.exists():
            for yml_file in base_loc_path.rglob(pattern):
                self._loc_scan_total_files += 1
                try:
                    self._parse_description_file_generic(
                        yml_file, lang_code, found_tracker
                    )
                    self._loc_scan_ok_files += 1
                except Exception as exc:
                    self._record_failure(kind="loc", path=yml_file, exc=exc)
        mod_folder = Path(self.config.paths.mod_folder_path)
        local_mod_path = self.config.paths.local_mod_folder_path
        local_mod_folder = Path(local_mod_path) if local_mod_path else None
        scanned_priority: Set[str] = set()

        def scan_localisation_dirs(paths: List[Tuple[str, Path]]):
            for _, loc_dir in paths:
                for yml_file in loc_dir.rglob(pattern):
                    self._loc_scan_total_files += 1
                    try:
                        self._parse_description_file_generic(
                            yml_file, lang_code, found_tracker
                        )
                        self._loc_scan_ok_files += 1
                    except Exception as exc:
                        self._record_failure(kind="loc", path=yml_file, exc=exc)

        if self.config.localization.priority_localization_mod_ids:
            priority_ids = [
                mod_id
                for mod_id in self.config.localization.priority_localization_mod_ids
                if mod_id in self.enabled_mods.all_ids
            ]
            priority_paths, _, _ = self._collect_mod_subdirs(
                priority_ids, mod_folder, ("localisation",)
            )
            scan_localisation_dirs(priority_paths)
            scanned_priority.update(mod_id for mod_id, _ in priority_paths)

        workshop_paths, _, _ = self._collect_mod_subdirs(
            self.enabled_mods.workshop_ids,
            mod_folder,
            ("localisation",),
            skip_ids=scanned_priority,
        )
        scan_localisation_dirs(workshop_paths)

        local_paths, _, _ = self._collect_mod_subdirs(
            self.enabled_mods.local_ids,
            local_mod_folder,
            ("localisation",),
            skip_ids=scanned_priority,
        )
        scan_localisation_dirs(local_paths)

    def _parse_description_file_generic(
        self, filepath: Path, lang_code: str, found_tracker: Optional[dict]
    ):
        content = self._read_file_with_encoding(filepath)
        if not content:
            return
        polity_suffixes = self.config.tech.polity_description_suffixes
        variant_set = self.variant_tech_ids
        polity_variant_map = self.polity_variant_map
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = self.DESCRIPTION_LOCALIZATION_REGEX.match(line)
            if not match:
                continue
            desc_key = match.group(1)
            description = self._clean_description_text(match.group(2))
            base_tech_id = ""
            suffix_label = None
            for suffix in polity_suffixes:
                suffix_token = f"_desc_{suffix}"
                if desc_key.endswith(suffix_token):
                    base_tech_id = desc_key[: -len(suffix_token)]
                    suffix_label = suffix
                    break
            if not base_tech_id:
                if desc_key.endswith("_desc"):
                    base_tech_id = desc_key[: -len("_desc")]
                else:
                    continue
            if not base_tech_id:
                continue
            target_tech_id = (
                base_tech_id
                if suffix_label is None
                else f"{base_tech_id}_{suffix_label}"
            )
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

    def _clean_description_text(self, description: str) -> str:
        description = (
            description.replace('\\"', '"').replace("\\n", " ").replace("\\t", " ")
        )
        return self.WHITESPACE_CLEANUP_REGEX.sub(" ", description).strip()
