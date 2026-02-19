from __future__ import annotations

"""Clausewitz (Paradox) script tokenizer + tolerant AST parser.

This module intentionally stays *pure*: it takes a string and produces an
order-preserving AST plus diagnostics. It does not evaluate triggers/effects.

Spans are 1-based (line, col) and use an exclusive end position.
"""

from dataclasses import dataclass


class TokenKind:
    BARE = "BARE"
    STRING = "STRING"
    LBRACE = "LBRACE"
    RBRACE = "RBRACE"
    OP = "OP"
    EOF = "EOF"
    MISSING = "MISSING"


_OPERATORS: tuple[str, ...] = ("!=", "<=", ">=", "?=", "=", "<", ">")
_OP_START_CHARS = set("=!<>?")


@dataclass(frozen=True)
class Span:
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    @staticmethod
    def at(line: int, col: int) -> "Span":
        return Span(line, col, line, col)


@dataclass(frozen=True)
class Diagnostic:
    message: str
    line: int
    col: int
    path: str | None = None

    def format(self) -> str:
        if self.path:
            return f"{self.path}:{self.line}:{self.col}: {self.message}"
        return f"{self.line}:{self.col}: {self.message}"


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    span: Span


@dataclass
class Atom:
    token: Token
    span: Span


@dataclass
class Assignment:
    key: Token
    op: Token
    value: "ClausewitzNode"
    span: Span


@dataclass
class Block:
    items: list["ClausewitzNode"]
    span: Span
    lbrace: Token | None = None
    rbrace: Token | None = None


ClausewitzNode = Atom | Assignment | Block


@dataclass(frozen=True)
class TokenizeResult:
    tokens: list[Token]
    diagnostics: list[Diagnostic]


@dataclass(frozen=True)
class ParseResult:
    root: Block
    diagnostics: list[Diagnostic]
    tokens: list[Token]


class _Cursor:
    def __init__(self, text: str) -> None:
        self._text = text
        self.i = 0
        self.line = 1
        self.col = 1

    def at_end(self) -> bool:
        return self.i >= len(self._text)

    def peek(self, offset: int = 0) -> str:
        j = self.i + offset
        if j < 0 or j >= len(self._text):
            return ""
        return self._text[j]

    def position(self) -> tuple[int, int]:
        return self.line, self.col

    def advance(self) -> str:
        if self.at_end():
            return ""
        ch = self._text[self.i]
        if ch == "\r":
            if self.i + 1 < len(self._text) and self._text[self.i + 1] == "\n":
                self.i += 2
            else:
                self.i += 1
            self.line += 1
            self.col = 1
            return "\n"
        if ch == "\n":
            self.i += 1
            self.line += 1
            self.col = 1
            return "\n"
        self.i += 1
        self.col += 1
        return ch


