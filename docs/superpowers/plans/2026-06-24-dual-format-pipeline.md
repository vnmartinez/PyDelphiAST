# Dual-Format Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `to_outline()` for compact LLM-friendly output, fix DPR parser to handle embedded compiler directives in uses clauses, flatten slim_ast wrappers, and update `/documentar` to use `.docs`/`.projects` folder layout.

**Architecture:** Four independent changes — one parser fix, one slim_ast improvement, one new public function, one skill update. No shared state between tasks; each is testable in isolation.

**Tech Stack:** Python 3.x, pytest, pydelphiast (src/pydelphiast/)

---

### Task 1: Fix DPR parser — compiler directives inside uses items

**Root cause:** `_parse_uses_item` does not skip `COMPILER_DIR` tokens after the optional path string. When a DPR has `UImpPedidoCompra in 'UImpPedidoCompra.pas' {$R *.res},` the directive sits between the path and the comma, causing `_parse_uses_clause` to fail with "Expected SEMI, got COMPILER_DIR".

**Files:**
- Modify: `src/pydelphiast/parsers/pas_parser.py:232-239`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

Add this test class to `tests/test_parser.py`:

```python
class TestDprCompilerDirectiveInUses:
    def test_compiler_dir_after_path_string(self):
        """Reproduces the {$R *.res} embedded inside a uses item."""
        src = (
            "program Foo;\n"
            "uses\n"
            "  UnitA in 'UnitA.pas' {$R *.res},\n"
            "  UnitB in 'UnitB.pas';\n"
            "begin end.\n"
        )
        ast = parse_pas(src)
        assert ast["kind"] == "Program"
        uses = ast["uses"]
        assert uses["kind"] == "UsesClause"
        names = [i["name"] for i in uses["items"]]
        assert names == ["UnitA", "UnitB"]

    def test_compiler_dir_before_semi(self):
        """Handles {$R *.res} after the last uses item before the semicolon."""
        src = (
            "program Foo;\n"
            "uses\n"
            "  UnitA in 'UnitA.pas'\n"
            "  {$R *.res};\n"
            "begin end.\n"
        )
        ast = parse_pas(src)
        assert ast["kind"] == "Program"
        assert ast["uses"]["items"][0]["name"] == "UnitA"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_parser.py::TestDprCompilerDirectiveInUses -v
```

Expected: both tests FAIL with `ParseError` or assertion error.

- [ ] **Step 3: Apply the fix**

In `src/pydelphiast/parsers/pas_parser.py`, modify `_parse_uses_item` to skip compiler directives after the optional path:

```python
def _parse_uses_item(self) -> dict:
    start = self.current
    name = self.parse_qualified_name()
    path = None
    if self.check(TT.IN):
        self.advance()
        path = self.expect(TT.STRING).value
    self.skip_compiler_dirs()
    return self._node("UsesItem", start, name=name, path=path)
```

Also add `self.skip_compiler_dirs()` before `self.expect(TT.SEMI)` in `_parse_uses_clause` to handle the case where `{$R *.res}` appears after the last item:

```python
def _parse_uses_clause(self) -> dict:
    start = self.current
    self.expect(TT.USES)
    items: List[dict] = []
    self.skip_compiler_dirs()
    items.append(self._parse_uses_item())
    while self.match(TT.COMMA):
        self.skip_compiler_dirs()
        if self.check(TT.SEMI):  # trailing comma before semicolon
            break
        items.append(self._parse_uses_item())
    self.skip_compiler_dirs()
    self.expect(TT.SEMI)
    return self._node("UsesClause", start, items=items)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_parser.py::TestDprCompilerDirectiveInUses -v
```

Expected: both PASS.

- [ ] **Step 5: Run full test suite**

```
pytest -v
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/pydelphiast/parsers/pas_parser.py tests/test_parser.py
git commit -m "fix: skip compiler directives embedded inside uses items"
```

---

### Task 2: Flatten TypeSection/ConstSection wrappers in slim_ast

