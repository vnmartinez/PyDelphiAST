# TOON Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export the essential Delphi hierarchy (group > projects > units > form/types > methods, with file paths at every level) as TOON text via `pydelphiast.to_toon()` and `python -m pydelphiast <file> --toon`.

**Architecture:** New module `src/pydelphiast/toon.py` with three independent layers: a generic TOON encoder (`encode_toon`), a Delphi-specific reducer (`extract_compact_hierarchy`) that accepts a full or `slim_ast` AST, and the composition `to_toon`. Two one-line fixes stamp missing file paths (`.dpr` root in `DelphiProject._parse_dpr`, companion form in `parse_file`). The CLI gains a `--toon` flag.

**Tech Stack:** Python >= 3.10 (stdlib only), pytest.

**Spec:** `docs/superpowers/specs/2026-10-02-toon-export-design.md`

## Global Constraints

- Zero external dependencies: stdlib only (`math`, `os`, `re`, `decimal`, `typing`).
- TOON output: 2-space indent, `,` delimiter, `\n` line endings, **no trailing newline**.
- Method rows always have the fields `vis,kind,name,params,returns`, in this order.
- Every `path`/`source` is relative to `base`, with `/` separators; `base` is absolute with `/` separators.
- CLI without `--toon` must behave exactly as before.
- Code style: match `src/pydelphiast/__init__.py` (type hints, `from __future__ import annotations`, section banners `# ----`), ruff line-length 100.
- Known parser limitations (do NOT try to fix here): the identifier `TO` and `class operator` inside records fail to parse; unlabeled class sections get visibility `published`.

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/pydelphiast/toon.py` | Create | Encoder, formatting helpers, compact hierarchy, `to_toon` |
| `tests/test_toon.py` | Create | All TOON tests (one section per task) |
| `src/pydelphiast/project.py` | Modify `_parse_dpr` | Stamp `filename` on `.dpr` root |
| `src/pydelphiast/__init__.py` | Modify imports, `__all__`, `parse_file` | Re-export API; stamp form `filename` |
| `src/pydelphiast/__main__.py` | Modify `_build_parser`, `main` | `--toon` flag |
| `CLAUDE.md`, `README.md` | Modify | Document `--toon` and the API |

## Setup (once, before Task 1)

The package must be importable by pytest (today `pytest` fails at collection without it):

```bash
pip install -e .
```

Then `pytest -q` → all existing tests PASS.

---

### Task 1: Generic TOON encoder

**Files:**
- Create: `src/pydelphiast/toon.py`
- Create: `tests/test_toon.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `encode_toon(value: Any) -> str` (raises `TypeError` for non JSON-like values); private helpers `_fmt_primitive`, `_is_primitive`, used only inside the module.

- [x] **Step 1: Write the failing tests**

Create `tests/test_toon.py` with:

```python
"""Tests for the TOON export (encoder, compact hierarchy, CLI)."""

from __future__ import annotations

import pytest

from pydelphiast.toon import encode_toon


# ---------------------------------------------------------------------------
# Task 1 – encoder
# ---------------------------------------------------------------------------

class TestEncodeToonPrimitives:
    @pytest.mark.parametrize("value, expected", [
        (None, "null"),
        (True, "true"),
        (False, "false"),
        (42, "42"),
        (-7, "-7"),
        (1.5, "1.5"),
        (2.0, "2"),
        (-0.0, "0"),
        (1e-7, "0.0000001"),
    ])
    def test_scalar_values(self, value, expected):
        assert encode_toon({"k": value}) == f"k: {expected}"

    @pytest.mark.parametrize("value, expected", [
        ("hello", "hello"),
        ("hello world", "hello world"),
        ("class function", "class function"),
        ("TList<T>", "TList<T>"),
        ("", '""'),
        (" a", '" a"'),
        ("a ", '"a "'),
        ("true", '"true"'),
        ("null", '"null"'),
        ("123", '"123"'),
        ("1.5", '"1.5"'),
        ("05", '"05"'),
        ("a:b", '"a:b"'),
        ("a,b", '"a,b"'),
        ("[x]", '"[x]"'),
        ("{x}", '"{x}"'),
        ("-x", '"-x"'),
        ('a"b', '"a\\"b"'),
        ("a\\b", '"a\\\\b"'),
        ("l1\nl2", '"l1\\nl2"'),
        ("t\tx", '"t\\tx"'),
    ])
    def test_string_quoting(self, value, expected):
        assert encode_toon({"k": value}) == f"k: {expected}"

    def test_key_needing_quotes(self):
        assert encode_toon({"my key": 1}) == '"my key": 1'

    def test_dotted_key_is_bare(self):
        assert encode_toon({"Font.Name": "Tahoma"}) == "Font.Name: Tahoma"

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            encode_toon({"s": {1, 2}})

    def test_root_primitive(self):
        assert encode_toon("x y") == "x y"


class TestEncodeToonStructures:
    def test_flat_object(self):
        assert encode_toon({"a": 1, "b": "x"}) == "a: 1\nb: x"

    def test_nested_object(self):
        assert encode_toon({"a": {"b": 1, "c": {"d": 2}}}) == "a:\n  b: 1\n  c:\n    d: 2"

    def test_empty_object(self):
        assert encode_toon({"a": {}}) == "a:"

    def test_primitive_array(self):
        assert encode_toon({"t": ["A", "B c", 3]}) == "t[3]: A,B c,3"

    def test_empty_array(self):
        assert encode_toon({"t": []}) == "t[0]:"

    def test_tabular_array(self):
        value = {"m": [{"x": 1, "y": "a"}, {"x": 2, "y": ""}]}
        assert encode_toon(value) == 'm[2]{x,y}:\n  1,a\n  2,""'

    def test_non_uniform_objects_use_list_form(self):
        value = {"u": [{"name": "A", "t": [{"x": 1}]}, {"name": "B"}]}
        assert encode_toon(value) == (
            "u[2]:\n"
            "  - name: A\n"
            "    t[1]{x}:\n"
            "      1\n"
            "  - name: B"
        )

    def test_list_item_with_nested_object(self):
        value = {"u": [{"name": "A", "form": {"name": "F"}}, {"name": "B"}]}
        assert encode_toon(value) == (
            "u[2]:\n"
            "  - name: A\n"
            "    form:\n"
            "      name: F\n"
            "  - name: B"
        )

    def test_mixed_list(self):
        value = {"x": [1, {"a": 1}, [1, 2]]}
        assert encode_toon(value) == "x[3]:\n  - 1\n  - a: 1\n  - [2]: 1,2"

    def test_root_list(self):
        assert encode_toon([1, 2]) == "[2]: 1,2"
```

