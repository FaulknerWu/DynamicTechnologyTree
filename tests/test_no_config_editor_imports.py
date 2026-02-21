from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FORBIDDEN_TOKENS = (
    ".".join(("gui", "config_editor")),
    "Config" + "Editor",
)


def _iter_text_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]

    files: list[Path] = []
    for candidate in path.rglob("*"):
        if not candidate.is_file():
            continue
        if "__pycache__" in candidate.parts:
            continue
        if candidate.suffix in {".pyc", ".pyo"}:
            continue
        files.append(candidate)
    return files


def test_no_config_editor_imports() -> None:
    scan_targets = [
        ROOT_DIR / "src",
        ROOT_DIR / "tests",
        ROOT_DIR / "packaging" / "pyinstaller" / "techtree_gui.spec",
    ]
    current_file = Path(__file__).resolve()
    violations: list[str] = []

    for target in scan_targets:
        for file_path in _iter_text_files(target):
            if file_path.resolve() == current_file:
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            for token in FORBIDDEN_TOKENS:
                if token in content:
                    violations.append(
                        f"{file_path.relative_to(ROOT_DIR)} contains {token}"
                    )

    assert not violations, "\n".join(sorted(violations))
