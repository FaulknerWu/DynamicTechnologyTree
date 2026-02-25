from __future__ import annotations

from dtt_core.clausewitz_parser import Atom, ClausewitzNode, TokenKind

TRUTHY_LITERALS = frozenset({"yes", "true", "1", "on"})
FALSY_LITERALS = frozenset({"no", "false", "0", "off"})


def _atom_text(node: ClausewitzNode) -> str | None:
    if not isinstance(node, Atom):
        return None
    if node.token.kind in (TokenKind.BARE, TokenKind.STRING):
        return node.token.value
    return None

