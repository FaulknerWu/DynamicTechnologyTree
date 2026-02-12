# TESTS

**Generated:** 2026-02-02T18:38:48Z
complexity: 3/5
scope: tests/*
inherits: ../AGENTS.md

## OVERVIEW
Pytest-based smoke + golden regression coverage for the generator plus offscreen GUI/i18n coverage; tests run from a repo checkout without requiring an editable install.

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Path injection | `tests/conftest.py:7` | Prepends `src/` to `sys.path` so tests can `import generator` |
| Smoke test | `tests/test_smoke.py:25` | Writes temp `config.ini`, runs basic pipeline stages, asserts no techs |
| Golden output regression | `tests/test_golden_output.py:35` | Runs end-to-end fixture pipeline; asserts output bytes match committed snapshots |
| GUI i18n + runtime retranslation | `tests/test_gui_i18n.py:88` | Runs PyQt6 in offscreen mode; validates locale mapping/fallbacks, runtime UI retranslation, config language persistence, and language lock while generation is active |
| Pytest config | `pyproject.toml:29` | `testpaths=["tests"]`, `python_files=test_*.py` |

## CONVENTIONS
- Tests assume the flat-module import model (`import generator`) and rely on `tests/conftest.py` to make it work.
- Prefer `tmp_path`-style isolated filesystem tests; avoid touching real Stellaris installs.
- Treat `tests/fixtures/` as the canonical fake Stellaris/workshop layout for hermetic tests.
- Treat `tests/golden/` as snapshots: update only when an output change is intended and reviewed.

## ANTI-PATTERNS
- Importing from the repo without `tests/conftest.py` (tests become dependent on an editable install).
- Writing output to the real `./localisation/` tree; keep tests hermetic.
