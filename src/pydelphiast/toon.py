"""TOON (Token-Oriented Object Notation) export for PyDelphiAST.

Two layers:

* ``encode_toon(value)`` - generic TOON encoder (knows nothing about Delphi).
* ``extract_compact_hierarchy(ast)`` - reduces a full or slim AST to the
  essential hierarchy: group > projects > units > form/types > methods.

``to_toon(ast)`` composes both.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any, List, Optional

__all__ = ["encode_toon"]


# ---------------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------------

_INDENT = "  "
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")
_LEADING_ZERO_RE = re.compile(r"^0\d+$")
_SPECIAL_CHARS = frozenset(':"\\[]{},\n\r\t')
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _needs_quotes(s: str) -> bool:
    if s == "" or s != s.strip():
        return True
    if s in ("true", "false", "null"):
        return True
    if _NUMERIC_RE.match(s) or _LEADING_ZERO_RE.match(s):
        return True
    if s.startswith("-"):
        return True
    return any(c in _SPECIAL_CHARS for c in s)


def _quote(s: str) -> str:
    return '"' + "".join(_ESCAPES.get(c, c) for c in s) + '"'


def _fmt_number(n: Any) -> str:
    if isinstance(n, float):
        if not math.isfinite(n):
            return "null"
        if n == 0:
            return "0"
        if n.is_integer():
            return str(int(n))
        text = repr(n)
        if "e" in text or "E" in text:
            text = format(Decimal(text), "f")
        return text
    return str(n)


def _fmt_primitive(v: Any) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return _fmt_number(v)
    if isinstance(v, str):
        return _quote(v) if _needs_quotes(v) else v
    raise TypeError(f"Cannot encode {type(v).__name__} as TOON")


def _fmt_key(k: Any) -> str:
    if not isinstance(k, str):
        raise TypeError(f"TOON keys must be str, got {type(k).__name__}")
    return k if _KEY_RE.match(k) else _quote(k)


def _is_primitive(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _tabular_fields(items: list) -> Optional[List[str]]:
    if not items or not all(isinstance(i, dict) and i for i in items):
        return None
    fields = list(items[0].keys())
    for item in items:
        if list(item.keys()) != fields:
            return None
        if not all(_is_primitive(v) for v in item.values()):
            return None
    return fields


def _encode_object(obj: dict, depth: int, lines: List[str]) -> None:
    pad = _INDENT * depth
    for k, v in obj.items():
        key = _fmt_key(k)
        if isinstance(v, dict):
            lines.append(f"{pad}{key}:")
            _encode_object(v, depth + 1, lines)
        elif isinstance(v, list):
            _encode_array(key, v, depth, lines)
        else:
            lines.append(f"{pad}{key}: {_fmt_primitive(v)}")


def _encode_array(key: str, arr: list, depth: int, lines: List[str]) -> None:
    pad = _INDENT * depth
    n = len(arr)
    if all(_is_primitive(v) for v in arr):
        values = ",".join(_fmt_primitive(v) for v in arr)
        lines.append(f"{pad}{key}[{n}]:" + (f" {values}" if arr else ""))
        return
    fields = _tabular_fields(arr)
    if fields:
        header = ",".join(_fmt_key(f) for f in fields)
        lines.append(f"{pad}{key}[{n}]{{{header}}}:")
        row_pad = _INDENT * (depth + 1)
        for item in arr:
            lines.append(row_pad + ",".join(_fmt_primitive(item[f]) for f in fields))
        return
    lines.append(f"{pad}{key}[{n}]:")
    for item in arr:
        _encode_list_item(item, depth + 1, lines)


def _encode_list_item(item: Any, depth: int, lines: List[str]) -> None:
    pad = _INDENT * depth
    if _is_primitive(item):
        lines.append(f"{pad}- {_fmt_primitive(item)}")
        return
    sub: List[str] = []
    if isinstance(item, dict):
        if not item:
            lines.append(f"{pad}-")
            return
        _encode_object(item, 0, sub)
        cont = pad + _INDENT
    elif isinstance(item, list):
        _encode_array("", item, 0, sub)
        cont = pad
    else:
        raise TypeError(f"Cannot encode {type(item).__name__} as TOON")
    lines.append(f"{pad}- {sub[0]}")
    lines.extend(cont + s for s in sub[1:])


def encode_toon(value: Any) -> str:
    """Encode a JSON-like value (dict/list/primitive) as TOON text.

    Indentation is 2 spaces, delimiter is ``,``, no trailing newline.
    Raises ``TypeError`` for values that are not str/int/float/bool/None/dict/list.
    """
    lines: List[str] = []
    if isinstance(value, dict):
        _encode_object(value, 0, lines)
    elif isinstance(value, list):
        _encode_array("", value, 0, lines)
    else:
        lines.append(_fmt_primitive(value))
    return "\n".join(lines)
