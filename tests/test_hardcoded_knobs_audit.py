from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]

WATCHED_MODULES = (
    "src/dtt_core/output.py",
    "src/dtt_core/sav_reader.py",
    "src/dtt_core/file_decode.py",
    "src/dtt_core/render.py",
    "src/dtt_core/file_indexer.py",
    "src/dtt_core/ingestion_pipeline.py",
    "src/dtt_core/load_order_resolver.py",
    "src/dtt_core/generate_localization.py",
    "src/gui/path_detector.py",
    "src/generator.py",
)

UPPERCASE_POLICY_NAME = re.compile(r"^_*[A-Z][A-Z0-9_]*$")
ALLOWED_NUMERIC_BINOPS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
)
ALLOWED_NUMERIC_UNARYOPS = (ast.UAdd, ast.USub, ast.Invert)


def _is_uppercase_policy_name(name: str) -> bool:
    return bool(UPPERCASE_POLICY_NAME.fullmatch(name))


def _is_numeric_literal(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    )


def _is_pure_numeric_expression(node: ast.AST) -> bool:
    if _is_numeric_literal(node):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ALLOWED_NUMERIC_UNARYOPS):
        return _is_pure_numeric_expression(node.operand)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ALLOWED_NUMERIC_BINOPS):
        return _is_pure_numeric_expression(node.left) and _is_pure_numeric_expression(
            node.right
        )
    return False


def _iter_module_level_numeric_policy_constants(
    module_source: str,
) -> list[tuple[str, int, str]]:
    parsed = ast.parse(module_source)
    hits: list[tuple[str, int, str]] = []

    for node in parsed.body:
        if isinstance(node, ast.Assign):
            if not _is_pure_numeric_expression(node.value):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and _is_uppercase_policy_name(
                    target.id
                ):
                    hits.append((target.id, node.lineno, ast.unparse(node.value)))
        elif isinstance(node, ast.AnnAssign):
            if node.value is None or not _is_pure_numeric_expression(node.value):
                continue
            if isinstance(node.target, ast.Name) and _is_uppercase_policy_name(
                node.target.id
            ):
                hits.append((node.target.id, node.lineno, ast.unparse(node.value)))

    return hits


def test_hardcoded_knobs_audit() -> None:
    missing_modules: list[str] = []
    violations: list[str] = []

    for relative_module in WATCHED_MODULES:
        module_path = ROOT_DIR / relative_module
        if not module_path.exists():
            missing_modules.append(relative_module)
            continue

        module_source = module_path.read_text(encoding="utf-8")
        for name, line, value_repr in _iter_module_level_numeric_policy_constants(
            module_source
        ):
            violations.append(f"{relative_module}:{line} -> {name} = {value_repr}")

    assert not missing_modules, f"Watched modules missing: {sorted(missing_modules)}"
    assert (
        not violations
    ), "Move numeric policy constants into Settings; found:\n" + "\n".join(
        sorted(violations)
    )
