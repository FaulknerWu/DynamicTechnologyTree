# MIXINS PIPELINE

## OVERVIEW
Generation logic is split into mixins that compose into `TechTreeGenerator` (`src/generator.py:18`). Each mixin owns one stage of the pipeline.

## WHERE TO LOOK
| Stage | Owner | Entry | Notes |
|-------|-------|-------|-------|
| Config + localization | `ConfigAndLocalizationMixin` | `src/mixins/config_mixin.py:19` | `_load_configuration`, `_load_enabled_mod_ids_from_dlc_load`, `_l()` |
| Scan technologies | `ParserMixin` | `src/mixins/parser_mixin.py:70` | Reads base game + mods tech `.txt` into `Technology` |
| Build relations | `RelationsMixin` | `src/mixins/relations_mixin.py:2` | Populates `unlocked_tech_ids` from prerequisites |
| Scan descriptions | `ParserMixin` | `src/mixins/parser_mixin.py:294` | Parses localisation `.yml` descriptions per language |
| Precompute overlong roots | `RelationsMixin` | `src/mixins/relations_mixin.py:10` | Used for display/statistics decisions |
| Cycle detection | `CycleMixin` | `src/mixins/cycle_mixin.py:36` | Reports circular dependencies |
| Statistics | `StatsMixin` | `src/mixins/stats_mixin.py:17` | Prints generation statistics |
| Render tree text | `RenderMixin` | `src/mixins/render_mixin.py:330` | Formats trees with depth/child/node constraints |
| Write output YML | `OutputMixin` | `src/mixins/output_mixin.py:212` | Writes localisation files and variant expansions |

## PIPELINE ORDER
Entry: `TechTreeGenerator.run_generation_process()` (`src/generator.py:33`)
1) `scan_all_technology_files()` (`src/mixins/parser_mixin.py:70`)
2) `build_technology_tree_relationships()` (`src/mixins/relations_mixin.py:2`)
3) `scan_all_tech_descriptions()` (`src/mixins/parser_mixin.py:294`)
4) `_precompute_overlong_trees()` (`src/mixins/relations_mixin.py:10`)
5) `report_circular_dependencies()` (`src/mixins/cycle_mixin.py:36`)
6) `display_generation_statistics()` (`src/mixins/stats_mixin.py:17`)
7) `generate_all_yml_files()` (`src/mixins/output_mixin.py:212`)

## ANTI-PATTERNS
- Silent parse skips: `except Exception: pass` in `_scan_technology_path()` (`src/mixins/parser_mixin.py:104`).
- Treating IO errors as "file missing": `_read_file_with_encoding` returns `""` on exception (`src/mixins/parser_mixin.py:122`).
- Duplicate constants: `MAX_PREREQ_DISPLAY` / `ELLIPSIS` appear on both generator and render mixin (`src/generator.py:30`, `src/mixins/render_mixin.py:33`).