- [x] **Step 2: Run test**

Run: `pytest tests/test_toon.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pydelphiast.toon'`

- [x] **Step 3: Implement the encoder**

Create `src/pydelphiast/toon.py`:

```python
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
```

- [x] **Step 4: Run tests**

Run: `pytest tests/test_toon.py -v`
Expected: all tests PASS

- [x] **Step 5: Commit**

```bash
git add src/pydelphiast/toon.py tests/test_toon.py
git commit -m "feat(toon): add generic TOON encoder

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Delphi type, parameter and method-row formatting

**Files:**
- Modify: `src/pydelphiast/toon.py` (append a new section at the end)
- Modify: `tests/test_toon.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `_type_str(node: Any) -> str` — `TypeRef` → `name<args>`, `StringType` → `string`, `OpenArrayType`/`ArrayType` → `array of T|const`, `SetType` → `set of T`, `PointerType` → `^T`, `ProcType` → `procedure|function`, `MethodReference` → `reference to …`, `None` → `""`, other → its `kind`.
  - `_params_str(params: Any) -> str` — `const A,B:string; var C:Integer`.
  - `_method_row(m: dict) -> dict` — `{"vis", "kind", "name", "params", "returns"}` (in that key order).

- [x] **Step 1: Write the failing tests**

Replace the import block at the top of `tests/test_toon.py` (everything between the docstring and the first `# ----` banner) with:

```python
from __future__ import annotations

import pytest

import pydelphiast as pda
from pydelphiast.toon import (
    _method_row,
    _params_str,
    _type_str,
    encode_toon,
)
```

Append to `tests/test_toon.py`:

```python
# ---------------------------------------------------------------------------
# Task 2 – type / parameter / method formatting
# ---------------------------------------------------------------------------

def _tref(name, *args):
    node = {"kind": "TypeRef", "name": name}
    if args:
        node["typeArgs"] = list(args)
    return node


class TestTypeStr:
    @pytest.mark.parametrize("node, expected", [
        (None, ""),
        (_tref("Integer"), "Integer"),
        (_tref("TList", {"kind": "StringType"}), "TList<string>"),
        (_tref("TDictionary", _tref("string"), _tref("TList", _tref("Integer"))),
         "TDictionary<string,TList<Integer>>"),
        ({"kind": "StringType"}, "string"),
        ({"kind": "OpenArrayType"}, "array of const"),
        ({"kind": "OpenArrayType", "elementType": _tref("Integer")}, "array of Integer"),
        ({"kind": "ArrayType", "elementType": _tref("Byte")}, "array of Byte"),
        ({"kind": "SetType", "baseType": _tref("TDir")}, "set of TDir"),
        ({"kind": "PointerType", "baseType": _tref("Integer")}, "^Integer"),
        ({"kind": "ProcType", "isFunction": True}, "function"),
        ({"kind": "ProcType", "isFunction": False}, "procedure"),
        ({"kind": "MethodReference", "procType": {"kind": "ProcType", "isFunction": False}},
         "reference to procedure"),
        ({"kind": "EnumType"}, "EnumType"),
    ])
    def test_type_str(self, node, expected):
        assert _type_str(node) == expected


class TestParamsAndMethodRow:
    def test_params_from_real_method(self):
        ast = pda.parse_source(
            "unit U; interface type T = class "
            "procedure P(const A, B: string; var C: Integer; out D; "
            "const V: array of const; X: array of Integer); end; "
            "implementation end.",
            "U.pas",
        )
        m = ast["interface"]["declarations"][0]["items"][0]["typeDefinition"]["members"][0]
        assert _params_str(m["params"]) == (
            "const A,B:string; var C:Integer; out D; "
            "const V:array of const; X:array of Integer"
        )

    def test_params_open_array_param_node(self):
        params = [{"kind": "OpenArrayParam", "modifier": "const", "elementType": None}]
        assert _params_str(params) == "const array of const"

    def test_params_empty(self):
        assert _params_str(None) == ""
        assert _params_str([]) == ""

    def test_method_row_function(self):
        m = {"kind": "MethodDecl", "methodKind": "function", "name": "Get",
             "returnType": _tref("Integer"), "visibility": "protected",
             "isClassMember": False}
        assert _method_row(m) == {"vis": "protected", "kind": "function", "name": "Get",
                                  "params": "", "returns": "Integer"}

    def test_method_row_class_member_and_default_visibility(self):
        m = {"kind": "MethodDecl", "methodKind": "function", "name": "Make",
             "returnType": _tref("TFoo"), "isClassMember": True}
        assert _method_row(m) == {"vis": "public", "kind": "class function",
                                  "name": "Make", "params": "", "returns": "TFoo"}
```