**Files:**
- Modify: `src/pydelphiast/__init__.py:177-211`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_parser.py`:

```python
class TestSlimAstFlatten:
    def test_type_section_flattened(self):
        src = "unit T; interface type TFoo = class end; implementation end."
        slim = pda.slim_ast(pda.parse_source(src, "T.pas"))
        decls = slim["interface"]["declarations"]
        # Should be TypeDecl directly, not wrapped in TypeSection
        kinds = [d["kind"] for d in decls]
        assert "TypeSection" not in kinds
        assert "TypeDecl" in kinds

    def test_const_section_flattened(self):
        src = "unit T; interface const X = 1; implementation end."
        slim = pda.slim_ast(pda.parse_source(src, "T.pas"))
        decls = slim["interface"]["declarations"]
        kinds = [d["kind"] for d in decls]
        assert "ConstSection" not in kinds
        assert "ConstDecl" in kinds

    def test_var_section_flattened(self):
        src = "unit T; interface var X: Integer; implementation end."
        slim = pda.slim_ast(pda.parse_source(src, "T.pas"))
        decls = slim["interface"]["declarations"]
        kinds = [d["kind"] for d in decls]
        assert "VarSection" not in kinds
        assert "VarDecl" in kinds
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_parser.py::TestSlimAstFlatten -v
```

Expected: all three FAIL (TypeSection/ConstSection/VarSection are currently present).

- [ ] **Step 3: Implement flattening in slim_ast**

In `src/pydelphiast/__init__.py`, update `slim_ast` to flatten wrapper sections. Add a set of wrapper kinds and a helper that flattens after recursion:

```python
# Wrapper section kinds whose items should be inlined into parent declarations
_FLATTEN_KINDS = {"TypeSection", "ConstSection", "VarSection"}


def slim_ast(node: object) -> object:
    """Return a structural-only view of an AST node."""
    if isinstance(node, list):
        result = [slim_ast(item) for item in node]
        # Flatten wrapper sections inline
        flattened = []
        for item in result:
            if isinstance(item, dict) and item.get("kind") in _FLATTEN_KINDS:
                flattened.extend(item.get("items", []))
            else:
                if item not in (None, [], {}):
                    flattened.append(item)
        return flattened

    if not isinstance(node, dict):
        return node

    kind = node.get("kind", "")

    out: dict = {}
    for key, val in node.items():
        if key in ("startPos", "endPos"):
            continue
        if key in _STRIP_KEYS:
            continue
        if key == "items" and kind in ("UsesClause",):
            out[key] = [
                {k: v for k, v in slim_ast(i).items() if k in ("kind", "name", "path")}
                for i in (val or [])
                if isinstance(i, dict)
            ]
            continue
        out[key] = slim_ast(val)

    out = {k: v for k, v in out.items() if v not in (None, [], {})}
    return out
```

Also remove `"TypeSection"`, `"ConstSection"`, `"VarSection"` from `_STRUCTURAL_KINDS` since they are now flattened away (their children are kept):

```python
_STRUCTURAL_KINDS = {
    "Unit", "Program", "Library", "Package",
    "InterfaceSection", "ImplementationSection",
    "UsesClause", "UsesItem",
    "TypeDecl",
    "ClassType", "RecordType", "InterfaceType", "DispinterfaceType", "ObjectType",
    "EnumType", "SubrangeType", "SetType", "ArrayType", "PointerType",
    "ProcType", "FileType", "PackedType",
    "MethodDecl", "FieldDecl", "PropertyDecl", "VisibilitySection",
    "RoutineDecl",
    "ConstDecl", "TypedConstDecl",
    "VarDecl",
    "ExportsSection", "ExportsItem",
    "DfmObject", "DfmProperty",
    "GroupProject", "ProjectRef", "DprojProject",
    "ParseError",
}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_parser.py::TestSlimAstFlatten -v
```

Expected: all three PASS.

- [ ] **Step 5: Run full test suite**

```
pytest -v
```

Expected: all passing. If any existing test checks for `TypeSection`/`ConstSection` kinds in slim output, update those assertions to match the flattened form.

- [ ] **Step 6: Commit**

```bash
git add src/pydelphiast/__init__.py tests/test_parser.py
git commit -m "feat: flatten TypeSection/ConstSection/VarSection wrappers in slim_ast"
```

---

### Task 3: Add `to_outline()` public function

**Files:**
- Modify: `src/pydelphiast/__init__.py`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_parser.py`:

