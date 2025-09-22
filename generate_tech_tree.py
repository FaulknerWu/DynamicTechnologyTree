"""
Stellaris Dynamic Technology Tree Generator
"""

import re
import configparser
import json
import sys
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List
from collections import Counter


@dataclass
class Technology:
    tech_id: str
    research_area: str = ""
    tier_level: int = 0
    prerequisite_tech_ids: List[str] = field(default_factory=list)
    unlocked_tech_ids: List[str] = field(default_factory=list)
    is_dangerous_tech: bool = False
    is_repeatable_tech: bool = False
    research_cost: str = ""
    tech_categories: List[str] = field(default_factory=list)
    unlock_conditions: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        dangerous_tech_list = {
            "tech_synthetic_workers", "tech_sapient_ai", "tech_positronic_ai",
            "tech_mega_engineering", "tech_colossus", "tech_juggernaut"
        }
        self.is_dangerous_tech = self.tech_id in dangerous_tech_list
        self.is_repeatable_tech = "repeatable" in self.tech_id


class TechTreeGenerator:
    
    # 研究领域对应的图标（游戏内富文本标记），用于在最终描述中渲染小图标
    RESEARCH_AREA_ICONS = {
        "physics": "£physics£",
        "engineering": "£engineering£", 
        "society": "£society£"
    }
    
    # 受支持的语言及其YML文件头（Stellaris本地化约定）
    SUPPORTED_LANGUAGES = {
        "english": "l_english",
        "simp_chinese": "l_simp_chinese"
    }
    
    # 少量UI文案（按语言）
    LOCALIZATION_STRINGS = {
        "english": {
            "title": "Technology Tree",
            "top_level": "Maximum Level Reached",
            "requires": "Requires",
            "tier_label": "Tier:",
            "already_shown": "already shown above",
            "skip_long_tree": "Too many follow-up technologies. Not displayed for performance."
        },
        "simp_chinese": {
            "title": "科技树",
            "top_level": "已达到顶级", 
            "requires": "还需",
            "tier_label": "级别:",
            "already_shown": "已在上方展示",
            "skip_long_tree": "后续科技太多，性能原因不做展示"
        }
    }
    
    # 解析科技文件所用的核心正则：
    # - TECH_DEFINITION_REGEX：匹配 tech_id = { 的起始位置
    # - 其余正则匹配常见键，如 prerequisites/cost/category/potential 等
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

    def __init__(self, config_path: str):
        self.all_technologies: Dict[str, Technology] = {}
        self.base_game_tech_ids = set()
        self.tech_descriptions: Dict[str, Dict[str, str]] = {}
        self.base_game_path, self.mod_folder_path, self.dlc_load_json_path, self.localization_mod_list = self._load_configuration(config_path)

        self.current_mod_folder_name = Path(__file__).parent.name
        # 从 dlc_load.json 读取当前启用的 MOD 列表（Steam workshop id 对应目录名）
        self.enabled_mod_ids = self._load_enabled_mod_ids_from_dlc_load()

        self.LONG_TREE_THRESHOLD = 100
        self.overlong_tech_ids = set()

        
    def _load_configuration(self, config_path: str) -> tuple:
    # 从 config.ini 读取：
    # - 游戏本体路径 base_game_path
    # - MOD 根目录路径 mod_folder_path
    # 其余过滤/汉化集中化配置已废弃，统一使用 dlc_load.json 的 enabled_mods 自动识别
        config = configparser.ConfigParser()
        config.read(config_path, encoding='utf-8')
        
        try:
            base_path = config.get('paths', 'base_game_path')
            mod_path = config.get('paths', 'mod_folder_path')
            dlc_path_cfg = config.get('paths', 'dlc_load_path', fallback='').strip()
            # 可选集中汉化 MOD 列表
            centralized_str = ''
            if config.has_section('chinese_localization'):
                centralized_str = config.get('chinese_localization', 'centralized_mods', fallback='').strip()
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            raise ValueError(f"配置文件缺少必需的配置项: {e}")
        # 若未配置，自行推断（Windows 默认用户文档路径）；其它平台提示需要配置
        if not dlc_path_cfg:
            if os.name == 'nt':
                dlc_path = str(Path.home() / 'Documents' / 'Paradox Interactive' / 'Stellaris' / 'dlc_load.json')
            else:
                print("提示: 非 Windows 系统且未在 config.ini 中设置 dlc_load_path, 请手动配置该路径。")
                dlc_path = ''
        else:
            dlc_path = dlc_path_cfg
        localization_mod_list: List[str] = []
        if centralized_str:
            localization_mod_list = [m.strip() for m in centralized_str.split(',') if m.strip()]
        if localization_mod_list:
            # 不再输出具体MOD ID，仅提示已配置
            print(f"汉化优先MOD数量: {len(localization_mod_list)}")
        return base_path, mod_path, dlc_path, localization_mod_list

    def _load_enabled_mod_ids_from_dlc_load(self) -> List[str]:
        # Paradox 启用的 mod 列表在用户文档目录 dlc_load.json 中，形如 "mod/ugc_123456789.mod"
        # 需要取出数字 ID，然后在 workshop 目录下找到对应文件夹（目录名即数字 ID）
        # Windows 上路径示例： C:/Users/<User>/Documents/Paradox Interactive/Stellaris/dlc_load.json
        try:
            if self.dlc_load_json_path:
                dlc_json_path = Path(self.dlc_load_json_path)
            else:
                # 没有可用路径直接返回空
                return []
            if not dlc_json_path.exists():
                print(f"警告: 找不到 dlc_load.json: {dlc_json_path}")
                return []
            data = json.loads(dlc_json_path.read_text(encoding='utf-8'))
            enabled = data.get('enabled_mods', [])
            mod_ids: List[str] = []
            for entry in enabled:
                # 形如 mod/ugc_1995601384.mod
                name = Path(entry).name  # ugc_1995601384.mod
                if name.startswith('ugc_') and name.endswith('.mod'):
                    num_part = name[len('ugc_'):-len('.mod')]
                    if num_part.isdigit():
                        mod_ids.append(num_part)
            # 不输出具体启用 MOD ID 列表，仅打印数量
            print(f"启用MOD数量: {len(mod_ids)}")
            return mod_ids
        except Exception as e:
            print(f"警告: 读取 dlc_load.json 失败: {e}")
            return []
    
    # 以下旧的过滤与集中汉化逻辑已移除：统一根据 dlc_load.json 中 enabled_mods 决定扫描集合
        
    def scan_all_technology_files(self):
    # 扫描顺序：先本体，再MOD；用于随后统计“本体/非本体”的科技数量
        self._scan_technology_path(Path(self.base_game_path) / "common" / "technology", "游戏本体科技文件")
        self.base_game_tech_ids = set(self.all_technologies.keys())
        
        mod_folder = Path(self.mod_folder_path)
        if mod_folder.exists():
            scanned_count = 0
            missing_mod_dirs: List[str] = []           # dlc_load中有，但目录不存在
            missing_tech_dirs: List[str] = []          # 目录存在，但没有 common/technology
            for mod_id in self.enabled_mod_ids:
                if mod_id == self.current_mod_folder_name:
                    continue
                mod_dir = mod_folder / mod_id
                if not mod_dir.is_dir():
                    missing_mod_dirs.append(mod_id)
                    continue
                mod_tech_path = mod_dir / "common" / "technology"
                if not mod_tech_path.exists():
                    missing_tech_dirs.append(mod_id)
                    continue
                new_techs = self._scan_technology_path(mod_tech_path, f"MOD科技文件 {mod_id}")
                if new_techs > 0:
                    scanned_count += 1

            if missing_mod_dirs:
                print(f"提示: 有 {len(missing_mod_dirs)} 个启用MOD目录缺失")
            print(f"提示: 有 {scanned_count} 个启用MOD有新增科技")
        
    def _scan_technology_path(self, path: Path, description: str) -> int:
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
    # 读取并去掉注释后，按“tech_id = { ... }”为单位切片，再解析每个区块
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
        except:
            try:
                return filepath.read_text(encoding='utf-8', errors='ignore')
            except:
                return ""

    def _remove_comments_from_content(self, content: str) -> str:
    # Stellaris脚本以 # 为行内注释，此处粗略去除注释，保留注释前的内容
        lines = []
        for line in content.splitlines():
            if line.lstrip().startswith('#'):
                continue
            if '#' in line:
                line = line.split('#', 1)[0]
            lines.append(line)
        return '\n'.join(lines)

    def _extract_braced_block(self, content: str, start_pos: int) -> str:
    # 从 start_pos 开始，假设当前位置紧随一个“{”，使用括号深度计数法，查找与之匹配的“}”
    # 返回不包含首尾大括号的内部文本；若未能闭合（括号不匹配），返回空字符串
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
    # 逐项解析科技区块内的键：
    # - area / tier / prerequisites / cost / category / (starting_)potential
    # - is_dangerous / is_repeatable（也可以由ID或显式标记获得）
        if area_match := self.RESEARCH_AREA_REGEX.search(content):
            tech.research_area = area_match.group(1)
        
        if tier_match := self.TIER_REGEX.search(content):
            tech.tier_level = int(tier_match.group(1))
        
        if m := self.PREREQUISITES_REGEX.search(content):
            block = self._extract_braced_block(content, m.end())
            tech_matches = self.TECH_ID_REGEX.findall(block)
            tech.prerequisite_tech_ids = [m_id if m_id else w_id for m_id, w_id in tech_matches]
        
        if self.STARTING_TECH_REGEX.search(content):
            # 起始科技明确无前置
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
    
    def scan_all_tech_descriptions(self):
        self._scan_english_tech_descriptions()
        self._scan_chinese_tech_descriptions()

    def _scan_english_tech_descriptions(self):
    # 先从本体 localisation 提取英文描述，再扫描MOD；
    # 非本体的英文描述也会回填到中文缺省，以便至少有英文文案可用
        base_localisation_path = Path(self.base_game_path) / "localisation"
        if base_localisation_path.exists():
            files = list(base_localisation_path.rglob("*l_english*.yml"))
            if files:
                for yml_file in files:
                    try:
                        self._parse_english_description_file(yml_file, is_base_game=True)
                    except Exception:
                        pass
        
        mod_folder = Path(self.mod_folder_path)
        if mod_folder.exists():
            for mod_id in self.enabled_mod_ids:
                if mod_id == self.current_mod_folder_name:
                    continue
                mod_dir = mod_folder / mod_id
                if mod_dir.is_dir():
                    mod_localisation_path = mod_dir / "localisation"
                    if mod_localisation_path.exists():
                        self._scan_mod_english_localization_files(mod_localisation_path)

    def _scan_chinese_tech_descriptions(self):
    # 中文描述的优先级：本体 -> 配置的集中汉化MOD(与启用列表求交集) -> 其余启用MOD
        found_chinese_descriptions = {}
        
        base_localisation_path = Path(self.base_game_path) / "localisation"
        if base_localisation_path.exists():
            files = list(base_localisation_path.rglob("*l_simp_chinese*.yml"))
            if files:
                for yml_file in files:
                    try:
                        self._parse_chinese_description_file(yml_file, found_chinese_descriptions)
                    except Exception:
                        pass
        
        mod_folder = Path(self.mod_folder_path)
        if mod_folder.exists():
            # 1) 集中汉化优先
            prioritized = []
            if hasattr(self, 'localization_mod_list') and self.localization_mod_list:
                prioritized = [m for m in self.localization_mod_list if m in self.enabled_mod_ids]
            scanned_set = set()
            for mod_id in prioritized:
                if mod_id == self.current_mod_folder_name:
                    continue
                mod_dir = mod_folder / mod_id
                if mod_dir.is_dir():
                    loc_path = mod_dir / 'localisation'
                    if loc_path.exists():
                        self._scan_chinese_localization_files(loc_path, found_chinese_descriptions)
                        scanned_set.add(mod_id)
            # 2) 其余启用 MOD
            for mod_id in self.enabled_mod_ids:
                if mod_id in scanned_set or mod_id in prioritized:
                    continue
                if mod_id == self.current_mod_folder_name:
                    continue
                mod_dir = mod_folder / mod_id
                if mod_dir.is_dir():
                    loc_path = mod_dir / 'localisation'
                    if loc_path.exists():
                        self._scan_chinese_localization_files(loc_path, found_chinese_descriptions)

    def _scan_mod_english_localization_files(self, localisation_path: Path):
        try:
            files = list(localisation_path.rglob("*l_english*.yml"))
            if files:
                for yml_file in files:
                    try:
                        self._parse_english_description_file(yml_file, is_base_game=False)
                    except Exception:
                        pass
        except Exception:
            pass

    def _scan_chinese_localization_files(self, localisation_path: Path, found_descriptions: dict) -> int:
        if not localisation_path or not localisation_path.exists():
            return 0
            
        found_count = 0
        try:
            chinese_files = list(localisation_path.rglob("*l_simp_chinese*.yml"))
            for yml_file in chinese_files:
                try:
                    found_count += self._parse_chinese_description_file(yml_file, found_descriptions)
                except Exception:
                    pass
        except Exception:
            pass
        return found_count

    def _parse_chinese_description_file(self, filepath: Path, found_descriptions: dict) -> int:
    # DESCRIPTION_LOCALIZATION_REGEX 只匹配 "xxx_desc:0 \"...\"" 形式；
    # 对每行做轻量正则提取并清洗转义字符
        content = self._read_file_with_encoding(filepath)
        if not content:
            return 0
        
        found_count = 0
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            match = self.DESCRIPTION_LOCALIZATION_REGEX.match(line)
            if match:
                desc_key = match.group(1)
                description = self._clean_description_text(match.group(2))
                tech_id = desc_key.replace('_desc', '')
                
                if (tech_id in self.all_technologies and tech_id not in found_descriptions):
                    if tech_id not in self.tech_descriptions:
                        self.tech_descriptions[tech_id] = {}
                    
                    self.tech_descriptions[tech_id]["simp_chinese"] = description
                    found_descriptions[tech_id] = True
                    found_count += 1
        
        return found_count

    def _parse_english_description_file(self, filepath: Path, is_base_game: bool):
    # 英文描述与中文逻辑相似；若来自MOD（非本体），同时作为中文的兜底文本
        content = self._read_file_with_encoding(filepath)
        if not content:
            return
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            match = self.DESCRIPTION_LOCALIZATION_REGEX.match(line)
            if match:
                desc_key = match.group(1)
                description = self._clean_description_text(match.group(2))
                tech_id = desc_key.replace('_desc', '')
                
                if tech_id in self.all_technologies:
                    if tech_id not in self.tech_descriptions:
                        self.tech_descriptions[tech_id] = {}

                    if is_base_game:
                        self.tech_descriptions[tech_id]["english"] = description
                    else:
                        self.tech_descriptions[tech_id]["english"] = description
                        self.tech_descriptions[tech_id]["simp_chinese"] = description

    def _clean_description_text(self, description: str) -> str:
    # 去除常见的转义与多余空白，保持单行
        description = description.replace('\\"', '"').replace('\\n', ' ').replace('\\t', ' ')
        return self.WHITESPACE_CLEANUP_REGEX.sub(' ', description).strip()
            
    def build_technology_tree_relationships(self):
    # 将“前置->后继”的引用补全：对每个科技A，其前置B们都追加 A 到 B.unlocked_tech_ids
        for tech in self.all_technologies.values():
            for prereq_id in tech.prerequisite_tech_ids:
                if prereq_id in self.all_technologies:
                    prereq_tech = self.all_technologies[prereq_id]
                    if tech.tech_id not in prereq_tech.unlocked_tech_ids:
                        prereq_tech.unlocked_tech_ids.append(tech.tech_id)

    # 计算某科技的唯一可达后继科技数量
    def _count_unique_successors(self, tech_id: str) -> int:
    # 使用显式栈进行有向图的可达节点计数（去重），避免递归栈过深
        if tech_id not in self.all_technologies:
            return 0
        visited = set()
        stack = list(self.all_technologies[tech_id].unlocked_tech_ids)
        while stack:
            tid = stack.pop()
            if tid in visited or tid not in self.all_technologies:
                continue
            visited.add(tid)
            stack.extend(self.all_technologies[tid].unlocked_tech_ids)
        return len(visited)

    # 预计算超长科技树集合
    def _precompute_overlong_trees(self) -> None:
    # 预先计算“后继科技数量”超过阈值的根节点，生成描述时直接给出提示，避免生成超长文本
        self.overlong_tech_ids.clear()
        for tid in self.all_technologies.keys():
            cnt = self._count_unique_successors(tid)
            if cnt > self.LONG_TREE_THRESHOLD:
                self.overlong_tech_ids.add(tid)
                        
    def _format_tech_tree_entry(self, tech_id: str, indent_level: int = 1, current_prereq: str = None, lang_code: str = "simp_chinese") -> str:
    # 将单个科技渲染为一行：包含层级缩进、领域图标、颜色以及“还需”其它并列前置的提示
        if tech_id not in self.all_technologies:
            return ""
            
        tech = self.all_technologies[tech_id]
        indent = "    " * indent_level
        
        area_icon = self.RESEARCH_AREA_ICONS.get(tech.research_area, "")
        
        if tech.is_dangerous_tech:
            formatted = f"({tech.tier_level})['technology:{tech_id}', {area_icon}§R${tech_id}$§!]"
        elif tech.tier_level >= 5 or tech.is_repeatable_tech:
            formatted = f"({tech.tier_level})['technology:{tech_id}', {area_icon}§M${tech_id}$§!]"
        else:
            formatted = f"({tech.tier_level})['technology:{tech_id}', {area_icon}§W${tech_id}$§!]"
        
        additional_prereqs = []
        if current_prereq and len(tech.prerequisite_tech_ids) > 1:
            for prereq_id in tech.prerequisite_tech_ids:
                if prereq_id != current_prereq and prereq_id in self.all_technologies:
                    prereq_tech = self.all_technologies[prereq_id]
                    prereq_area_icon = self.RESEARCH_AREA_ICONS.get(prereq_tech.research_area, "")
                    
                    if prereq_tech.is_dangerous_tech:
                        prereq_formatted = f"({prereq_tech.tier_level})['technology:{prereq_id}', {prereq_area_icon}§R${prereq_id}$§!]"
                    elif prereq_tech.tier_level >= 5 or prereq_tech.is_repeatable_tech:
                        prereq_formatted = f"({prereq_tech.tier_level})['technology:{prereq_id}', {prereq_area_icon}§M${prereq_id}$§!]"
                    else:
                        prereq_formatted = f"({prereq_tech.tier_level})['technology:{prereq_id}', {prereq_area_icon}§W${prereq_id}$§!]"
                    
                    additional_prereqs.append(prereq_formatted)
        
        entry = f"{indent}|--{formatted}"
        if additional_prereqs:
            prereq_text = " , ".join(additional_prereqs)
            requires_text = self.LOCALIZATION_STRINGS[lang_code]["requires"]
            entry += f" [§R{requires_text}§! {prereq_text}]"
        
        return entry
        
    def _build_tech_subtree(self, tech_id: str, current_depth: int = 0, parent_tech_id: str = None, lang_code: str = "simp_chinese", path_set: set | None = None, expanded_set: set | None = None) -> List[str]:
    # - path_set: 当前DFS路径节点集合，用于检测环（避免 A->...->A）；
    # - expanded_set: 从根开始已展开过子树的节点集合，避免同一节点在不同路径下重复展开；
    #   对已展开节点，仅追加一行并标注“已在上方展示”。
        if path_set is None:
            path_set = set()
        if expanded_set is None:
            expanded_set = set()

        if tech_id not in self.all_technologies:
            return []

        if tech_id in path_set:
            return []

        tech = self.all_technologies[tech_id]
        lines: List[str] = []

        path_set.add(tech_id)

        # 为了稳定与可读，按 tier 再按 tech_id 排序
        unlocked_techs = sorted(tech.unlocked_tech_ids, key=lambda tid: (
            self.all_technologies.get(tid, Technology(tid)).tier_level, tid
        ))

        already_shown_text = self.LOCALIZATION_STRINGS[lang_code].get("already_shown", "already shown")

        for unlock_id in unlocked_techs:
            base_line = self._format_tech_tree_entry(unlock_id, current_depth + 1, tech_id, lang_code)
            if not base_line:
                continue

            if (unlock_id in expanded_set) or (unlock_id in path_set):
                lines.append(f"{base_line} §g({already_shown_text})§!")
                continue

            lines.append(base_line)
            expanded_set.add(unlock_id)
            subtree_lines = self._build_tech_subtree(unlock_id, current_depth + 1, unlock_id, lang_code, path_set, expanded_set)
            lines.extend(subtree_lines)

        path_set.remove(tech_id)
        return lines
        
    def generate_tech_tree_content(self, tech_id: str, lang_code: str = "simp_chinese") -> str:
        if tech_id not in self.all_technologies:
            return ""

        # 超长科技树：直接返回提示，避免将巨量后继全部展开导致游戏闪退
        if tech_id in self.overlong_tech_ids:
            header = "\\n\\n§H$technology_tree_title$§!"
            skip_text = self.LOCALIZATION_STRINGS[lang_code]["skip_long_tree"]
            return f"{header}\\n§R{skip_text}§!"

        tree_lines = self._build_tech_subtree(tech_id, current_depth=0, parent_tech_id=tech_id, lang_code=lang_code, path_set=set(), expanded_set=set())
        if not tree_lines:
            return "\\n\\n§H$technology_tree_title$§!\\n§Y$tech_tree_max_level$§!"
            
        header = "\\n\\n§H$technology_tree_title$§!"
        content = header + "\\n" + "\\n".join(tree_lines)
        return content
        
    def _get_output_file_paths(self, lang_code: str, filename: str) -> List[Path]:
    # 将同一份localisation内容输出到多处路径，以兼容不同加载顺序策略
        base = Path("output/localisation/")
        paths = [
            base / filename,
            base / filename,
            base / lang_code / filename,
            base / "replace" / filename,
            base / lang_code / "replace" / filename,
            base / "zzz_tech_trees" / "replace" / filename,
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
        return paths

    def _generate_localization_files_for_language(self, lang_code: str, lang_key: str):
        self._generate_main_tech_tree_file(lang_code, lang_key)
        self._generate_tech_description_replacement_file(lang_code, lang_key)

    def _generate_main_tech_tree_file(self, lang_code: str, lang_key: str):
    # 为每个科技写入一条 _techtree 文本
        file_paths = self._get_output_file_paths(lang_code, f"zztechtreemain_l_{lang_code}.yml")
        lang_config = self.LOCALIZATION_STRINGS[lang_code]
        
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
                print(f"警告：无法写入文件 {file_path}: {e}")

    def _generate_tech_description_replacement_file(self, lang_code: str, lang_key: str):
    # 覆盖科技描述 _desc，将原描述（若有）+ 级别 + 树状内容 拼接；
    # 若缺失描述，不影响输出，仅统计缺失数量并提示
        file_paths = self._get_output_file_paths(lang_code, f"zztechtreereplaced_l_{lang_code}.yml")
        lines = [f"{lang_key}:"]
        
        missing_descriptions = []
        lang_config = self.LOCALIZATION_STRINGS[lang_code]
        
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
            print(f"警告: {lang_code} 语言有 {len(missing_descriptions)} 个科技缺失描述")
        
        content = '\n'.join(lines)
        for file_path in file_paths:
            try:
                file_path.write_text(content, encoding='utf-8-sig')
            except (OSError, PermissionError) as e:
                print(f"警告：无法写入文件 {file_path}: {e}")

    def detect_circular_dependencies(self) -> List[List[str]]:
        """检测科技树中的循环依赖并返回所有循环路径"""
    # 标准DFS
    # - visited: 全局已访问节点，避免重复起点
    # - rec_stack: 当前递归路径集合，遇到已在栈中的点即发现一条环
    # - path: 为了输出路径，遇环时截取从首次出现到当前的片段
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs_detect_cycle(tech_id: str, path: List[str]) -> None:
            if tech_id in rec_stack:
                cycle_start = path.index(tech_id)
                cycle = path[cycle_start:] + [tech_id]
                cycles.append(cycle)
                return
            
            if tech_id in visited or tech_id not in self.all_technologies:
                return
            
            visited.add(tech_id)
            rec_stack.add(tech_id)
            path.append(tech_id)
            
            tech = self.all_technologies[tech_id]
            for unlock_id in tech.unlocked_tech_ids:
                dfs_detect_cycle(unlock_id, path.copy())
            
            rec_stack.remove(tech_id)
            path.pop()
        
        for tech_id in self.all_technologies:
            if tech_id not in visited:
                dfs_detect_cycle(tech_id, [])
        
        return cycles
    
    def report_circular_dependencies(self) -> None:
        """检测并报告循环依赖"""
        print("正在检测科技循环依赖...")
        cycles = self.detect_circular_dependencies()
        
        if cycles:
            print(f"发现 {len(cycles)} 个循环依赖:")
            self_loops = []
            complex_cycles = []
            
            for cycle in cycles:
                if len(cycle) == 2 and cycle[0] == cycle[1]:
                    # 自循环 (A -> A)
                    self_loops.append(cycle[0])
                else:
                    # 复杂循环 (A -> B -> C -> A)
                    complex_cycles.append(cycle)
            
            if self_loops:
                print(f"  自循环科技 ({len(self_loops)}个):")
                for tech in self_loops:
                    print(f"    {tech} -> {tech}")
            
            if complex_cycles:
                print(f"  复杂循环 ({len(complex_cycles)}个):")
                for i, cycle in enumerate(complex_cycles, 1):
                    cycle_str = " -> ".join(cycle)
                    print(f"    循环 {i}: {cycle_str}")
            print("")
        else:
            print("未发现循环依赖。")

    def generate_all_yml_files(self):
        output_dir = Path("output/localisation")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for lang_code, lang_key in self.SUPPORTED_LANGUAGES.items():
            self._generate_localization_files_for_language(lang_code, lang_key)
    
    def run_generation_process(self):
        try:
            print("正在生成科技树MOD...")
            self.scan_all_technology_files()
            self.build_technology_tree_relationships()
            self.scan_all_tech_descriptions()

            print("正在统计科技树规模...")
            self._precompute_overlong_trees()
            
            self.report_circular_dependencies()
            
            self.display_generation_statistics()
            self.generate_all_yml_files()
            
            print("生成完成！")
            
        except Exception as e:
            print(f"生成过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

    def calculate_generation_statistics(self):
    # 基本计数统计：总数/本体/危险/循环科技/按领域/按级别等
        stats = {
            'total': len(self.all_technologies),
            'base': len(self.base_game_tech_ids),
            'dangerous': sum(1 for t in self.all_technologies.values() if t.is_dangerous_tech),
            'repeatable': sum(1 for t in self.all_technologies.values() if t.is_repeatable_tech),
            'per_area': dict(Counter(t.research_area or 'unknown' for t in self.all_technologies.values())),
            'per_tier': dict(Counter(t.tier_level for t in self.all_technologies.values()))
        }
        stats['mod'] = stats['total'] - stats['base']
        return stats

    def display_generation_statistics(self):
        stats = self.calculate_generation_statistics()
        print(f"\n生成统计:")
        print(f"科技总数: {stats['total']} (本体: {stats['base']}, MOD: {stats['mod']})")
        
        english_count = sum(1 for descs in self.tech_descriptions.values() if "english" in descs)
        chinese_count = sum(1 for descs in self.tech_descriptions.values() if "simp_chinese" in descs)
        print(f"本地化: 英文 {english_count}个, 中文 {chinese_count}个")
        if self.overlong_tech_ids:
            print(f"超长科技树(>{self.LONG_TREE_THRESHOLD} 后续科技) 数量: {len(self.overlong_tech_ids)} —— 游戏内不予展示")


def main():
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(application_path, "config.ini")
    
    if not Path(config_path).exists():
        print(f"错误: 配置文件 {config_path} 不存在")
        print("请确保config.ini文件存在并包含正确的路径配置")
        if getattr(sys, 'frozen', False):
            print("\n按 Enter 键退出。")
            input()
        return
        
    generator = TechTreeGenerator(config_path)
    generator.run_generation_process()
    
    if getattr(sys, 'frozen', False):
        print("\n按 Enter 键退出。")
        input()


if __name__ == "__main__":
    main()