def tokenize(text: str, *, path: str | None = None) -> TokenizeResult:
    cur = _Cursor(text)
    tokens: list[Token] = []
    diagnostics: list[Diagnostic] = []

    def emit(kind: str, value: str, *, start: tuple[int, int]) -> None:
        end_line, end_col = cur.position()
        start_line, start_col = start
        tokens.append(
            Token(
                kind=kind,
                value=value,
                span=Span(
                    start_line=start_line,
                    start_col=start_col,
                    end_line=end_line,
                    end_col=end_col,
                ),
            )
        )

    def diag(message: str, *, at: tuple[int, int]) -> None:
        line, col = at
        diagnostics.append(Diagnostic(message=message, line=line, col=col, path=path))

    while not cur.at_end():
        ch = cur.peek()
        if ch.isspace():
            cur.advance()
            continue
        if ch == "#":
            while not cur.at_end() and cur.peek() not in ("\n", "\r"):
                cur.advance()
            continue
        if ch == "{":
            start = cur.position()
            cur.advance()
            emit(TokenKind.LBRACE, "{", start=start)
            continue
        if ch == "}":
            start = cur.position()
            cur.advance()
            emit(TokenKind.RBRACE, "}", start=start)
            continue
        if ch == '"':
            start = cur.position()
            cur.advance()
            buf: list[str] = []
            while not cur.at_end():
                inner = cur.peek()
                if inner == '"':
                    cur.advance()
                    emit(TokenKind.STRING, "".join(buf), start=start)
                    break
                if inner in ("\n", "\r"):
                    diag("Unterminated string literal", at=start)
                    emit(TokenKind.STRING, "".join(buf), start=start)
                    break
                if inner == "\\":
                    cur.advance()
                    if cur.at_end():
                        buf.append("\\")
                        diag("Unterminated escape sequence in string literal", at=start)
                        emit(TokenKind.STRING, "".join(buf), start=start)
                        break
                    nxt = cur.peek()
                    if nxt in ('"', "\\"):
                        buf.append(nxt)
                        cur.advance()
                    else:
                        buf.append("\\")
                        buf.append(nxt)
                        cur.advance()
                    continue

                buf.append(inner)
                cur.advance()
            else:
                diag("Unterminated string literal", at=start)
                emit(TokenKind.STRING, "".join(buf), start=start)
            continue
        if ch in _OP_START_CHARS:
            start = cur.position()
            matched = ""
            for op in _OPERATORS:
                if text.startswith(op, cur.i):
                    matched = op
                    break
            if matched:
                for _ in range(len(matched)):
                    cur.advance()
                emit(TokenKind.OP, matched, start=start)
            else:
                cur.advance()
                diag(f"Unexpected character: {ch!r}", at=start)
                emit(TokenKind.BARE, ch, start=start)
            continue
        start = cur.position()
        buf = []
        while not cur.at_end():
            inner = cur.peek()
            if (
                inner.isspace()
                or inner in ("{", "}", '"', "#")
                or inner in _OP_START_CHARS
            ):
                break
            buf.append(inner)
            cur.advance()

        if not buf:
            cur.advance()
            diag(f"Unexpected character: {ch!r}", at=start)
            emit(TokenKind.BARE, ch, start=start)
            continue

        emit(TokenKind.BARE, "".join(buf), start=start)

    eof_line, eof_col = cur.position()
    tokens.append(Token(kind=TokenKind.EOF, value="", span=Span.at(eof_line, eof_col)))
    return TokenizeResult(tokens=tokens, diagnostics=diagnostics)


class _TokenStream:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._i = 0

    def peek(self, offset: int = 0) -> Token:
        idx = self._i + offset
        if idx < 0:
            idx = 0
        if idx >= len(self._tokens):
            return self._tokens[-1]
        return self._tokens[idx]

    def advance(self) -> Token:
        tok = self.peek()
        if tok.kind != TokenKind.EOF:
            self._i += 1
        return tok

    def at_end(self) -> bool:
        return self.peek().kind == TokenKind.EOF


