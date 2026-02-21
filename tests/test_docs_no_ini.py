"""Guardrail: README must not document config.ini as a supported format.

pytest selector: ``-k docs_no_ini``
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
README_PATH = ROOT_DIR / "README.md"

_INI_SCHEMA_PATTERNS = (
    re.compile(r"^##\s+.*config\.ini", re.MULTILINE),
    re.compile(r"```ini\b"),
)


def test_docs_no_ini_schema_in_readme() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    violations: list[str] = []
    for pattern in _INI_SCHEMA_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            violations.extend(matches)

    assert (
        not violations
    ), "README still documents config.ini as a configuration format: " + repr(
        violations
    )


def test_docs_no_ini_mentions_settings_json() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    assert "settings.json" in text, "README does not mention settings.json"
