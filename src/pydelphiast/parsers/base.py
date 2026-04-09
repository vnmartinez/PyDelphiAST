"""Base parser class with token-navigation utilities."""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..errors import ParseError
from ..tokens import DIRECTIVE_TYPES, TT
from ..lexer import Token


class BaseParser:
    """Common token-navigation machinery shared by all Delphi parsers.

    Sub-classes call :meth:`expect`, :meth:`match`, :meth:`check` etc.
    to walk the flat ``tokens`` list.
    """

    def __init__(self, tokens: List[Token], filename: str = "") -> None:
        self.tokens = tokens
        self.filename = filename
        self.pos = 0

    # ------------------------------------------------------------------
    # Current token helpers
    # ------------------------------------------------------------------

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def peek(self, offset: int = 1) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.type != TT.EOF:
            self.pos += 1
        return tok

    # ------------------------------------------------------------------
    # Check / match helpers
    # ------------------------------------------------------------------

    def check(self, *types: TT) -> bool:
        """Return True if the current token is one of *types*."""
        return self.current.type in types

    def check_value(self, *values: str) -> bool:
        """Case-insensitive value check (for directive keywords used as idents)."""
        return self.current.value.lower() in {v.lower() for v in values}

    def match(self, *types: TT) -> Optional[Token]:
        """Consume and return the current token if its type is in *types*."""
        if self.current.type in types:
            return self.advance()
        return None

    def expect(self, *types: TT) -> Token:
        """Consume the current token, raising :class:`ParseError` if type mismatch."""
        if self.current.type not in types:
            expected = " or ".join(t.name for t in types)
            raise self._error(
                f"Expected {expected}, got {self.current.type.name} ({self.current.value!r})"
            )
        return self.advance()

    # ------------------------------------------------------------------
    # Identifier helpers
    # ------------------------------------------------------------------

    def is_ident(self, tok: Optional[Token] = None) -> bool:
        """True if *tok* (default: current) is an identifier or a directive word."""
        t = tok or self.current
        return t.type == TT.IDENT or t.type in DIRECTIVE_TYPES

    def expect_ident(self) -> Token:
        """Consume an identifier (or a directive used as identifier)."""
        if not self.is_ident():
            raise self._error(
                f"Expected identifier, got {self.current.type.name} ({self.current.value!r})"
            )
        return self.advance()

    def try_ident(self) -> Optional[Token]:
        """Consume and return an identifier / directive-as-ident, or None."""
        if self.is_ident():
            return self.advance()
        return None

    # ------------------------------------------------------------------
    # Position helpers
    # ------------------------------------------------------------------

    def pos_of(self, tok: Token) -> dict:
        return {"line": tok.line, "col": tok.col}

    def end_pos_of(self, tok: Token) -> dict:
        return {"line": tok.end_line, "col": tok.end_col}

    def span(self, start_tok: Token, end_tok: Optional[Token] = None) -> Tuple[dict, dict]:
        end = end_tok or self.tokens[max(0, self.pos - 1)]
        return self.pos_of(start_tok), self.end_pos_of(end)

    # ------------------------------------------------------------------
    # Error factory
    # ------------------------------------------------------------------

    def _error(self, msg: str) -> ParseError:
        tok = self.current
        return ParseError(msg, tok.line, tok.col, self.filename)

    # ------------------------------------------------------------------
    # Qualified name
    # ------------------------------------------------------------------

    def parse_qualified_name(self) -> str:
        """Parse ``A.B.C`` qualified names; returns the dotted string."""
        parts = [self.expect_ident().value]
        while self.check(TT.DOT) and self.is_ident(self.peek()):
            self.advance()  # .
            parts.append(self.expect_ident().value)
        return ".".join(parts)

    # ------------------------------------------------------------------
    # Skip compiler directives encountered inline (e.g. {$IFDEF ...})
    # ------------------------------------------------------------------

    def skip_compiler_dirs(self) -> List[str]:
        """Consume any leading COMPILER_DIR tokens, return their values."""
        dirs: List[str] = []
        while self.check(TT.COMPILER_DIR):
            dirs.append(self.advance().value)
        return dirs