- [x] **Step 2: Run test**

Run: `pytest tests/test_toon.py -v`
Expected: FAIL — `ImportError: cannot import name '_method_row'`

- [x] **Step 3: Implement the helpers**

Append to the end of `src/pydelphiast/toon.py`:

```python
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
```

- [x] **Step 4: Run tests**

Run: `pytest tests/test_toon.py -v`
Expected: all tests PASS

- [x] **Step 5: Commit**

```bash
git add src/pydelphiast/toon.py tests/test_toon.py
git commit -m "feat(toon): format Delphi types, params and method rows

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Compact extraction for units and forms (+ form path stamping)

**Files:**
- Modify: `src/pydelphiast/toon.py` (imports, `__all__`, new section at the end)
- Modify: `src/pydelphiast/__init__.py` (`parse_file`, `.pas` branch)
- Modify: `tests/test_toon.py`

**Interfaces:**
- Consumes: `_type_str`, `_method_row` (Task 2).
- Produces:
  - `extract_compact_hierarchy(ast: Any, base_dir: Optional[str] = None) -> dict` — returns `{"base": <abs posix dir>, <rootkey>: ...}`; root keys in this task: `unit`, `form`, `error`; list input → plural keys (`units`, `forms`, `errors`).
  - `_compact_root(node, base) -> Tuple[Optional[str], Optional[dict]]` — Task 4 replaces it with the full version.
  - `_prune`, `_stem`, `_rel`, `_compact_unit`, `_compact_form`, `_PLURAL` (reused by Task 4).

- [x] **Step 1: Write the failing tests**

Replace the import block at the top of `tests/test_toon.py` with:

```python
from __future__ import annotations

import pytest

import pydelphiast as pda
from pydelphiast.toon import (
    _method_row,
    _params_str,
    _type_str,
    encode_toon,
    extract_compact_hierarchy,
)
```

Append to `tests/test_toon.py`:

```python
# ---------------------------------------------------------------------------
# Task 3 – unit / form extraction
# ---------------------------------------------------------------------------

UNIT_SRC = """unit UDemo;
interface
type
  IFoo = interface
    ['{00000000-0000-0000-0000-000000000000}']
    function Get: Integer;
  end;
  TRec = record
    X: Integer;
    procedure Clear;
  end;
  TFwd = class;
  TFoo = class(TForm, IFoo)
  private
    FX: Integer;
    procedure DoIt(const A, B: string; var C: Integer);
  protected
    function Get: Integer; virtual;
  public
    constructor Create(AOwner: TComponent); override;
    class function Make: TFoo;
    property X: Integer read FX;
  end;
  THelp = class helper for TObject
    procedure Hi;
  end;
  TPack = packed record
    A: Byte;
  end;
  TCount = Integer;
procedure Free(P: Pointer);
implementation
type
  TImpl = class
    procedure Z;
  end;
procedure Free(P: Pointer); begin end;
end.
"""

EXPECTED_UNIT_TYPES = [
    {"name": "IFoo", "kind": "interface",
     "methods": [{"vis": "public", "kind": "function", "name": "Get",
                  "params": "", "returns": "Integer"}]},
    {"name": "TRec", "kind": "record",
     "methods": [{"vis": "public", "kind": "procedure", "name": "Clear",
                  "params": "", "returns": ""}]},
    {"name": "TFoo", "kind": "class", "ancestors": ["TForm", "IFoo"],
     "methods": [
         {"vis": "private", "kind": "procedure", "name": "DoIt",
          "params": "const A,B:string; var C:Integer", "returns": ""},
         {"vis": "protected", "kind": "function", "name": "Get",
          "params": "", "returns": "Integer"},
         {"vis": "public", "kind": "constructor", "name": "Create",
          "params": "AOwner:TComponent", "returns": ""},
         {"vis": "public", "kind": "class function", "name": "Make",
          "params": "", "returns": "TFoo"},
     ]},
    {"name": "THelp", "kind": "class helper", "for": "TObject",
     "methods": [{"vis": "published", "kind": "procedure", "name": "Hi",
                  "params": "", "returns": ""}]},
    {"name": "TPack", "kind": "record"},
    {"name": "TImpl", "kind": "class",
     "methods": [{"vis": "published", "kind": "procedure", "name": "Z",
                  "params": "", "returns": ""}]},
]


