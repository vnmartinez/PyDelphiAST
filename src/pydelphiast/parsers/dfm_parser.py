"""Parser for Delphi Form (.dfm) text files.

Produces an AST dict with the structure::

    {
      "kind": "Form",
      "objectKind": "object" | "inherited" | "inline",
      "name": "Form1",
      "className": "TForm1",
      "properties": [...],
      "children": [...],
      "startPos": {"line": N, "col": N},
      "endPos": {"line": N, "col": N}
    }

Binary .dfm files are not supported; convert them first with the Delphi
``convert`` utility or Lazarus.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..errors import ParseError


# ---------------------------------------------------------------------------
# Tokenizer (simple line/word based – DFM has a simple grammar)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"'(?:[^']|'')*'"          # string literal
    r"|[A-Za-z_][A-Za-z0-9_.]*"  # identifier / qualified name
    r"|\$[0-9A-Fa-f]+"         # hex literal
    r"|-?[0-9]+(?:\.[0-9]+)?"  # integer / float (possibly negative)
    r"|:=|<>|<="               # multi-char ops
    r"|[=(){}\[\],+\-*/<>]"    # single-char ops
    r"|#[0-9]+"                # char literal
    r"|{[^}]*}"                # hex data block  { FF 00 ... }
    r"|\([\s\S]*?\)"           # items list  ( ... )  – lazy, inner parens ok?
)

# We use a recursive line parser instead of regexes for the full DFM grammar.


class DfmLexer:
    """Minimal tokeniser for text-mode DFM files."""

    def __init__(self, src: str) -> None:
        self.lines = src.splitlines()
        self.line_idx = 0    # 0-based
        self.col = 0         # 0-based
        self._buf = ""
        self._buf_line = 0
        self._buf_col = 0
        self._reload()

    def _reload(self) -> None:
        if self.line_idx < len(self.lines):
            self._buf = self.lines[self.line_idx].lstrip()
            # actual column of first non-space char
            stripped = self.lines[self.line_idx]
            self._buf_col = len(stripped) - len(stripped.lstrip()) + 1
            self._buf_line = self.line_idx + 1  # 1-based
        else:
            self._buf = ""

    @property
    def pos(self) -> Tuple[int, int]:
        """Current 1-based (line, col) position."""
        return self._buf_line, self._buf_col

    def skip_blank(self) -> None:
        while self.line_idx < len(self.lines) and not self._buf.strip():
            self.line_idx += 1
            self._reload()

    def peek_word(self) -> str:
        """Peek at the first whitespace-delimited word on the current buffer."""
        return self._buf.split()[0] if self._buf.split() else ""

    def read_line(self) -> str:
        """Return the remaining buffer for the current line and advance."""
        s = self._buf
        self.line_idx += 1
        self._reload()
        return s.strip()

    def read_token(self) -> str:
        """Read the next whitespace-delimited token."""
        self.skip_blank()
        if not self._buf:
            return ""
        parts = self._buf.split(None, 1)
        tok = parts[0]
        self._buf = parts[1] if len(parts) > 1 else ""
        self._buf_col += len(tok)
        return tok

    def read_until_end(self) -> str:
        """Read all content until the matching 'end' keyword (for items)."""
        depth = 1
        lines: List[str] = []
        while self.line_idx < len(self.lines):
            raw = self.lines[self.line_idx]
            stripped = raw.strip().lower()
            self.line_idx += 1
            self._reload()
            if stripped == "end":
                depth -= 1
                if depth == 0:
                    break
            elif stripped.startswith(("object ", "inherited ", "inline ")):
                depth += 1
            lines.append(raw)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class DfmParser:
    """Parse a text-mode Delphi .dfm file into an AST dict."""

    def __init__(self, src: str, filename: str = "<unknown>") -> None:
        self.src = src
        self.filename = filename

    def parse(self) -> dict:
        lex = DfmLexer(self.src)
        lex.skip_blank()
        node = self._parse_object(lex)
        return node

    # ------------------------------------------------------------------

    def _parse_object(self, lex: DfmLexer) -> dict:
        lex.skip_blank()
        sl, sc = lex.pos
        header = lex.read_line()
        parts = header.split()
        if not parts:
            raise ParseError("Empty DFM object header", sl, sc, self.filename)

        obj_kind = parts[0].lower()
        if obj_kind not in ("object", "inherited", "inline"):
            raise ParseError(
                f"Expected object/inherited/inline, got {parts[0]!r}", sl, sc, self.filename
            )

        name = ""
        class_name = ""
        # Format: object Name: ClassName  or  object ClassName (anonymous)
        rest = " ".join(parts[1:])
        if ":" in rest:
            name_part, class_part = rest.split(":", 1)
            name = name_part.strip()
            class_name = class_part.strip()
        else:
            class_name = rest.strip()

        properties: List[dict] = []
        children: List[dict] = []

        while lex.line_idx < len(lex.lines):
            lex.skip_blank()
            if not lex._buf:
                break

            first_word = lex._buf.split()[0].lower()

            if first_word == "end":
                lex.read_line()  # consume 'end'
                break
            elif first_word in ("object", "inherited", "inline"):
                children.append(self._parse_object(lex))
            else:
                prop = self._parse_property(lex)
                if prop:
                    properties.append(prop)

        el, ec = lex.pos

        return {
            "kind": "DfmObject",
            "objectKind": obj_kind,
            "name": name,
            "className": class_name,
            "properties": properties,
            "children": children,
            "startPos": {"line": sl, "col": sc},
            "endPos": {"line": el, "col": ec},
        }

    def _parse_property(self, lex: DfmLexer) -> Optional[dict]:
        lex.skip_blank()
        sl, sc = lex.pos
        line = lex.read_line()
        if not line:
            return None

        # Split on first '='
        if "=" not in line:
            # Could be a multi-line item list or binary data continuation
            return {"kind": "DfmRawLine", "value": line, "startPos": {"line": sl, "col": sc}}

        eq_idx = line.index("=")
        prop_name = line[:eq_idx].strip()
        raw_value = line[eq_idx + 1:].strip()

        value = self._parse_value(raw_value, lex, sl, sc)

        return {
            "kind": "DfmProperty",
            "name": prop_name,
            "value": value,
            "startPos": {"line": sl, "col": sc},
        }

    def _parse_value(self, raw: str, lex: DfmLexer, sl: int, sc: int) -> Any:
        """Convert a raw DFM value string to a Python value."""
        if not raw:
            return None

        # Multi-line string / items list starting with (
        if raw == "(":
            lines: List[str] = []
            while lex.line_idx < len(lex.lines):
                lex.skip_blank()
                l = lex.read_line()
                if l == ")":
                    break
                lines.append(l)
            return {"kind": "DfmList", "items": [self._parse_value(ln, lex, sl, sc) for ln in lines]}

        # Set literal  [akLeft, akTop]
        if raw.startswith("["):
            inner = raw.strip("[]")
            items = [s.strip() for s in inner.split(",") if s.strip()]
            return {"kind": "DfmSet", "items": items}

        # Hex data block  {FF 00 ...}  possibly multi-line
        if raw.startswith("{"):
            data = raw
            if not raw.endswith("}"):
                while lex.line_idx < len(lex.lines):
                    lex.skip_blank()
                    extra = lex.read_line()
                    data += " " + extra
                    if extra.endswith("}"):
                        break
            return {"kind": "DfmBinary", "data": data}

        # String literal
        if raw.startswith("'"):
            # Strip outer quotes (already handled concatenation in read_line)
            return raw

        # Boolean
        if raw.lower() in ("true", "false"):
            return raw.lower() == "true"

        # Numeric
        if raw.startswith("$"):
            try:
                return int(raw[1:], 16)
            except ValueError:
                pass
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            pass

        # Identifier / enum value / expression – keep as string
        return raw


def parse_dfm(src: str, filename: str = "<unknown>") -> dict:
    """Parse a text DFM source string; return the AST dict."""
    return DfmParser(src, filename).parse()
