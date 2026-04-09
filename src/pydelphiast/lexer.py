"""Delphi 10 lexer – converts source text into a flat token list."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .errors import LexerError
from .tokens import ALL_KEYWORDS, TT


# ---------------------------------------------------------------------------
# Token dataclass
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Token:
    type: TT
    value: str
    line: int       # 1-based
    col: int        # 1-based
    end_line: int
    end_col: int

    def pos_dict(self) -> dict:
        return {"line": self.line, "col": self.col}

    def end_pos_dict(self) -> dict:
        return {"line": self.end_line, "col": self.end_col}

    def __repr__(self) -> str:  # pragma: no cover
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.col})"


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

class Lexer:
    """Tokenizes a Delphi source string into a list of :class:`Token` objects.

    Call :meth:`tokenize` to get all tokens.  The last token is always EOF.
    Comments and whitespace are silently consumed.  Compiler directives
    (``{$...}`` / ``(*$...*)``) are emitted as ``COMPILER_DIR`` tokens so the
    parser can inspect them.
    """

    __slots__ = ("src", "filename", "pos", "line", "col", "tokens")

    def __init__(self, src: str, filename: str = "<unknown>") -> None:
        self.src = src
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[Token] = []

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def tokenize(self) -> List[Token]:
        while self.pos < len(self.src):
            self._skip_whitespace()
            if self.pos >= len(self.src):
                break
            self._next_token()
        self.tokens.append(Token(TT.EOF, "", self.line, self.col, self.line, self.col))
        return self.tokens

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ch(self, offset: int = 0) -> Optional[str]:
        idx = self.pos + offset
        return self.src[idx] if idx < len(self.src) else None

    def _advance(self) -> str:
        ch = self.src[self.pos]
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        self.pos += 1
        return ch

    def _skip_whitespace(self) -> None:
        while self.pos < len(self.src) and self.src[self.pos] in " \t\r\n":
            self._advance()

    def _error(self, msg: str) -> LexerError:
        return LexerError(msg, self.line, self.col, self.filename)

    # ------------------------------------------------------------------
    # Token dispatch
    # ------------------------------------------------------------------

    def _next_token(self) -> None:  # noqa: C901 (complexity ok for a lexer)
        sl, sc = self.line, self.col
        ch = self.src[self.pos]

        # ── Single-line comment ──────────────────────────────────────────
        if ch == "/" and self._ch(1) == "/":
            while self.pos < len(self.src) and self.src[self.pos] != "\n":
                self._advance()
            return

        # ── Brace comment / compiler directive ─────────────────────────
        if ch == "{":
            if self._ch(1) == "$":
                tok = self._read_brace_directive(sl, sc)
                self.tokens.append(tok)
            else:
                self._skip_brace_comment()
            return

        # ── Paren-star comment / compiler directive ─────────────────────
        if ch == "(" and self._ch(1) == "*":
            if self._ch(2) == "$":
                tok = self._read_paren_directive(sl, sc)
                self.tokens.append(tok)
            else:
                self._skip_paren_comment()
            return

        # ── String literal ───────────────────────────────────────────────
        if ch == "'":
            self.tokens.append(self._read_string(sl, sc))
            return

        # ── Char literal  #nn  #$nn ──────────────────────────────────────
        if ch == "#":
            self.tokens.append(self._read_char(sl, sc))
            return

        # ── Hex literal  $FFFF ───────────────────────────────────────────
        if ch == "$":
            self.tokens.append(self._read_hex(sl, sc))
            return

        # ── Numeric literal ──────────────────────────────────────────────
        if ch.isdigit():
            self.tokens.append(self._read_number(sl, sc))
            return

        # ── Identifier / keyword ─────────────────────────────────────────
        if ch.isalpha() or ch == "_":
            self.tokens.append(self._read_ident(sl, sc))
            return

        # ── Operators and punctuation ────────────────────────────────────
        self._advance()  # consume first char

        if ch == ":":
            if self._ch() == "=":
                self._advance()
                self.tokens.append(Token(TT.ASSIGN, ":=", sl, sc, self.line, self.col))
            else:
                self.tokens.append(Token(TT.COLON, ":", sl, sc, self.line, self.col))

        elif ch == ".":
            if self._ch() == ".":
                self._advance()
                self.tokens.append(Token(TT.DOTDOT, "..", sl, sc, self.line, self.col))
            else:
                self.tokens.append(Token(TT.DOT, ".", sl, sc, self.line, self.col))

        elif ch == "<":
            if self._ch() == ">":
                self._advance()
                self.tokens.append(Token(TT.NEQ, "<>", sl, sc, self.line, self.col))
            elif self._ch() == "=":
                self._advance()
                self.tokens.append(Token(TT.LTE, "<=", sl, sc, self.line, self.col))
            else:
                self.tokens.append(Token(TT.LT, "<", sl, sc, self.line, self.col))

        elif ch == ">":
            if self._ch() == "=":
                self._advance()
                self.tokens.append(Token(TT.GTE, ">=", sl, sc, self.line, self.col))
            else:
                self.tokens.append(Token(TT.GT, ">", sl, sc, self.line, self.col))

        elif ch == "(":
            self.tokens.append(Token(TT.LPAREN, "(", sl, sc, self.line, self.col))
        elif ch == ")":
            self.tokens.append(Token(TT.RPAREN, ")", sl, sc, self.line, self.col))
        elif ch == "[":
            self.tokens.append(Token(TT.LBRACKET, "[", sl, sc, self.line, self.col))
        elif ch == "]":
            self.tokens.append(Token(TT.RBRACKET, "]", sl, sc, self.line, self.col))
        elif ch == "+":
            self.tokens.append(Token(TT.PLUS, "+", sl, sc, self.line, self.col))
        elif ch == "-":
            self.tokens.append(Token(TT.MINUS, "-", sl, sc, self.line, self.col))
        elif ch == "*":
            self.tokens.append(Token(TT.STAR, "*", sl, sc, self.line, self.col))
        elif ch == "/":
            self.tokens.append(Token(TT.SLASH, "/", sl, sc, self.line, self.col))
        elif ch == "=":
            self.tokens.append(Token(TT.EQ, "=", sl, sc, self.line, self.col))
        elif ch == "@":
            self.tokens.append(Token(TT.AT, "@", sl, sc, self.line, self.col))
        elif ch == "^":
            self.tokens.append(Token(TT.CARET, "^", sl, sc, self.line, self.col))
        elif ch == ",":
            self.tokens.append(Token(TT.COMMA, ",", sl, sc, self.line, self.col))
        elif ch == ";":
            self.tokens.append(Token(TT.SEMI, ";", sl, sc, self.line, self.col))
        else:
            raise self._error(f"Unexpected character: {ch!r}")

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def _skip_brace_comment(self) -> None:
        self._advance()  # {
        while self.pos < len(self.src):
            if self._advance() == "}":
                return
        raise self._error("Unterminated brace comment")

    def _skip_paren_comment(self) -> None:
        self._advance(); self._advance()  # (*
        while self.pos < len(self.src):
            ch = self._advance()
            if ch == "*" and self._ch() == ")":
                self._advance()
                return
        raise self._error("Unterminated (* comment")

    def _read_brace_directive(self, sl: int, sc: int) -> Token:
        """Read ``{$...}`` compiler directive."""
        raw = ""
        self._advance()  # {
        while self.pos < len(self.src):
            ch = self._advance()
            raw += ch
            if ch == "}":
                break
        else:
            raise self._error("Unterminated compiler directive")
        return Token(TT.COMPILER_DIR, "{" + raw, sl, sc, self.line, self.col)

    def _read_paren_directive(self, sl: int, sc: int) -> Token:
        """Read ``(*$...*)``) compiler directive."""
        raw = ""
        self._advance(); self._advance()  # (*
        while self.pos < len(self.src):
            ch = self._advance()
            if ch == "*" and self._ch() == ")":
                self._advance()
                break
            raw += ch
        else:
            raise self._error("Unterminated compiler directive")
        return Token(TT.COMPILER_DIR, "(*" + raw + "*)", sl, sc, self.line, self.col)

    # ------------------------------------------------------------------
    # Literals
    # ------------------------------------------------------------------

    def _read_string(self, sl: int, sc: int) -> Token:
        """Read a quoted string, handling doubled-quote escapes.

        Delphi allows adjacent string / char fragments: ``'foo'#13#10'bar'``
        The lexer emits a single STRING token with the *raw concatenated value*
        (quotes and #nn included) so that the parser can reconstruct it.
        """
        raw = ""
        while self.pos < len(self.src) and self.src[self.pos] in ("'", "#"):
            if self.src[self.pos] == "#":
                # char literal embedded in string
                raw += self._read_char_raw()
            else:
                self._advance()  # opening '
                while self.pos < len(self.src):
                    ch = self._advance()
                    if ch == "'":
                        if self._ch() == "'":
                            self._advance()
                            raw += "'"
                        else:
                            break
                    else:
                        raw += ch
        return Token(TT.STRING, raw, sl, sc, self.line, self.col)

    def _read_char_raw(self) -> str:
        """Consume a ``#nn`` or ``#$nn`` fragment; return the decoded char."""
        self._advance()  # #
        if self._ch() == "$":
            self._advance()
            digits = ""
            while self.pos < len(self.src) and self.src[self.pos] in "0123456789ABCDEFabcdef":
                digits += self._advance()
            return chr(int(digits, 16)) if digits else "\x00"
        else:
            digits = ""
            while self.pos < len(self.src) and self.src[self.pos].isdigit():
                digits += self._advance()
            return chr(int(digits)) if digits else "\x00"

    def _read_char(self, sl: int, sc: int) -> Token:
        """Read a standalone ``#nn`` char literal (not preceded by ``'``).

        The value stored is the raw ``#nn`` / ``#$nn`` text.
        """
        raw = "#"
        if self._ch(1) == "$":
            self._advance()  # #
            self._advance()  # $
            raw = "#$"
            while self.pos < len(self.src) and self.src[self.pos] in "0123456789ABCDEFabcdef":
                raw += self._advance()
        else:
            self._advance()  # #
            while self.pos < len(self.src) and self.src[self.pos].isdigit():
                raw += self._advance()
        return Token(TT.CHAR, raw, sl, sc, self.line, self.col)

    def _read_hex(self, sl: int, sc: int) -> Token:
        self._advance()  # $
        digits = ""
        while self.pos < len(self.src) and self.src[self.pos] in "0123456789ABCDEFabcdef":
            digits += self._advance()
        return Token(TT.HEX, "$" + digits, sl, sc, self.line, self.col)

    def _read_number(self, sl: int, sc: int) -> Token:
        raw = ""
        while self.pos < len(self.src) and self.src[self.pos].isdigit():
            raw += self._advance()

        is_float = False
        # Decimal part – only consume '.' if NOT followed by another '.' (range op)
        if self._ch() == "." and self._ch(1) != ".":
            nxt = self._ch(1)
            if nxt is not None and nxt.isdigit():
                is_float = True
                raw += self._advance()  # .
                while self.pos < len(self.src) and self.src[self.pos].isdigit():
                    raw += self._advance()

        # Exponent
        if self._ch() in ("e", "E"):
            is_float = True
            raw += self._advance()
            if self._ch() in ("+", "-"):
                raw += self._advance()
            while self.pos < len(self.src) and self.src[self.pos].isdigit():
                raw += self._advance()

        tt = TT.FLOAT if is_float else TT.INTEGER
        return Token(tt, raw, sl, sc, self.line, self.col)

    def _read_ident(self, sl: int, sc: int) -> Token:
        raw = ""
        while self.pos < len(self.src) and (self.src[self.pos].isalnum() or self.src[self.pos] == "_"):
            raw += self._advance()
        tt = ALL_KEYWORDS.get(raw.lower(), TT.IDENT)
        return Token(tt, raw, sl, sc, self.line, self.col)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def tokenize(src: str, filename: str = "<unknown>") -> List[Token]:
    """Return the full token list for *src* (last element is EOF)."""
    return Lexer(src, filename).tokenize()