class TestExtractUnit:
    def test_unit_types_from_full_ast(self, tmp_path):
        ast = pda.parse_source(UNIT_SRC, "UDemo.pas")
        out = extract_compact_hierarchy(ast, base_dir=str(tmp_path))
        assert out["base"] == str(tmp_path).replace("\\", "/")
        assert out["unit"]["name"] == "UDemo"
        assert "path" not in out["unit"]  # parse_source does not stamp filename
        assert out["unit"]["types"] == EXPECTED_UNIT_TYPES

    def test_slim_and_full_ast_give_same_result(self, tmp_path):
        ast = pda.parse_source(UNIT_SRC, "UDemo.pas")
        full = extract_compact_hierarchy(ast, base_dir=str(tmp_path))
        slim = extract_compact_hierarchy(pda.slim_ast(ast), base_dir=str(tmp_path))
        assert full == slim

    def test_unit_file_with_companion_form(self, tmp_path):
        (tmp_path / "UMain.pas").write_text(
            "unit UMain;\ninterface\ntype\n  TMainForm = class(TForm)\n"
            "    procedure FormCreate(Sender: TObject);\n  end;\n"
            "implementation\nprocedure TMainForm.FormCreate(Sender: TObject); begin end;\nend.\n",
            encoding="utf-8",
        )
        (tmp_path / "UMain.dfm").write_text(
            "object MainForm: TMainForm\n  Left = 0\nend\n", encoding="utf-8"
        )
        out = extract_compact_hierarchy(pda.parse_file(str(tmp_path / "UMain.pas")))
        assert out["base"] == str(tmp_path).replace("\\", "/")
        assert out["unit"] == {
            "name": "UMain",
            "path": "UMain.pas",
            "form": {"name": "MainForm", "class": "TMainForm", "path": "UMain.dfm"},
            "types": [{
                "name": "TMainForm", "kind": "class", "ancestors": ["TForm"],
                "methods": [{"vis": "published", "kind": "procedure", "name": "FormCreate",
                             "params": "Sender:TObject", "returns": ""}],
            }],
        }

    def test_form_path_falls_back_to_unit_path(self, tmp_path):
        unit = {"kind": "Unit", "name": "U", "filename": str(tmp_path / "U.pas"),
                "form": {"kind": "DfmObject", "name": "F", "className": "TF"}}
        out = extract_compact_hierarchy(unit)
        assert out["unit"]["form"] == {"name": "F", "class": "TF", "path": "U.dfm"}

    def test_dfm_root(self, tmp_path):
        dfm = tmp_path / "F.dfm"
        dfm.write_text("object F: TF\nend\n", encoding="utf-8")
        out = extract_compact_hierarchy(pda.parse_file(str(dfm)))
        assert out["form"] == {"name": "F", "class": "TF", "path": "F.dfm"}

    def test_parse_error_root(self, tmp_path):
        node = {"kind": "ParseError", "filename": str(tmp_path / "X.pas"), "message": "boom"}
        out = extract_compact_hierarchy(node)
        assert out["error"] == {"path": "X.pas", "message": "boom"}

    def test_parse_file_stamps_form_filename(self, tmp_path):
        (tmp_path / "U.pas").write_text("unit U; interface implementation end.",
                                        encoding="utf-8")
        (tmp_path / "U.dfm").write_text("object F: TF\nend\n", encoding="utf-8")
        ast = pda.parse_file(str(tmp_path / "U.pas"))
        assert ast["form"]["filename"] == str((tmp_path / "U.dfm").resolve())
```

- [x] **Step 2: Run test**

Run: `pytest tests/test_toon.py -v`
Expected: FAIL — `ImportError: cannot import name 'extract_compact_hierarchy'`

- [x] **Step 3: Update module imports and `__all__`**

In `src/pydelphiast/toon.py` replace

```python
import math
import re
from decimal import Decimal
from typing import Any, List, Optional

__all__ = ["encode_toon"]
```

with

```python
import math
import os
import re
from decimal import Decimal
from typing import Any, Iterator, List, Optional, Tuple

__all__ = ["encode_toon", "extract_compact_hierarchy"]
```

- [x] **Step 4: Implement unit/form extraction**

Append to the end of `src/pydelphiast/toon.py`:

```python
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
```

- [x] **Step 5: Stamp the companion form path in `parse_file()`**

In `src/pydelphiast/__init__.py`, `parse_file()`, `.pas` branch, replace

```python
                with open(dfm_path, encoding=encoding, errors="replace") as fh:
                    ast["form"] = parse_dfm(fh.read(), dfm_path)
```

with

```python
                with open(dfm_path, encoding=encoding, errors="replace") as fh:
                    ast["form"] = parse_dfm(fh.read(), dfm_path)
                ast["form"]["filename"] = os.path.abspath(dfm_path)
```

- [x] **Step 6: Run tests**

Run: `pytest tests/test_toon.py -v`
Expected: all tests PASS (including `test_parse_file_stamps_form_filename`)

- [x] **Step 7: Run tests**

Run: `pytest -q`
Expected: full suite PASS

- [x] **Step 8: Commit**

```bash
git add src/pydelphiast/toon.py tests/test_toon.py src/pydelphiast/__init__.py
git commit -m "feat(toon): extract compact hierarchy for units and forms

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Compact extraction for projects and groups (+ `.dpr` path stamping)