```python
class TestToOutline:
    def test_basic_unit(self):
        src = "unit uOperacoesMat; interface uses Math; type TRound = class public class function Arredondar(pValor, pCasas: Double): Double; end; implementation end."
        slim = pda.slim_ast(pda.parse_source(src, "uOperacoesMat.pas"))
        outline = pda.to_outline(slim)
        assert "[uOperacoesMat]" in outline
        assert "TRound" in outline
        assert "Arredondar" in outline

    def test_uses_filters_system_units(self):
        src = "unit uFoo; interface uses System.SysUtils, Vcl.Forms, uMyUnit; implementation end."
        slim = pda.slim_ast(pda.parse_source(src, "uFoo.pas"))
        outline = pda.to_outline(slim)
        assert "System.SysUtils" not in outline
        assert "Vcl.Forms" not in outline
        assert "uMyUnit" in outline

    def test_returns_string(self):
        src = "unit Foo; interface implementation end."
        slim = pda.slim_ast(pda.parse_source(src, "Foo.pas"))
        result = pda.to_outline(slim)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_outline_smaller_than_json(self):
        src = """unit uOperacoesMat; interface uses Math;
        type
          TRound = class
          public
            class function Arredondar(pValor, pCasas: Double): Double;
          end;
          TMultiplic = class
          public
            class function MultiplicarQtde(pQtde, pValor: Double): Double;
          end;
        implementation end."""
        slim = pda.slim_ast(pda.parse_source(src, "uOperacoesMat.pas"))
        outline = pda.to_outline(slim)
        json_size = len(json.dumps(slim))
        assert len(outline) < json_size
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_parser.py::TestToOutline -v
```

Expected: all FAIL with `AttributeError: module 'pydelphiast' has no attribute 'to_outline'`.

- [ ] **Step 3: Implement `to_outline()`**

Add to `src/pydelphiast/__init__.py` after `slim_ast`:

