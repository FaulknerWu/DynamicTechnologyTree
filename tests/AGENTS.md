# TESTS

**Generated:** 2026-02-02T13:08:50Z
complexity: 3/5
scope: tests/*
inherits: ../AGENTS.md

## OVERVIEW
Pytest-based smoke coverage for the generator; tests run from a repo checkout without requiring an editable install.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Path injection | `tests/conftest.py:7` | Prepends `src/` to `sys.path` so tests can `import generator` |
| Smoke test | `tests/test_smoke.py:25` | Writes temp `config.ini`, runs basic pipeline stages, asserts no techs |
| Pytest config | `pyproject.toml:29` | `testpaths=["tests"]`, `python_files=test_*.py` |

## CONVENTIONS
- Tests assume the flat-module import model (`import generator`) and rely on `tests/conftest.py` to make it work.
- Prefer `tmp_path`-style isolated filesystem tests; avoid touching real Stellaris installs.

## ANTI-PATTERNS
- Importing from the repo without `tests/conftest.py` (tests become dependent on an editable install).
- Writing output to the real `./localisation/` tree; keep tests hermetic.