**Files:**
- Modify: `src/pydelphiast/toon.py`
- Modify: `src/pydelphiast/project.py` (`DelphiProject._parse_dpr`)
- Modify: `tests/test_toon.py`

**Interfaces:**
- Consumes: `_prune`, `_stem`, `_rel`, `_compact_unit`, `_compact_form`, `_PLURAL` (Task 3).
- Produces: `extract_compact_hierarchy` now also handles root kinds `GroupProject` (key `group`), `DprojProject`/`Program`/`Library`/`Package` (key `project`); `_compact_project(node, base) -> dict`, `_compact_group(node, base) -> dict`.

- [x] **Step 1: Write the failing tests**

Replace the import block at the top of `tests/test_toon.py` with:

```python
from __future__ import annotations

from pathlib import Path

import pytest

import pydelphiast as pda
from pydelphiast.toon import (
    _method_row,
    _params_str,
    _type_str,
    encode_toon,
    extract_compact_hierarchy,
)
```

Append to `tests/test_toon.py`:

```python
# ---------------------------------------------------------------------------
# Task 4 – project / group extraction
# ---------------------------------------------------------------------------

_NS = "http://schemas.microsoft.com/developer/msbuild/2003"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _dproj(main_source: str) -> str:
    return (
        f'<Project xmlns="{_NS}">\n'
        "  <PropertyGroup>\n"
        f"    <MainSource>{main_source}</MainSource>\n"
        "    <Config Condition=\"'$(Config)'==''\">Debug</Config>\n"
        "    <Platform Condition=\"'$(Platform)'==''\">Win32</Platform>\n"
        "  </PropertyGroup>\n"
        "</Project>\n"
    )


@pytest.fixture()
def group_dir(tmp_path: Path) -> Path:
    """Build: Group.groupproj -> App/App.dproj, Tool/Tool.dproj, Gone/Gone.dproj (missing)."""
    _write(tmp_path / "Group.groupproj",
           f'<Project xmlns="{_NS}">\n  <ItemGroup>\n'
           '    <Projects Include="App\\App.dproj"/>\n'
           '    <Projects Include="Tool\\Tool.dproj"/>\n'
           '    <Projects Include="Gone\\Gone.dproj"/>\n'
           "  </ItemGroup>\n</Project>\n")
    _write(tmp_path / "App" / "App.dproj", _dproj("App.dpr"))
    _write(tmp_path / "App" / "App.dpr",
           "program App;\nuses\n  UMain in 'UMain.pas',\n"
           "  UShared in '../Shared/UShared.pas';\nbegin\nend.\n")
    _write(tmp_path / "App" / "UMain.pas",
           "unit UMain;\ninterface\ntype\n  TMainForm = class(TForm)\n"
           "  public\n    function Ok(const S: string): Boolean;\n  end;\n"
           "implementation\nfunction TMainForm.Ok(const S: string): Boolean; begin end;\nend.\n")
    _write(tmp_path / "App" / "UMain.dfm", "object MainForm: TMainForm\nend\n")
    _write(tmp_path / "Shared" / "UShared.pas",
           "unit UShared;\ninterface\nimplementation\nend.\n")
    _write(tmp_path / "Tool" / "Tool.dproj", _dproj("Tool.dpr"))
    _write(tmp_path / "Tool" / "Tool.dpr",
           "program Tool;\nuses\n  UShared in '../Shared/UShared.pas';\nbegin\nend.\n")
    return tmp_path


EXPECTED_GROUP = {
    "name": "Group",
    "path": "Group.groupproj",
    "projects": [
        {
            "name": "App",
            "path": "App/App.dproj",
            "source": "App/App.dpr",
            "platform": "Win32",
            "config": "Debug",
            "units": [
                {
                    "name": "UMain",
                    "path": "App/UMain.pas",
                    "form": {"name": "MainForm", "class": "TMainForm",
                             "path": "App/UMain.dfm"},
                    "types": [{
                        "name": "TMainForm", "kind": "class", "ancestors": ["TForm"],
                        "methods": [{"vis": "public", "kind": "function", "name": "Ok",
                                     "params": "const S:string", "returns": "Boolean"}],
                    }],
                },
                {"name": "UShared", "path": "Shared/UShared.pas"},
            ],
        },
        {
            "name": "Tool",
            "path": "Tool/Tool.dproj",
            "source": "Tool/Tool.dpr",
            "platform": "Win32",
            "config": "Debug",
            "units": [{"name": "UShared", "path": "Shared/UShared.pas", "ref": True}],
        },
        {"name": "Gone", "path": "Gone/Gone.dproj", "missing": True},
    ],
}


class TestExtractProject:
    def test_dpr_root_has_filename(self, group_dir):
        ast = pda.parse_project(str(group_dir / "App" / "App.dpr"))
        assert ast["filename"] == str(group_dir / "App" / "App.dpr")

    def test_group_hierarchy(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Group.groupproj"))
        out = extract_compact_hierarchy(ast)
        assert out["base"] == str(group_dir).replace("\\", "/")
        assert out["group"] == EXPECTED_GROUP

    def test_group_hierarchy_from_slim_ast(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Group.groupproj"))
        assert extract_compact_hierarchy(pda.slim_ast(ast))["group"] == EXPECTED_GROUP

    def test_dpr_root(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Tool" / "Tool.dpr"))
        out = extract_compact_hierarchy(ast)
        assert out["base"] == str(group_dir / "Tool").replace("\\", "/")
        assert out["project"] == {
            "name": "Tool",
            "path": "Tool.dpr",
            "units": [{"name": "UShared", "path": "../Shared/UShared.pas"}],
        }

    def test_dproj_root(self, group_dir):
        ast = pda.parse_project(str(group_dir / "App" / "App.dproj"))
        out = extract_compact_hierarchy(ast)
        assert out["project"]["path"] == "App.dproj"
        assert out["project"]["source"] == "App.dpr"
        assert [u["name"] for u in out["project"]["units"]] == ["UMain", "UShared"]

    def test_list_input_groups_by_kind(self, group_dir):
        asts = [
            pda.parse_file(str(group_dir / "App" / "UMain.pas")),
            pda.parse_file(str(group_dir / "Shared" / "UShared.pas")),
        ]
        out = extract_compact_hierarchy(asts)
        assert out["base"] == str(group_dir).replace("\\", "/")
        assert [u["path"] for u in out["units"]] == ["App/UMain.pas", "Shared/UShared.pas"]
        assert set(out) == {"base", "units"}
```