```python
# ---------------------------------------------------------------------------
# Outline view — compact text for LLM consumption
# ---------------------------------------------------------------------------

# System/framework unit prefixes to suppress in uses output
_SYSTEM_PREFIXES = (
    "System.", "Vcl.", "Winapi.", "FMX.", "Web.", "Xml.",
    "Data.", "FireDAC.", "Soap.", "Datasnap.", "REST.",
    "IdHTTP", "SysUtils", "Classes", "Math", "StrUtils",
    "DateUtils", "IOUtils", "RegularExpressions",
)

# Units whose methods are too low-level to list individually
_BULK_LABELS = {"sql", "helper"}

# Max methods listed per class before truncating
_MAX_METHODS = 8


def _outline_label(unit_name: str, members: list) -> str:
    """Heuristic label for a unit based on name and class members."""
    n = unit_name.lower()
    ancestor_names = " ".join(
        m.get("name", "") for m in members if isinstance(m, dict)
    ).lower()
    if n.startswith("udm") or "tdatamodule" in ancestor_names:
        return "datamodule"
    if n.startswith("ufrm") or "tform" in ancestor_names:
        return "form"
    if n.startswith("upsq") or n.startswith("usql"):
        return "sql"
    if n.startswith("uhel"):
        return "helper"
    if n.startswith("upcta") or "tbasetabela" in ancestor_names:
        return "table"
    if n.startswith("ucls") or "facade" in n:
        return "facade"
    return "unit"


def _outline_unit(node: dict) -> str:
    """Render one Unit node as an outline line-group."""
    name = node.get("name", "?")
    iface = node.get("interface", {})
    uses_clause = iface.get("uses", {})
    decls = iface.get("declarations", [])

    # Collect local uses
    local_uses = [
        i["name"] for i in uses_clause.get("items", [])
        if isinstance(i, dict)
        and not any(i.get("name", "").startswith(p) for p in _SYSTEM_PREFIXES)
    ]

    # Collect class/record type members for label detection
    all_ancestors: list = []
    for d in decls:
        if isinstance(d, dict) and d.get("kind") == "TypeDecl":
            td = d.get("typeDefinition", {})
            all_ancestors.extend(td.get("ancestors", []))

    label = _outline_label(name, all_ancestors)

    # Header line
    parts = [f"[{name}] {label}"]

    # Primary class (first class/record TypeDecl)
    primary_class = None
    for d in decls:
        if isinstance(d, dict) and d.get("kind") == "TypeDecl":
            kind = d.get("typeDefinition", {}).get("kind", "")
            if kind in ("ClassType", "RecordType", "InterfaceType"):
                primary_class = d
                break

    if primary_class:
        td = primary_class["typeDefinition"]
        ancestors = [a.get("name") for a in td.get("ancestors", []) if a.get("name")]
        class_name = primary_class["name"]
        ancestor_str = f"({', '.join(ancestors)})" if ancestors else ""
        parts[0] += f" > {class_name}{ancestor_str}"

    if local_uses:
        parts[0] += f" uses: {', '.join(local_uses)}"

    lines = [parts[0]]

    if label in _BULK_LABELS:
        # Count public routines only
        n_routines = sum(
            1 for d in decls
            if isinstance(d, dict) and d.get("kind") == "RoutineDecl"
        )
        if n_routines:
            lines.append(f"  — {n_routines} routines")
        return "\n".join(lines)

    # List members of primary class
    if primary_class:
        members = primary_class["typeDefinition"].get("members", [])
        _render_members(members, lines, indent="  ")

    # Additional classes
    extra_classes = [
        d for d in decls
        if isinstance(d, dict) and d.get("kind") == "TypeDecl"
        and d is not primary_class
        and d.get("typeDefinition", {}).get("kind") in ("ClassType", "RecordType", "InterfaceType")
    ]
    for ec in extra_classes:
        td = ec["typeDefinition"]
        members = td.get("members", [])
        simple_methods = _simple_method_names(members)
        if simple_methods:
            lines.append(f"  CLASS {ec['name']}: {' '.join(simple_methods[:6])}")

    return "\n".join(lines)


def _simple_method_names(members: list) -> list:
    """Return +/-Name strings for methods, grouped."""
    out = []
    for m in members:
        if not isinstance(m, dict):
            continue
        if m.get("kind") != "MethodDecl":
            continue
        vis = m.get("visibility", "public")
        prefix = "+" if vis in ("public", "published") else "-"
        if m.get("isClassMember"):
            prefix = "+class "
        name = m.get("name", "?")
        params = m.get("params", [])
        ret = m.get("returnType", {})
        if params or ret:
            param_str = _fmt_params(params)
            ret_str = f":{ret.get('name', '')}" if ret and ret.get("name") else ""
            out.append(f"{prefix}{name}({param_str}){ret_str}")
        else:
            out.append(f"{prefix}{name}")
    return out


def _render_members(members: list, lines: list, indent: str = "  ") -> None:
    """Append member lines to lines list."""
    method_lines = _simple_method_names(members)
    if not method_lines:
        return

    # Group no-arg/no-ret methods on one line
    simple = [m for m in method_lines if "(" not in m]
    complex_ = [m for m in method_lines if "(" in m]

    if simple:
        # Pack up to 6 simple methods per line
        for i in range(0, len(simple), 6):
            lines.append(indent + " ".join(simple[i:i+6]))

    for m in complex_[:_MAX_METHODS]:
        lines.append(indent + m)

    total = len(method_lines)
    if total > _MAX_METHODS:
        lines.append(f"{indent}… +{total - _MAX_METHODS} more")


def _fmt_params(params: list) -> str:
    """Compact parameter list string."""
    parts = []
    for pg in params:
        if not isinstance(pg, dict):
            continue
        names = ",".join(pg.get("names", []))
        tr = pg.get("typeRef", {})
        tname = tr.get("name", "") if tr else ""
        if tname:
            parts.append(f"{names}:{tname}")
        else:
            parts.append(names)
    return ",".join(parts)


def to_outline(ast: dict) -> str:
    """Return a compact text outline of a slim AST for LLM consumption.

    Accepts the output of ``slim_ast()``.  Much smaller than the JSON
    representation — typically 15-25x fewer tokens.
    """
    lines: list = []

    kind = ast.get("kind", "")

    if kind == "Unit":
        lines.append(_outline_unit(ast))

    elif kind in ("GroupProject",):
        for proj in ast.get("resolvedProjects", []):
            proj_name = proj.get("mainSource", proj.get("filename", "?"))
            platform = proj.get("platform", "")
            config = proj.get("config", "")
            units = proj.get("resolvedUnits", [])
            unit_count = len(proj.get("units", units))
            lines.append(
                f"// {proj_name} — {platform}/{config} — {unit_count} units"
            )
            for u in units:
                if isinstance(u, dict) and u.get("kind") == "Unit":
                    lines.append(_outline_unit(u))
            lines.append("")

    elif kind in ("Program", "Library"):
        name = ast.get("name", "?")
        lines.append(f"// {name}")
        for u in ast.get("resolvedUnits", []):
            if isinstance(u, dict) and u.get("kind") == "Unit":
                lines.append(_outline_unit(u))

    elif kind == "MultiUnit":
        for u in ast.get("units", []):
            if isinstance(u, dict) and u.get("kind") == "Unit":
                lines.append(_outline_unit(u))

    else:
        # Fallback: just dump top-level unit if present
        if kind == "Unit":
            lines.append(_outline_unit(ast))

    return "\n".join(lines)
```

