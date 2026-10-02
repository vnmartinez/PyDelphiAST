"""TOON (Token-Oriented Object Notation) export for PyDelphiAST.

Two layers:

* ``encode_toon(value)`` - generic TOON encoder (knows nothing about Delphi).
* ``extract_compact_hierarchy(ast)`` - reduces a full or slim AST to the
  essential hierarchy: group > projects > units > form/types > methods.

``to_toon(ast)`` composes both.
"""

from __future__ import annotations

import math
import os
import re
from decimal import Decimal
from typing import Any, Iterator, List, Optional, Tuple

__all__ = ["encode_toon", "extract_compact_hierarchy"]


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


# ---------------------------------------------------------------------------
# Delphi type / parameter formatting
# ---------------------------------------------------------------------------

def _type_str(node: Any) -> str:
    """Render a type node (TypeRef, StringType, ...) as compact Delphi text."""
    if not isinstance(node, dict):
        return ""
    kind = node.get("kind", "")
    if kind == "TypeRef":
        name = node.get("name", "")
        args = node.get("typeArgs") or []
        if args:
            name += "<" + ",".join(_type_str(a) for a in args) + ">"
        return name
    if kind == "StringType":
        return "string"
    if kind in ("OpenArrayType", "ArrayType"):
        elem = node.get("elementType")
        return "array of " + (_type_str(elem) if elem else "const")
    if kind == "SetType":
        return "set of " + _type_str(node.get("baseType"))
    if kind == "PointerType":
        return "^" + _type_str(node.get("baseType"))
    if kind == "ProcType":
        return "function" if node.get("isFunction") else "procedure"
    if kind == "MethodReference":
        return "reference to " + _type_str(node.get("procType"))
    return kind


def _params_str(params: Any) -> str:
    """Render a parameter list as ``const A,B:string; var C:Integer``."""
    parts: List[str] = []
    for pg in params or []:
        if not isinstance(pg, dict):
            continue
        mod = pg.get("modifier")
        prefix = f"{mod} " if mod else ""
        if pg.get("kind") == "OpenArrayParam":
            elem = pg.get("elementType")
            parts.append(prefix + "array of " + (_type_str(elem) if elem else "const"))
            continue
        names = ",".join(pg.get("names") or [])
        tname = _type_str(pg.get("typeRef"))
        parts.append(f"{prefix}{names}:{tname}" if tname else f"{prefix}{names}")
    return "; ".join(parts)


def _method_row(m: dict) -> dict:
    """Return the tabular row ``{vis, kind, name, params, returns}`` of a MethodDecl."""
    kind = m.get("methodKind", "")
    if m.get("isClassMember"):
        kind = "class " + kind
    return {
        "vis": m.get("visibility") or "public",
        "kind": kind,
        "name": m.get("name", ""),
        "params": _params_str(m.get("params")),
        "returns": _type_str(m.get("returnType")),
    }


# ---------------------------------------------------------------------------
# Compact hierarchy extraction
# ---------------------------------------------------------------------------

_TYPE_KINDS = {
    "ClassType": "class",
    "InterfaceType": "interface",
    "DispinterfaceType": "dispinterface",
    "RecordType": "record",
    "ObjectType": "object",
}
_SECTION_KINDS = ("TypeSection", "ConstSection", "VarSection")
_PLURAL = {"group": "groups", "project": "projects", "unit": "units",
           "form": "forms", "error": "errors"}


def _prune(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v != "" and v != [] and v != {}}


def _stem(path: Any) -> str:
    return os.path.splitext(os.path.basename(path or ""))[0]


def _rel(path: Any, base: str) -> str:
    """Path relative to *base*, POSIX separators; absolute if on another drive."""
    if not path:
        return ""
    abs_path = os.path.abspath(path)
    try:
        rel = os.path.relpath(abs_path, base)
    except ValueError:
        rel = abs_path
    return rel.replace("\\", "/")