- [x] **Step 2: Run tests**

Run: `pytest tests/test_toon.py -v -k Project`
Expected: 5 FAIL (`KeyError: 'filename'` / `'group'` / `'project'`); `test_list_input_groups_by_kind` already passes (units only)

- [x] **Step 3: Stamp `filename` on the `.dpr` root**

In `src/pydelphiast/project.py`, `_parse_dpr`, replace

```python
        ast = self._safe_parse_pas(src, path)
        # Follow uses references to .pas files in the same / nearby directories
```

with

```python
        ast = self._safe_parse_pas(src, path)
        ast["filename"] = path
        # Follow uses references to .pas files in the same / nearby directories
```

- [x] **Step 4: Add project/group extraction**

In `src/pydelphiast/toon.py`, insert right after the `_PLURAL = {...}` constant:

```python
_PROJECT_KINDS = ("DprojProject", "Program", "Library", "Package")
```

Insert right after `def _rel(...)`:

```python
def _resolve(anchor: str, rel: str) -> str:
    if not rel:
        return ""
    return os.path.normpath(os.path.join(os.path.dirname(anchor), rel))
```

Insert right after `def _compact_unit(...)` (before `_compact_root`):

```python
def _compact_project(node: dict, base: str) -> dict:
    kind = node.get("kind")
    units: list = []
    if kind == "DprojProject":
        path = node.get("filename", "")
        main = node.get("mainSourceAst") or {}
        main_failed = main.get("kind") == "ParseError"
        source = main.get("filename") or _resolve(path, node.get("mainSource", ""))
        out: dict = {
            "name": (None if main_failed else main.get("name")) or _stem(path),
            "path": _rel(path, base),
            "source": _rel(source, base),
            "platform": node.get("platform"),
            "config": node.get("config"),
        }
        if main_failed:
            out["error"] = main.get("message", "")
        units = main.get("resolvedUnits") or []
    elif kind in ("Program", "Library", "Package"):
        path = node.get("filename", "")
        out = {"name": node.get("name") or _stem(path), "path": _rel(path, base)}
        units = node.get("resolvedUnits") or []
    elif kind == "ParseError":
        path = node.get("filename", "")
        out = {"name": _stem(path), "path": _rel(path, base),
               "error": node.get("message", "")}
        units = node.get("resolvedUnits") or []
    else:  # ProjectRef (missing) / UnknownProjectRef
        path = node.get("path", "")
        out = {"name": _stem(path), "path": _rel(path, base)}
        if node.get("missing"):
            out["missing"] = True
    out["units"] = [_compact_unit(u, base) for u in units if isinstance(u, dict)]
    return _prune(out)


def _compact_group(node: dict, base: str) -> dict:
    path = node.get("filename", "")
    projects: List[dict] = []
    for p in node.get("resolvedProjects") or []:
        if not isinstance(p, dict):
            continue
        if p.get("kind") == "ProjectRef":
            p = dict(p, path=_resolve(path, p.get("path", "")))
        projects.append(_compact_project(p, base))
    return _prune({"name": _stem(path), "path": _rel(path, base), "projects": projects})
```

Replace the whole `_compact_root` function with:

```python
def _compact_root(node: dict, base: str) -> Tuple[Optional[str], Optional[dict]]:
    kind = node.get("kind")
    if kind == "GroupProject":
        return "group", _compact_group(node, base)
    if kind in _PROJECT_KINDS:
        return "project", _compact_project(node, base)
    if kind == "Unit":
        return "unit", _compact_unit(node, base)
    if kind == "DfmObject":
        return "form", _compact_form(node, base)
    if kind == "ParseError":
        return "error", _prune({"path": _rel(node.get("filename", ""), base),
                                "message": node.get("message", "")})
    return None, None
```

- [x] **Step 5: Run tests**

Run: `pytest tests/test_toon.py -v`
Expected: all tests PASS

- [x] **Step 6: Run tests**

Run: `pytest -q`
Expected: full suite PASS

- [x] **Step 7: Commit**

