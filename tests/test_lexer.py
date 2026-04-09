"""Tests for the Delphi lexer."""

from __future__ import annotations

import pytest

from pydelphiast.lexer import tokenize
from pydelphiast.tokens import TT


def toks(src: str):
    """Tokenise *src* and return types (excluding EOF)."""
    return [t.type for t in tokenize(src) if t.type != TT.EOF]


def vals(src: str):
    """Tokenise *src* and return values (excluding EOF)."""
    return [t.value for t in tokenize(src) if t.type != TT.EOF]


# ---------------------------------------------------------------------------
# Reserved words
# ---------------------------------------------------------------------------

class TestReservedWords:
    def test_unit(self):
        assert toks("unit") == [TT.UNIT]

    def test_begin_end(self):
        assert toks("begin end") == [TT.BEGIN, TT.END]

    def test_case_insensitive(self):
        assert toks("BEGIN END") == [TT.BEGIN, TT.END]
        assert toks("Begin End") == [TT.BEGIN, TT.END]

    def test_procedure(self):
        assert toks("procedure") == [TT.PROCEDURE]

    def test_function(self):
        assert toks("function") == [TT.FUNCTION]


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------

class TestDirectives:
    def test_virtual(self):
        assert toks("virtual") == [TT.D_VIRTUAL]

    def test_override(self):
        assert toks("override") == [TT.D_OVERRIDE]

    def test_published(self):
        assert toks("published") == [TT.D_PUBLISHED]

    def test_cdecl(self):
        assert toks("cdecl") == [TT.D_CDECL]


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

class TestLiterals:
    def test_integer(self):
        ts = tokenize("42")
        assert ts[0].type == TT.INTEGER
        assert ts[0].value == "42"

    def test_float(self):
        ts = tokenize("3.14")
        assert ts[0].type == TT.FLOAT
        assert ts[0].value == "3.14"

    def test_float_exp(self):
        ts = tokenize("1e5")
        assert ts[0].type == TT.FLOAT

    def test_hex(self):
        ts = tokenize("$FF")
        assert ts[0].type == TT.HEX
        assert ts[0].value == "$FF"

    def test_string(self):
        ts = tokenize("'hello'")
        assert ts[0].type == TT.STRING
        assert ts[0].value == "hello"

    def test_string_escaped_quote(self):
        ts = tokenize("'it''s'")
        assert ts[0].type == TT.STRING
        assert ts[0].value == "it's"

    def test_char_literal(self):
        ts = tokenize("#13")
        assert ts[0].type == TT.CHAR

    def test_char_hex_literal(self):
        ts = tokenize("#$0D")
        assert ts[0].type == TT.CHAR

    def test_string_with_hash_concat(self):
        ts = tokenize("'hello'#13#10")
        assert ts[0].type == TT.STRING
        assert "\r" in ts[0].value or "\n" in ts[0].value or ts[0].value == "hello\r\n"


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class TestOperators:
    def test_assign(self):
        assert toks(":=") == [TT.ASSIGN]

    def test_neq(self):
        assert toks("<>") == [TT.NEQ]

    def test_lte(self):
        assert toks("<=") == [TT.LTE]

    def test_gte(self):
        assert toks(">=") == [TT.GTE]

    def test_dotdot(self):
        assert toks("..") == [TT.DOTDOT]

    def test_dot(self):
        assert toks(".") == [TT.DOT]


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

class TestComments:
    def test_line_comment_skipped(self):
        assert toks("// this is a comment\nend") == [TT.END]

    def test_brace_comment_skipped(self):
        assert toks("{ comment } end") == [TT.END]

    def test_paren_comment_skipped(self):
        assert toks("(* comment *) end") == [TT.END]

    def test_compiler_directive_kept(self):
        assert toks("{$IFDEF WIN32}") == [TT.COMPILER_DIR]

    def test_paren_compiler_directive_kept(self):
        assert toks("(*$R+*)") == [TT.COMPILER_DIR]


# ---------------------------------------------------------------------------
# Position tracking
# ---------------------------------------------------------------------------

class TestPositions:
    def test_line_tracking(self):
        ts = tokenize("unit\nFoo")
        assert ts[0].line == 1
        assert ts[1].line == 2

    def test_col_tracking(self):
        ts = tokenize("  unit")
        assert ts[0].col == 3   # 1-based, after 2 spaces


# ---------------------------------------------------------------------------
# Full small snippet
# ---------------------------------------------------------------------------

class TestSnippet:
    def test_unit_header(self):
        src = "unit MyUnit;"
        types = toks(src)
        assert types == [TT.UNIT, TT.IDENT, TT.SEMI]
        assert vals(src)[1] == "MyUnit"

    def test_uses_clause(self):
        src = "uses SysUtils, Classes;"
        types = toks(src)
        assert types[0] == TT.USES
        assert TT.COMMA in types
        assert types[-1] == TT.SEMI