Add `"to_outline"` to `__all__` in `src/pydelphiast/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_parser.py::TestToOutline -v
```

Expected: all PASS.

- [ ] **Step 5: Run full test suite**

```
pytest -v
```

Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/pydelphiast/__init__.py tests/test_parser.py
git commit -m "feat: add to_outline() for compact LLM-friendly AST representation"
```

---

### Task 4: Update `/documentar` skill — .docs/.projects layout + outline usage

**Files:**
- Modify: `C:/Users/vinicius.martinez/.claude/skills/documentar/SKILL.md`
- Modify: `c:/Users/vinicius.martinez/Documents/PyDelphiAST/.claude/skills/documentar/SKILL.md`

Both files are identical — apply the same change to both.

- [ ] **Step 1: Rewrite both SKILL.md files**

Replace the content of both copies with:

```markdown
---
name: documentar
description: Use when asked to document, map, or analyze a Delphi repository or source file. Triggered by /documentar. Parses syntax with PyDelphiAST, derives semantic understanding from the outline artifact, and writes analysis to .docs/. Artifacts go to .projects/.
---

# /documentar

Analyzes a Delphi codebase in two phases — syntactic (PyDelphiAST → outline) then semantic (Claude) — and writes documentation to `.docs/`. Reports token cost at the end.

## Usage

```
/documentar                          # document Delphi files in current directory
/documentar <path>                   # .pas, .dpr, .dproj, .groupproj, or directory
/documentar <path> --out <file>      # custom output path (default: .docs/DELPHI_DOCS.md)
/documentar <path> --full-ast        # also write full slim_ast.json to .projects/
```

## Folder layout

```
<project-root>/
  .docs/
    DELPHI_DOCS.md          ← semantic analysis (LLM output)
  .projects/
    slim_ast.json           ← canonical JSON artifact (tools / RAG)
    outline.txt             ← compact text artifact (LLM input)
```

Create both folders if they do not exist.

## Workflow

### Phase 1 — Syntactic mapping (PyDelphiAST)

Run PyDelphiAST on the target and produce both artifacts.