```bash
git add src/pydelphiast/toon.py tests/test_toon.py src/pydelphiast/project.py
git commit -m "feat(toon): extract compact hierarchy for projects and groups

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `to_toon()` and public API

**Files:**
- Modify: `src/pydelphiast/toon.py`
- Modify: `src/pydelphiast/__init__.py`
- Modify: `tests/test_toon.py`

**Interfaces:**
- Consumes: `encode_toon` (Task 1), `extract_compact_hierarchy` (Tasks 3-4).
- Produces: `to_toon(ast: Any, base_dir: Optional[str] = None) -> str`; `pydelphiast.to_toon`, `pydelphiast.extract_compact_hierarchy`, `pydelphiast.encode_toon` (also in `pydelphiast.__all__`).

- [x] **Step 1: Write the failing tests**

Replace the import block at the top of `tests/test_toon.py` with:

```python
from __future__ import annotations

from pathlib import Path

import pytest

import pydelphiast as pda
from pydelphiast.toon import (
    _method_row,
    _params_str,
    _type_str,
    encode_toon,
    extract_compact_hierarchy,
    to_toon,
)
```

Append to `tests/test_toon.py`:

```python
# ---------------------------------------------------------------------------
# Task 5 – to_toon end to end + public API
# ---------------------------------------------------------------------------

class TestToToon:
    def test_public_api_exports(self):
        assert pda.to_toon is to_toon
        assert pda.extract_compact_hierarchy is extract_compact_hierarchy
        assert pda.encode_toon is encode_toon
        for name in ("to_toon", "extract_compact_hierarchy", "encode_toon"):
            assert name in pda.__all__

    def test_group_toon_text(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Group.groupproj"))
        base = str(group_dir).replace("\\", "/")
        assert pda.to_toon(ast) == (
            f'base: "{base}"\n'
            "group:\n"
            "  name: Group\n"
            "  path: Group.groupproj\n"
            "  projects[3]:\n"
            "    - name: App\n"
            "      path: App/App.dproj\n"
            "      source: App/App.dpr\n"
            "      platform: Win32\n"
            "      config: Debug\n"
            "      units[2]:\n"
            "        - name: UMain\n"
            "          path: App/UMain.pas\n"
            "          form:\n"
            "            name: MainForm\n"
            "            class: TMainForm\n"
            "            path: App/UMain.dfm\n"
            "          types[1]:\n"
            "            - name: TMainForm\n"
            "              kind: class\n"
            "              ancestors[1]: TForm\n"
            "              methods[1]{vis,kind,name,params,returns}:\n"
            '                public,function,Ok,"const S:string",Boolean\n'
            "        - name: UShared\n"
            "          path: Shared/UShared.pas\n"
            "    - name: Tool\n"
            "      path: Tool/Tool.dproj\n"
            "      source: Tool/Tool.dpr\n"
            "      platform: Win32\n"
            "      config: Debug\n"
            "      units[1]{name,path,ref}:\n"
            "        UShared,Shared/UShared.pas,true\n"
            "    - name: Gone\n"
            "      path: Gone/Gone.dproj\n"
            "      missing: true"
        )

    def test_toon_is_smaller_than_json(self, group_dir):
        ast = pda.parse_project(str(group_dir / "Group.groupproj"))
        assert len(pda.to_toon(ast)) * 5 < len(pda.to_json(ast))
```

- [x] **Step 2: Run test**

Run: `pytest tests/test_toon.py -v -k ToToon`
Expected: FAIL — `ImportError: cannot import name 'to_toon'`

- [x] **Step 3: Add `to_toon`**

In `src/pydelphiast/toon.py` change `__all__` to

```python
__all__ = ["encode_toon", "extract_compact_hierarchy", "to_toon"]
```

and append to the end of the file:

```python
def to_toon(ast: Any, base_dir: Optional[str] = None) -> str:
    """Return the TOON text of the compact hierarchy of *ast*."""
    return encode_toon(extract_compact_hierarchy(ast, base_dir))
```

- [x] **Step 4: Re-export from the package**

In `src/pydelphiast/__init__.py`, after `from .project import DelphiProject` add

```python
from .toon import encode_toon, extract_compact_hierarchy, to_toon
```

and in `__all__` replace

```python
    # Outline view
    "to_outline",
]
```

with

```python
    # Outline view
    "to_outline",
    # TOON export
    "to_toon",
    "extract_compact_hierarchy",
    "encode_toon",
]
```

Also add to the module docstring "Quick start" block:

```python
    # Compact hierarchy as TOON (token-efficient, for LLM contexts)
    text = pda.to_toon(pda.parse_project("MyApp.groupproj"))
```

- [x] **Step 5: Run tests**

Run: `pytest tests/test_toon.py -v`
Expected: all tests PASS

- [x] **Step 6: Commit**

```bash
git add src/pydelphiast/toon.py tests/test_toon.py src/pydelphiast/__init__.py
git commit -m "feat(toon): add to_toon and export TOON API

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: CLI `--toon` flag and documentation

**Files:**
- Modify: `src/pydelphiast/__main__.py` (`_build_parser`, `main`, module docstring)
- Modify: `CLAUDE.md`, `README.md`
- Modify: `tests/test_toon.py`

