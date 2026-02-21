# Settings Reference

Auto-generated from the Settings schema. Do not edit by hand.

Re-generate with:

```bash
python -m settings_reference
```

## Paths

| Field | Label | Description | Default |
|-------|-------|-------------|---------|
| `file_indexing.localisation_glob` | Localisation file glob | Glob pattern used under localisation_root when indexing localisation files. | `"**/*.yml"` |
| `file_indexing.localisation_replace_prefix` | Localisation replace prefix | Localisation files under this prefix are loaded in a late phase. | `"localisation/replace"` |
| `file_indexing.localisation_root` | Localisation root (relative) | Relative path under each source root scanned for localisation files. | `"localisation"` |
| `file_indexing.technology_glob` | Technology file glob | Glob pattern used under technology_root when indexing technology files. | `"*.txt"` |
| `file_indexing.technology_root` | Technology root (relative) | Relative path under each source root scanned for technology files. | `"common/technology"` |
| `load_order.multi_active_playset_selection_policy` | Active playset selection policy | How to choose a playset when multiple active playsets are active. | `"latest_created_then_name_then_id"` |
| `paths.base_game_path` | Game install directory | Directory where Stellaris is installed. | `""` |
| `paths.game_directory_name` | Game directory name | Directory name under steamapps/common used for autodetection. | `"Stellaris"` |
| `paths.launcher_db_filename` | Launcher database filename | Filename searched under user data path for launcher database. | `"launcher-v2.sqlite"` |
| `paths.launcher_db_path` | Launcher DB (launcher-v2.sqlite) | Path to launcher-v2.sqlite used to resolve enabled mods. | `""` |
| `paths.local_mod_directory_name` | Local mod directory name | Directory searched under user data path for local mods. | `"mod"` |
| `paths.local_mod_folder_path` | Local MOD directory (optional) | Optional local mod directory outside Steam Workshop. | `""` |
| `paths.mod_folder_path` | Workshop directory | Steam Workshop directory for Stellaris mods. | `""` |
| `paths.steam_app_id` | Steam app ID | Workshop app ID used for autodetection. | `"281990"` |
| `paths.user_data_subpath_components` | User data subpath components | Subpath components under Documents for user data autodetection. | `["Paradox Interactive", "Stellaris"]` |

## Localization

| Field | Label | Description | Default |
|-------|-------|-------------|---------|
| `localization.language` | Language | Language used for generated localisation output. | `"simp_chinese"` |

## Display

| Field | Label | Description | Default |
|-------|-------|-------------|---------|
| `display.max_children_per_node` | Max children per node (0 = unlimited) | Maximum children shown per node (0 means unlimited). | `12` |
| `display.max_display_nodes` | Max displayed nodes (0 = unlimited) | Maximum nodes rendered in one tree (0 means unlimited). | `128` |
| `display.max_prereq_display` | Max additional prerequisites | Maximum extra prerequisites shown before the ellipsis. | `2` |
| `display.max_tree_depth` | Max tree depth (0 = unlimited) | Maximum tree depth to render (0 means unlimited). | `4` |
| `progress_milestones.cycles` | CYCLES progress | Progress milestone for CYCLES. | `60` |
| `progress_milestones.done` | DONE progress | Progress milestone for DONE. | `100` |
| `progress_milestones.ingest_l10n` | INGEST_L10N progress | Progress milestone for INGEST_L10N. | `45` |
| `progress_milestones.load_order` | LOAD_ORDER progress | Progress milestone for LOAD_ORDER. | `20` |
| `progress_milestones.relations` | RELATIONS progress | Progress milestone for RELATIONS. | `35` |
| `progress_milestones.render` | RENDER progress | Progress milestone for RENDER. | `50` |
| `progress_milestones.save_parse_parse` | SAVE_PARSE parse progress | Progress milestone for SAVE_PARSE parse. | `10` |
| `progress_milestones.save_parse_start` | SAVE_PARSE start progress | Progress milestone for SAVE_PARSE start. | `5` |
| `progress_milestones.write_output` | WRITE_OUTPUT progress | Progress milestone for WRITE_OUTPUT. | `80` |

## Output

| Field | Label | Description | Default |
|-------|-------|-------------|---------|
| `decode.fallback_encodings` | Fallback input encodings | Tried after preferred encodings fail. | `["cp1252", "latin-1"]` |
| `decode.on_failure` | Decode failure policy | Behavior when all configured encodings fail. | `"replace"` |
| `decode.preferred_encodings` | Preferred input encodings | Tried first when decoding text files. | `["utf-8-sig", "utf-8"]` |
| `decode.replacement_encoding` | Replacement encoding | Used for replacement-mode decode when all attempts fail. | `"utf-8"` |
| `diagnostics.overlong_tree_roots_log_limit` | Over-breadth roots log limit | Maximum over-breadth root entries shown in diagnostics logs (0 means unlimited). | `50` |
| `ingestion.diagnostic_example_limit` | Ingestion diagnostics example limit | Maximum ingestion parse/decode examples shown per stage. | `10` |
| `output.eligibility_sample_size` | Eligibility report sample size | How many deterministic examples to include per eligibility report section. | `5` |
| `output.eligibility_unknown_warning_threshold` | Eligibility unknown-warning threshold | Warn when unknown potential exclusions reach this count (0 disables warning). | `1` |
| `output.on_existing_file` | On existing file | Behavior when the output file already exists. | `"overwrite"` |
| `output.on_write_error` | On write error | Behavior when writing one output target fails. | `"warn_and_continue"` |
| `output.report_encoding` | Report encoding | Encoding used for save eligibility reports. | `"utf-8"` |
| `output.yml_encoding` | YML encoding | Encoding used when writing localisation YML files. | `"utf-8-sig"` |
| `output.yml_targets` | YML output targets | Relative localisation targets generated for each output file. | `["", "{lang_code}", "replace", "{lang_code}/replace", "zzz_tech_trees/replace"]` |
| `save_reader.max_member_uncompressed_size_bytes` | Save ZIP per-member uncompressed cap (bytes) | Reject ZIP members larger than this many bytes. | `268435456` |
| `save_reader.max_parse_diagnostics_per_member` | Max parse diagnostics per member | Limit how many parse diagnostics are shown per save member. | `20` |
| `save_reader.max_total_uncompressed_size_bytes` | Save ZIP total uncompressed cap (bytes) | Reject ZIP archives whose total uncompressed size exceeds this. | `536870912` |

## settings

| Field | Label | Description | Default |
|-------|-------|-------------|---------|
| `schema_version` | Schema version | Version of the settings schema. | `1` |