def _iter_decls(section: Any) -> Iterator[dict]:
    """Yield declarations of a section, flattening Type/Const/Var sections."""
    if not isinstance(section, dict):
        return
    for d in section.get("declarations") or []:
        if not isinstance(d, dict):
            continue
        if d.get("kind") in _SECTION_KINDS:
            yield from (i for i in d.get("items") or [] if isinstance(i, dict))
        else:
            yield d


def _compact_type(decl: dict) -> Optional[dict]:
    td = decl.get("typeDefinition") or {}
    if td.get("kind") == "PackedType":
        td = td.get("inner") or {}
    label = _TYPE_KINDS.get(td.get("kind", ""))
    if not label or td.get("isForward"):
        return None
    if td.get("isHelper"):
        label += " helper"
    out: dict = {"name": decl.get("name", ""), "kind": label}
    if td.get("helperFor"):
        out["for"] = _type_str(td["helperFor"])
    out["ancestors"] = [_type_str(a) for a in td.get("ancestors") or []]
    members = td.get("members") or td.get("fields") or []
    out["methods"] = [
        _method_row(m) for m in members
        if isinstance(m, dict) and m.get("kind") == "MethodDecl"
    ]
    return _prune(out)


def _compact_form(node: dict, base: str, fallback_path: str = "") -> dict:
    path = node.get("filename") or fallback_path
    if node.get("kind") == "ParseError":
        return _prune({"path": _rel(path, base), "error": node.get("message", "")})
    return _prune({
        "name": node.get("name"),
        "class": node.get("className"),
        "path": _rel(path, base),
    })


def _compact_unit(node: dict, base: str) -> dict:
    kind = node.get("kind")
    if kind == "CircularRef":
        path = node.get("path", "")
        return {"name": _stem(path), "path": _rel(path, base), "ref": True}
    path = node.get("filename", "")
    if kind == "ParseError":
        return _prune({"name": _stem(path), "path": _rel(path, base),
                       "error": node.get("message", "")})
    out: dict = {"name": node.get("name") or _stem(path), "path": _rel(path, base)}
    form = node.get("form")
    if isinstance(form, dict):
        fallback = os.path.splitext(path)[0] + ".dfm" if path else ""
        out["form"] = _compact_form(form, base, fallback)
    types: List[dict] = []
    for section in ("interface", "implementation"):
        for d in _iter_decls(node.get(section)):
            if d.get("kind") == "TypeDecl":
                t = _compact_type(d)
                if t:
                    types.append(t)
    out["types"] = types
    return _prune(out)


def _compact_root(node: dict, base: str) -> Tuple[Optional[str], Optional[dict]]:
    kind = node.get("kind")
    if kind == "Unit":
        return "unit", _compact_unit(node, base)
    if kind == "DfmObject":
        return "form", _compact_form(node, base)
    if kind == "ParseError":
        return "error", _prune({"path": _rel(node.get("filename", ""), base),
                                "message": node.get("message", "")})
    return None, None


def _default_base(nodes: list) -> str:
    dirs = [
        os.path.dirname(os.path.abspath(n["filename"]))
        for n in nodes
        if isinstance(n, dict) and n.get("filename")
    ]
    if not dirs:
        return os.getcwd()
    try:
        return os.path.commonpath(dirs)
    except ValueError:  # different drives
        return dirs[0]


def extract_compact_hierarchy(ast: Any, base_dir: Optional[str] = None) -> dict:
    """Reduce a full or slim AST to the essential hierarchy for TOON export.

    Every file-backed level carries a ``path`` relative to ``base`` (POSIX
    separators). ``base`` defaults to the directory of the root file.
    """
    nodes = ast if isinstance(ast, list) else [ast]
    base = os.path.abspath(base_dir) if base_dir else _default_base(nodes)
    out: dict = {"base": base.replace("\\", "/")}
    if isinstance(ast, list):
        for n in nodes:
            if not isinstance(n, dict):
                continue
            key, val = _compact_root(n, base)
            if key:
                out.setdefault(_PLURAL[key], []).append(val)
    elif isinstance(ast, dict):
        key, val = _compact_root(ast, base)
        if key:
            out[key] = val
    return out