**Interfaces:**
- Consumes: `pydelphiast.to_toon` (Task 5).
- Produces: `python -m pydelphiast <file> --toon` → writes `<dir of first file>/<stem>.toon` (or `-o` target); stderr `TOON written to <path>`; `--slim`/`--indent` are ignored with `--toon`.

- [ ] **Step 1: Write the failing tests**

Replace the import block at the top of `tests/test_toon.py` with:

```python
from __future__ import annotations

from pathlib import Path

import pytest

import pydelphiast as pda
from pydelphiast.__main__ import main as cli_main
from pydelphiast.toon import (
    _method_row,
    _params_str,
    _type_str,
    encode_toon,
    extract_compact_hierarchy,
    to_toon,
)
```

Append to `tests/test_toon.py`:

```python
# ---------------------------------------------------------------------------
# Task 6 – CLI
# ---------------------------------------------------------------------------

class TestCliToon:
    def test_toon_flag_writes_toon_next_to_input(self, group_dir):
        root = group_dir / "Group.groupproj"
        assert cli_main([str(root), "--toon"]) == 0
        out = group_dir / "Group.toon"
        assert out.is_file()
        ast = pda.parse_project(str(root))
        assert out.read_text(encoding="utf-8") == pda.to_toon(ast)
        assert not (group_dir / "Group.json").exists()

    def test_toon_flag_respects_output(self, group_dir, tmp_path):
        target = tmp_path / "custom.toon"
        assert cli_main([str(group_dir / "App" / "UMain.pas"), "--toon",
                         "-o", str(target)]) == 0
        assert target.read_text(encoding="utf-8").startswith("base: ")

    def test_without_toon_still_writes_json(self, group_dir):
        assert cli_main([str(group_dir / "App" / "UMain.pas")]) == 0
        assert (group_dir / "App" / "UMain.json").is_file()
        assert not (group_dir / "App" / "UMain.toon").exists()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_toon.py -v -k Cli`
Expected: 2 FAIL (`SystemExit: 2`, argparse: unrecognized arguments: --toon); `test_without_toon_still_writes_json` already passes (regression guard)

- [ ] **Step 3: Add the flag**

In `src/pydelphiast/__main__.py`, `_build_parser()`, insert before the `--version` argument:

```python
    p.add_argument(
        "--toon",
        action="store_true",
        help="Output the compact hierarchy (group > projects > units > forms/types "
             "> methods) in TOON format to <stem>.toon",
    )
```

- [ ] **Step 4: Branch the output in `main()`**

Replace

```python
    output = results[0] if len(results) == 1 else results
    if args.slim:
        output = pda.slim_ast(output)
    text = json.dumps(output, indent=indent, ensure_ascii=False, default=str)

    if args.output:
        out_path = Path(args.output)
    else:
        # Default: write <first-input-stem>.json next to the input file
        stem = Path(args.files[0]).stem
        out_path = Path(args.files[0]).parent / f"{stem}.json"

    out_path.write_text(text, encoding="utf-8")
    print(f"AST written to {out_path}", file=sys.stderr)
```

with

```python
    output = results[0] if len(results) == 1 else results
    if args.toon:
        text = pda.to_toon(output)
        suffix, label = ".toon", "TOON"
    else:
        if args.slim:
            output = pda.slim_ast(output)
        text = json.dumps(output, indent=indent, ensure_ascii=False, default=str)
        suffix, label = ".json", "AST"

    if args.output:
        out_path = Path(args.output)
    else:
        # Default: write <first-input-stem><suffix> next to the input file
        stem = Path(args.files[0]).stem
        out_path = Path(args.files[0]).parent / f"{stem}{suffix}"

    out_path.write_text(text, encoding="utf-8")
    print(f"{label} written to {out_path}", file=sys.stderr)
```

Add to the module docstring usage examples:

```python
    # Compact hierarchy in TOON (writes MyApp.toon)
    python -m pydelphiast MyApp.groupproj --toon
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_toon.py -v`
Expected: all tests PASS

- [ ] **Step 6: Document**

In `CLAUDE.md`, section `## Commands`, after the "Save AST to a specific file" example add:

```bash
# Compact hierarchy in TOON (group > projects > units > forms/types > methods)
python -m pydelphiast MyApp.groupproj --toon    # → MyApp.toon
```

and in `## Architecture`, after the `project.py` line add:

```
  toon.py             – TOON export: encode_toon() (generic encoder),
                        extract_compact_hierarchy() (group > projects > units >
                        form/types > methods, paths relative to `base`), to_toon()
```

In `README.md`, add a short "TOON export" section with the CLI command above and:

```python
import pydelphiast as pda
print(pda.to_toon(pda.parse_project("MyApp.groupproj")))
```

- [ ] **Step 7: Final verification**

Run: `pytest -q`
Expected: full suite PASS (existing tests + `tests/test_toon.py`).

Run: `python -m pydelphiast tests/fixtures/simple.pas --toon -o %TEMP%/simple.toon` (PowerShell: `$env:TEMP/simple.toon`)
Expected: stderr `TOON written to …`; file starts with `base: "` and contains `unit:` / `types[`.

- [ ] **Step 8: Commit**

```bash
git add src/pydelphiast/__main__.py tests/test_toon.py CLAUDE.md README.md
git commit -m "feat(cli): add --toon flag for compact TOON export

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
