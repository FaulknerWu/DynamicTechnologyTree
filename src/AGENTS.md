# SRC KNOWLEDGE

## OVERVIEW
Python source lives under `src/` with a flat import model (top-level modules like `generator`, `config`, `models`, `localization`).

## STRUCTURE
```
src/
|-- generator.py        # TechTreeGenerator pipeline coordinator
|-- config.py           # config dataclasses/defaults (paths/localization/display/tech)
|-- models.py           # Technology model used across mixins
|-- localization.py     # per-language strings + research area icons
|-- gui/                # PyQt6 GUI (entrypoint, window, worker, path detection)
`-- mixins/             # pipeline stages (config/parser/render/output/relations/cycle/stats)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Orchestrator | `src/generator.py:18` | Mixins compose into `TechTreeGenerator` |
| Config schema/defaults | `src/config.py:57` | `GeneratorConfig` + sub-config dataclasses |
| Localization strings | `src/localization.py:9` | Used for UI + CLI-ish output + progress markers |
| Model shape | `src/models.py:1` | `Technology` attributes consumed by parser/render/output |

## CONVENTIONS
- Imports assume `src/` is on `sys.path` (either via install or script injection). Example: `from generator import TechTreeGenerator` (`src/gui/generation_worker.py:46`).
- Packaging is configured for flat modules (`pyproject.toml:24`); adding a new top-level module may require updating `pyproject.toml`.

## ANTI-PATTERNS
- Adding a second "official" entrypoint without aligning config/cwd semantics (see `src/gui/__init__.py:13` vs `scripts/generate_tech_tree_gui.py:15`).
- Introducing new top-level modules/packages under `src/` without deciding whether they are installed (setuptools config lives in `pyproject.toml:22`).
