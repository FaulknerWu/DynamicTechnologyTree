from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
SPEC_PATH = ROOT_DIR / "packaging" / "pyinstaller" / "techtree_gui.spec"

FORBIDDEN_SOURCE_TOKENS = (
    "configparser",
    "dtt_core.config_loader",
    "config_loader.py",
    "config.ini",
)

FORBIDDEN_SPEC_TOKENS = (
    "dtt_core.config_loader",
    "configparser",
)


def test_no_ini_parsing_tokens_removed_from_source_tree() -> None:
    offenders: list[str] = []
    for path in SRC_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_SOURCE_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT_DIR)}::{token}")

    assert not offenders, "Found legacy INI parsing tokens: " + ", ".join(offenders)


def test_no_ini_parsing_tokens_removed_from_packaging_spec() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    offenders = [token for token in FORBIDDEN_SPEC_TOKENS if token in spec_text]

    assert not offenders, "Found legacy INI tokens in spec: " + ", ".join(offenders)
