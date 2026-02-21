# DTT CORE

complexity: 4/5
scope: src/dtt_core/*
inherits: ../../AGENTS.md

## OVERVIEW
Core generation pipeline stages plus parsing/merge utilities used by `TechTreeGenerator`.

## STRUCTURE
```
src/dtt_core/
|-- ingestion_pipeline.py    # integrated scan/parse/merge pipeline (tech defs + localisation)
|-- load_order_resolver.py   # resolves mod load order from launcher DB / dlc_load.json
|-- file_indexer.py          # deterministic file indexing with LIOS/replace_path support
|-- source_manifest.py       # source roots + replace_path manifest
|-- clausewitz_parser.py     # tokenizer/parser for Clausewitz-ish .txt tech defs
|-- tech_extractor.py        # extract + normalize Technology definitions (incl swaps)
|-- tech_merge.py            # last-wins merge with provenance
|-- localisation_parser.py   # localisation YML parsing + last-wins merge + diagnostics
|-- file_decode.py           # tolerant decoding + diagnostics (avoid errors="ignore")
|-- trigger_evaluator.py     # evaluate tech triggers for filtered trees
|-- mod_descriptor_loader.py # parse .mod descriptors (encoding-tolerant)
|-- relations.py             # build prereq/unlock relationships; overlong-root precompute
|-- render.py                # tree formatting with depth/children/node caps and overflow hints
|-- output.py                # writes localisation YML variants (replace/dirs) as utf-8-sig
|-- cycle.py                 # circular dependency detection + reporting
|-- stats.py                 # generation stats reporting
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Tech + localisation ingestion | `src/dtt_core/ingestion_pipeline.py:54` | `IntegratedIngestionPipeline` scans, parses, and merges tech defs + localisation |
| Mod load order resolution | `src/dtt_core/load_order_resolver.py:35` | `LoadOrderResolver` resolves enabled mods from launcher DB / dlc_load.json |
| Deterministic file indexing | `src/dtt_core/file_indexer.py:25` | `FileIndexer` builds LIOS-ordered file index with replace_path support |
| Localisation parsing + merge | `src/dtt_core/localisation_parser.py:15` | Parses `.yml` localisation and merges via last-wins |
| Build relationships | `src/dtt_core/relations.py:18` | Populates prereq/unlock edges on `Technology` objects |
| Render a tree | `src/dtt_core/render.py:628` | `generate_tech_tree_content()` returns escaped `\\n` strings |
| Emit output files | `src/dtt_core/output.py:352` | `generate_all_yml_files()` writes multiple candidate paths |
| Cycle detection | `src/dtt_core/cycle.py:46` | `report_circular_dependencies()` prints warnings |
| Generation stats | `src/dtt_core/stats.py:49` | Summaries printed at end of run |

## CONVENTIONS
- Stage objects operate on shared in-memory maps (`all_technologies`, `tech_descriptions`, variant maps) that are owned by `TechTreeGenerator`.
- Output paths are relative to process CWD (GUI normalizes CWD in `src/gui/__init__.py`); keep `dtt_core` code CWD-agnostic.
- Output YML is written as UTF-8 BOM (`utf-8-sig`) for Stellaris compatibility (`src/dtt_core/output.py`).
- Parsing is tolerant by design (supports multiple encodings / imperfect inputs); failures should be observable via counters/logs.

## ANTI-PATTERNS
- Bypassing deterministic ordering/merge: go through `FileIndexer` + last-wins merge (avoid ad-hoc `glob()` ordering).
- File decoding: text reads now go through `dtt_core.file_decode` with diagnostics; avoid reintroducing `errors="ignore"` reads.
- Mixing GUI concerns into core stages; keep UI/progress parsing in `src/gui/` and logic in `src/dtt_core/`.
