# SRC KNOWLEDGE

complexity: 3/5
scope: src/*
inherits: ../AGENTS.md

## OVERVIEW
Python source lives under `src/` with a hybrid layout: a few flat top-level modules (`generator`, `config`, `models`, `localization`) plus packages (`dtt_core/`, `gui/`).

`src/generator.py` orchestrates the core pipeline via composition; the individual pipeline stages live under `src/dtt_core/`.

## STRUCTURE
```
src/
|-- generator.py        # TechTreeGenerator orchestrator (composition-based)
|-- config.py           # config dataclasses/defaults (paths/localization/display/tech)
|-- models.py           # Technology model consumed across pipeline stages
|-- localization.py     # per-language strings + research area icons
|-- dtt_core/           # core pipeline stages (scan/parse/relations/render/output/etc.)
`-- gui/                # PyQt6 GUI (entrypoint, window, worker, path detection)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Orchestrator | `src/generator.py:17` | Composes `dtt_core` stages into `TechTreeGenerator` |
| Config schema/defaults | `src/config.py:66` | `GeneratorConfig` + sub-config dataclasses |
| Core pipeline stages | `src/dtt_core/` | scan/parse, relations, render, cycle/stats, output |
| Localization strings | `src/localization.py:9` | Used for UI + CLI-ish output + progress markers |
| Model shape | `src/models.py:6` | `Technology` attributes consumed by scan/relations/render/output |

## CONVENTIONS
- Imports assume `src/` is on `sys.path` (via installation). Example: `from generator import TechTreeGenerator` (`src/gui/generation_worker.py:51`).
- Top-level modules are listed in `pyproject.toml` (`[tool.setuptools] py-modules`); adding a new flat module may require updating packaging config.
- Packages under `src/` (e.g. `dtt_core`, `gui`) are discovered via `find_packages` (`pyproject.toml`); keep package names stable for PyInstaller/module execution.
- `src/dynamic_technology_tree.egg-info/` is a build artifact (gitignored by `*.egg-info/`); avoid depending on it in code or docs.

## ANTI-PATTERNS
- Documenting/adding a second user-facing entrypoint; `dtt-gui` is the supported launcher (keep `python -m gui` for module execution/PyInstaller only).
- Growing new monolithic pipeline stages outside `src/dtt_core/`; prefer small, focused stage classes that `TechTreeGenerator` composes.
- Introducing new top-level modules/packages under `src/` without deciding whether they are installed (setuptools config lives in `pyproject.toml:22`).
