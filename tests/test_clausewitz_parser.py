# pyright: reportMissingImports=false

from __future__ import annotations

import pytest

from dtt_core.clausewitz_parser import (
    Assignment,
    Atom,
    Block,
    TokenKind,
    parse,
    tokenize,
)


def _only_assignments(items):
    return [item for item in items if isinstance(item, Assignment)]


def test_tokenize_hash_and_braces_inside_strings_are_literal() -> None:
    res = tokenize('a = "{#notcomment}" # outside\nb = "{ }"\n')
    assert res.diagnostics == []

    kinds = [tok.kind for tok in res.tokens]
    assert TokenKind.LBRACE not in kinds
    assert TokenKind.RBRACE not in kinds

    string_values = [tok.value for tok in res.tokens if tok.kind == TokenKind.STRING]
    assert string_values == ["{#notcomment}", "{ }"]


def test_parse_block_not_confused_by_braces_inside_string() -> None:
    res = parse('a = { b = "{ }" c = 1 }')
    assert res.diagnostics == []
    assert len(res.root.items) == 1

    top = res.root.items[0]
    assert isinstance(top, Assignment)
    assert top.key.value == "a"
    assert isinstance(top.value, Block)

    inner = _only_assignments(top.value.items)
    assert [a.key.value for a in inner] == ["b", "c"]
    assert isinstance(inner[0].value, Atom)
    assert inner[0].value.token.kind == TokenKind.STRING
    assert inner[0].value.token.value == "{ }"


def test_tokenize_escaped_quotes_and_backslashes_in_strings() -> None:
    res = tokenize('a = "x\\"y\\\\z"')
    assert res.diagnostics == []
    string_tokens = [tok for tok in res.tokens if tok.kind == TokenKind.STRING]
    assert len(string_tokens) == 1
    assert string_tokens[0].value == 'x"y\\z'


@pytest.mark.parametrize("op", ["=", "!=", "<", ">", "<=", ">=", "?="])
def test_parse_recognizes_all_supported_operators(op: str) -> None:
    res = parse(f"a {op} b")
    assert res.diagnostics == []
    assert len(res.root.items) == 1

    stmt = res.root.items[0]
    assert isinstance(stmt, Assignment)
    assert stmt.key.value == "a"
    assert stmt.op.value == op
    assert isinstance(stmt.value, Atom)
    assert stmt.value.token.value == "b"


def test_parse_preserves_special_bare_tokens() -> None:
    res = parse(
        "\n".join(
            [
                "a = @tier1cost3",
                "b = technologies/rare_techs",
                "c = some_scope.some_key",
            ]
        )
    )
    assert res.diagnostics == []

    assigns = _only_assignments(res.root.items)
    assert [a.key.value for a in assigns] == ["a", "b", "c"]
    assert [a.value.token.value for a in assigns if isinstance(a.value, Atom)] == [
        "@tier1cost3",
        "technologies/rare_techs",
        "some_scope.some_key",
    ]


def test_parse_preserves_duplicate_keys_and_statement_order() -> None:
    res = parse("a = 1\na = 2\n")
    assert res.diagnostics == []

    assigns = _only_assignments(res.root.items)
    assert len(assigns) == 2
    assert [a.key.value for a in assigns] == ["a", "a"]
    assert [a.value.token.value for a in assigns if isinstance(a.value, Atom)] == [
        "1",
        "2",
    ]


@pytest.mark.parametrize(
    "text, expected_substrings",
    [
        ("a = { b = c", ["Unterminated block"]),
        ('a = "unterminated\nb = 1\n', ["Unterminated string literal"]),
        ("}", ["Unexpected '}'"]),
    ],
)
def test_parse_recovery_accumulates_diagnostics(text: str, expected_substrings) -> None:
    res = parse(text)
    assert res.root is not None
    assert res.diagnostics

    joined = "\n".join(d.message for d in res.diagnostics)
    for substring in expected_substrings:
        assert substring in joined


def test_token_spans_track_newlines() -> None:
    res = tokenize("a=1\r\nb=2")
    b_tok = next(
        tok for tok in res.tokens if tok.kind == TokenKind.BARE and tok.value == "b"
    )
    assert (b_tok.span.start_line, b_tok.span.start_col) == (2, 1)