```python
import pydelphiast as pda, json, os, sys

target = sys.argv[1] if len(sys.argv) > 1 else "."

# Resolve: if directory, find the root project file
if os.path.isdir(target):
    for ext in (".groupproj", ".dproj", ".dpr"):
        candidates = [f for f in os.listdir(target) if f.endswith(ext)]
        if candidates:
            target = os.path.join(target, candidates[0])
            break
    else:
        import glob as G
        target = sorted(G.glob(os.path.join(target, "**", "*.pas"), recursive=True))

# Parse
if isinstance(target, list):
    ast = {"kind": "MultiUnit", "units": [pda.parse_file(p) for p in target]}
else:
    ast = pda.parse_file(target)

root = os.path.dirname(target) if isinstance(target, str) else "."
os.makedirs(os.path.join(root, ".projects"), exist_ok=True)
os.makedirs(os.path.join(root, ".docs"), exist_ok=True)

# Slim + outline
slim = pda.slim_ast(ast)
outline = pda.to_outline(slim)

slim_path = os.path.join(root, ".projects", "slim_ast.json")
outline_path = os.path.join(root, ".projects", "outline.txt")

with open(slim_path, "w", encoding="utf-8") as f:
    json.dump(slim, f, ensure_ascii=False, indent=2)
with open(outline_path, "w", encoding="utf-8") as f:
    f.write(outline)

slim_chars = len(json.dumps(slim))
outline_chars = len(outline)
print(f"slim_ast.json : {slim_chars:,} chars  ≈ {slim_chars//4:,} tokens")
print(f"outline.txt   : {outline_chars:,} chars  ≈ {outline_chars//4:,} tokens")
print(f"Savings       : {slim_chars // max(outline_chars, 1)}x vs JSON")
```

Save outline token count before Phase 2.

### Phase 2 — Semantic analysis (Claude)

Read `.projects/outline.txt` into context. **Do not read slim_ast.json** — outline is sufficient and costs far fewer tokens.

Analyze the outline and derive:

1. **Project overview** — what does this project do? type (VCL app, service, library…)
2. **Architecture** — layers, major subsystems, how units relate
3. **Domain model** — key types and relationships
4. **Public API surface** — exported routines, interfaces, entry points
5. **Dependency map** — local uses-clause graph; flag circular or deep chains
6. **Complexity hotspots** — units/classes with many methods or deep inheritance
7. **Documentation gaps** — public declarations likely lacking documentation

### Output — .docs/DELPHI_DOCS.md

Write `.docs/DELPHI_DOCS.md` (or `--out` path).
Prefix with:

```markdown
# DELPHI_DOCS.md

This file documents the Delphi codebase. Generated by /documentar using PyDelphiAST.
```

Sections (include only what the code reveals — do not invent):

```markdown
## Project Overview
## Architecture
## Domain Model
## Public API
## Dependency Map
## Complexity Hotspots
## Documentation Gaps
```

Same discipline as `/init`: no repeating, no generic advice, no invented sections, focus on what requires multiple files to understand.

### Token Report

```
─────────────────────────────────────────
 /documentar — token report
─────────────────────────────────────────
 .projects/slim_ast.json   <N> chars  ≈ <N/4> tokens  (canonical)
 .projects/outline.txt     <N> chars  ≈ <N/4> tokens  (LLM input)
 .docs/DELPHI_DOCS.md      <N> chars  ≈ <N/4> tokens  (output)
 LLM savings               ~<Nx> vs raw JSON
─────────────────────────────────────────
```

## What slim_ast keeps

| Kept | Stripped |
|------|---------|
| Units, programs, libraries | Routine bodies |
| Type definitions (class, record, interface, enum…) | Statement trees |
| Method signatures (no bodies) | Expression sub-trees |
| Fields, properties, consts, vars | startPos / endPos |
| Uses clauses | TypeSection/ConstSection/VarSection wrappers |

## Prerequisites

PyDelphiAST must be installed:

```bash
pip install -e .   # from repo root
```
```

- [ ] **Step 2: Verify both files were written**

```
cat "C:/Users/vinicius.martinez/.claude/skills/documentar/SKILL.md" | head -5
cat "c:/Users/vinicius.martinez/Documents/PyDelphiAST/.claude/skills/documentar/SKILL.md" | head -5
```

Both should show the same frontmatter.

- [ ] **Step 3: Commit the project-local copy**

```bash
git add .claude/skills/documentar/SKILL.md
git commit -m "feat: update /documentar skill — .docs/.projects layout, outline-first pipeline"
```
