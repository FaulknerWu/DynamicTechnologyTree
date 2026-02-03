# DTT CORE

complexity: 4/5
scope: src/dtt_core/*
inherits: ../../AGENTS.md

## OVERVIEW
Core generation pipeline stages (scan/parse -> relate -> render -> output) used by `TechTreeGenerator`.

## STRUCTURE
```
src/dtt_core/
|-- scan_parse.py    # scan Stellaris tech + localisation; parse into in-memory maps
|-- relations.py     # build prereq/unlock relationships; overlong-root precompute
|-- render.py        # tree formatting with depth/children/node caps and overflow hints
|-- output.py        # writes localisation YML variants (replace/dirs) as utf-8-sig
|-- cycle.py         # circular dependency detection + reporting
|-- stats.py         # generation stats reporting
`-- config_loader.py # reads config.ini + optional dlc_load.json; localization string lookup
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Scan + parse tech defs | `src/dtt_core/scan_parse.py:191` | `scan_all_technology_files()` populates `all_technologies` |
| Scan + parse descriptions | `src/dtt_core/scan_parse.py:456` | `scan_all_tech_descriptions()` populates `tech_descriptions` |
| Load config.ini | `src/dtt_core/config_loader.py:28` | `load_configuration()` returns `GeneratorConfig` |
| Enabled mods from dlc_load.json | `src/dtt_core/config_loader.py:149` | Maps workshop/local mods into enabled IDs |
| Build relationships | `src/dtt_core/relations.py:18` | Populates prereq/unlock edges on `Technology` objects |
| Render a tree | `src/dtt_core/render.py:555` | `generate_tech_tree_content()` returns escaped `\\n` strings |
| Emit output files | `src/dtt_core/output.py:279` | `generate_all_yml_files()` writes multiple candidate paths |
| Cycle detection | `src/dtt_core/cycle.py:46` | `report_circular_dependencies()` prints warnings |
| Generation stats | `src/dtt_core/stats.py:11` | Summaries printed at end of run |

## CONVENTIONS
- Stage objects operate on shared in-memory maps (`all_technologies`, `tech_descriptions`, variant maps) that are owned by `TechTreeGenerator`.
- Output paths are relative to process CWD (GUI normalizes CWD in `src/gui/__init__.py`); keep `dtt_core` code CWD-agnostic.
- Output YML is written as UTF-8 BOM (`utf-8-sig`) for Stellaris compatibility (`src/dtt_core/output.py`).
- Parsing is tolerant by design (supports multiple encodings / imperfect inputs); failures should be observable via counters/logs.

## ANTI-PATTERNS
- Silent exception swallowing: `src/dtt_core/render.py:486` has an `except Exception: pass` guard around overflow tagging.
- Silent data loss on reads: `read_text(..., errors="ignore")` is used when scanning/parsing (`src/dtt_core/scan_parse.py`, `src/dtt_core/config_loader.py`).
- Mixing GUI concerns into core stages; keep UI/progress parsing in `src/gui/` and logic in `src/dtt_core/`.