class _Parser:
    def __init__(
        self, *, tokens: list[Token], diagnostics: list[Diagnostic], path: str | None
    ) -> None:
        self._ts = _TokenStream(tokens)
        self.diagnostics = diagnostics
        self._path = path

    def _diag(self, message: str, *, at: Span | tuple[int, int]) -> None:
        if isinstance(at, Span):
            line = at.start_line
            col = at.start_col
        else:
            line, col = at
        self.diagnostics.append(
            Diagnostic(message=message, line=line, col=col, path=self._path)
        )

    def _missing_atom(self, *, at: tuple[int, int]) -> Atom:
        line, col = at
        span = Span.at(line, col)
        tok = Token(kind=TokenKind.MISSING, value="", span=span)
        return Atom(token=tok, span=span)

    def parse_root(self) -> Block:
        items: list[ClausewitzNode] = []
        while not self._ts.at_end():
            if self._ts.peek().kind == TokenKind.RBRACE:
                tok = self._ts.advance()
                self._diag("Unexpected '}'", at=tok.span)
                continue
            items.append(self._parse_item())

        eof = self._ts.peek()
        return Block(items=items, span=Span(1, 1, eof.span.end_line, eof.span.end_col))

    def _parse_item(self) -> ClausewitzNode:
        tok = self._ts.peek()
        if tok.kind == TokenKind.LBRACE:
            lbrace = self._ts.advance()
            self._diag("Unexpected '{' (block without key)", at=lbrace.span)
            return self._parse_block_after_lbrace(lbrace)

        if tok.kind in (TokenKind.BARE, TokenKind.STRING):
            key = self._ts.advance()
            if self._ts.peek().kind == TokenKind.OP:
                op = self._ts.advance()
                value = self._parse_value()
                span = Span(
                    key.span.start_line,
                    key.span.start_col,
                    value.span.end_line,
                    value.span.end_col,
                )
                return Assignment(key=key, op=op, value=value, span=span)
            return Atom(token=key, span=key.span)

        if tok.kind == TokenKind.OP:
            bad = self._ts.advance()
            self._diag("Unexpected operator", at=bad.span)
            return Atom(token=bad, span=bad.span)

        if tok.kind == TokenKind.RBRACE:
            bad = self._ts.advance()
            self._diag("Unexpected '}'", at=bad.span)
            return Atom(token=bad, span=bad.span)

        if tok.kind == TokenKind.EOF:
            return self._missing_atom(at=(tok.span.start_line, tok.span.start_col))

        bad = self._ts.advance()
        self._diag("Unexpected token", at=bad.span)
        return Atom(token=bad, span=bad.span)

    def _parse_value(self) -> ClausewitzNode:
        tok = self._ts.peek()
        if tok.kind == TokenKind.LBRACE:
            lbrace = self._ts.advance()
            return self._parse_block_after_lbrace(lbrace)

        if tok.kind in (TokenKind.BARE, TokenKind.STRING, TokenKind.OP):
            atom_tok = self._ts.advance()
            return Atom(token=atom_tok, span=atom_tok.span)

        if tok.kind in (TokenKind.RBRACE, TokenKind.EOF):
            self._diag("Expected value after operator", at=tok.span)
            return self._missing_atom(at=(tok.span.start_line, tok.span.start_col))

        bad = self._ts.advance()
        self._diag("Expected value after operator", at=bad.span)
        return Atom(token=bad, span=bad.span)

    def _parse_block_after_lbrace(self, lbrace: Token) -> Block:
        items: list[ClausewitzNode] = []
        while True:
            tok = self._ts.peek()
            if tok.kind == TokenKind.RBRACE:
                rbrace = self._ts.advance()
                span = Span(
                    lbrace.span.start_line,
                    lbrace.span.start_col,
                    rbrace.span.end_line,
                    rbrace.span.end_col,
                )
                return Block(items=items, span=span, lbrace=lbrace, rbrace=rbrace)
            if tok.kind == TokenKind.EOF:
                self._diag("Unterminated block; expected '}'", at=lbrace.span)
                span = Span(
                    lbrace.span.start_line,
                    lbrace.span.start_col,
                    tok.span.end_line,
                    tok.span.end_col,
                )
                return Block(items=items, span=span, lbrace=lbrace, rbrace=None)

            items.append(self._parse_item())


def parse(text: str, *, path: str | None = None) -> ParseResult:
    """Parse Clausewitz-like script text into an AST.

    The parser is recovery-oriented: it prefers accumulating diagnostics over
    raising exceptions.
    """

    tok_res = tokenize(text, path=path)
    diagnostics = list(tok_res.diagnostics)
    parser = _Parser(tokens=tok_res.tokens, diagnostics=diagnostics, path=path)
    root = parser.parse_root()
    return ParseResult(root=root, diagnostics=diagnostics, tokens=tok_res.tokens)
