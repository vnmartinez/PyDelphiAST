# Outline Filename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stamp each AST root with its absolute file path in `parse_file()` and render it in `_outline_unit()` so every unit entry in `outline.txt` shows its source location.

**Architecture:** Two targeted changes in one file (`src/pydelphiast/__init__.py`): `parse_file()` stamps `filename = os.path.abspath(path)` on the returned dict; `_outline_unit()` reads it and inserts it into the header between `[name]` and the label token. `slim_ast()` already passes `filename` through untouched (it is not in `_STRIP_KEYS`), so no changes needed there.

**Tech Stack:** Python 3.9+, pytest, pydelphiast (local editable install).

> **Session constraint:** No commits, no pushes during this session.

---

## File Map

| File | Action |
|------|--------|
| `src/pydelphiast/__init__.py` | Modify `parse_file()` (lines 90–100) and `_outline_unit()` (line 335) |
| `tests/test_parser.py` | Add `TestParseFileFilename` class and update `TestOutline` |

---

### Task 1: Stamp `filename` in `parse_file()` for `.pas` files

**Files:**
- Modify: `src/pydelphiast/__init__.py:90-97`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

Add this class at the bottom of `tests/test_parser.py`:

```python
# ---------------------------------------------------------------------------
# parse_file filename stamping
# ---------------------------------------------------------------------------

class TestParseFileFilename:
    def test_pas_file_gets_absolute_filename(self, tmp_path):
        src = "unit UTest;\ninterface\nimplementation\nend.\n"
        p = tmp_path / "UTest.pas"
        p.write_text(src, encoding="utf-8")
        ast = pda.parse_file(str(p), include_forms=False)
        assert ast.get("filename") == str(p.resolve())
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_parser.py::TestParseFileFilename::test_pas_file_gets_absolute_filename -v
```

Expected: FAIL — `assert None == '...'` (key missing)

- [ ] **Step 3: Implement — stamp filename for `.pas`/`.dpl`/`.dpk`**

In `src/pydelphiast/__init__.py`, change lines 90–97 from:

```python
    if ext in (".pas", ".dpl", ".dpk"):
        ast = parse_pas(src, path)
        if include_forms:
            dfm_path = os.path.splitext(path)[0] + ".dfm"
            if os.path.isfile(dfm_path):
                with open(dfm_path, encoding=encoding, errors="replace") as fh:
                    ast["form"] = parse_dfm(fh.read(), dfm_path)
        return ast
```

to:

```python
    if ext in (".pas", ".dpl", ".dpk"):
        ast = parse_pas(src, path)
        ast["filename"] = os.path.abspath(path)
        if include_forms:
            dfm_path = os.path.splitext(path)[0] + ".dfm"
            if os.path.isfile(dfm_path):
                with open(dfm_path, encoding=encoding, errors="replace") as fh:
                    ast["form"] = parse_dfm(fh.read(), dfm_path)
        return ast
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_parser.py::TestParseFileFilename::test_pas_file_gets_absolute_filename -v
```

Expected: PASS

---

### Task 2: Stamp `filename` in `parse_file()` for `.dfm` files

**Files:**
- Modify: `src/pydelphiast/__init__.py:99-100`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

Add to `TestParseFileFilename` class:

```python
    def test_dfm_file_gets_absolute_filename(self, tmp_path):
        src = "object Form1: TForm1\nend\n"
        p = tmp_path / "Form1.dfm"
        p.write_text(src, encoding="utf-8")
        ast = pda.parse_file(str(p))
        assert ast.get("filename") == str(p.resolve())
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_parser.py::TestParseFileFilename::test_dfm_file_gets_absolute_filename -v
```

Expected: FAIL — `assert None == '...'`

- [ ] **Step 3: Implement — stamp filename for `.dfm`/`.xfm`**

In `src/pydelphiast/__init__.py`, change lines 99–100 from:

```python
    if ext in (".dfm", ".xfm"):
        return parse_dfm(src, path)
```

to:

```python
    if ext in (".dfm", ".xfm"):
        result = parse_dfm(src, path)
        result["filename"] = os.path.abspath(path)
        return result
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_parser.py::TestParseFileFilename::test_dfm_file_gets_absolute_filename -v
```

Expected: PASS

- [ ] **Step 5: Confirm slim_ast passes filename through (no code change)**

Add to `TestParseFileFilename`:

```python
    def test_slim_ast_preserves_filename(self, tmp_path):
        src = "unit UTest;\ninterface\nimplementation\nend.\n"
        p = tmp_path / "UTest.pas"
        p.write_text(src, encoding="utf-8")
        ast = pda.parse_file(str(p), include_forms=False)
        slim = pda.slim_ast(ast)
        assert slim.get("filename") == str(p.resolve())
```

Run:

```
pytest tests/test_parser.py::TestParseFileFilename::test_slim_ast_preserves_filename -v
```

Expected: PASS (no code change — `slim_ast` already passes `filename` through)

---

### Task 3: Render `filename` in `_outline_unit()` header

**Files:**
- Modify: `src/pydelphiast/__init__.py:335`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

Add to `TestParseFileFilename`:

```python
    def test_outline_header_contains_filename(self, tmp_path):
        src = "unit ULogin;\ninterface\ntype\n  TLogin = class(TForm)\n  end;\nimplementation\nend.\n"
        p = tmp_path / "ULogin.pas"
        p.write_text(src, encoding="utf-8")
        ast = pda.parse_file(str(p), include_forms=False)
        slim = pda.slim_ast(ast)
        outline = pda.to_outline(slim)
        abs_path = str(p.resolve())
        assert f"[ULogin] {abs_path}" in outline
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_parser.py::TestParseFileFilename::test_outline_header_contains_filename -v
```

Expected: FAIL — path not in outline header

- [ ] **Step 3: Implement — insert filename into header**

In `src/pydelphiast/__init__.py`, change line 335 in `_outline_unit()` from:

```python
    header = f"[{name}] {label}"
```

to:

```python
    filename = node.get("filename", "")
    header = f"[{name}]"
    if filename:
        header += f" {filename}"
    header += f" {label}"
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_parser.py::TestParseFileFilename::test_outline_header_contains_filename -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```
pytest -v
```

Expected: all existing tests pass. The existing `TestOutline` tests use `parse_source()` which does NOT stamp `filename`, so their output is unchanged — `filename` is simply absent from the header (the `if filename:` guard handles this).

---

### Task 4: End-to-end verification

**Files:**
- No changes — verification only

- [ ] **Step 1: Create a scratch .pas file and run the skill pipeline manually**

```python
# Run in Python REPL or as a one-off script
import pydelphiast as pda, os

# Use any existing .pas fixture or write a temp one
src = """unit UExample;
interface
type
  TExample = class(TObject)
  public
    procedure Run;
  end;
implementation
end.
"""

tmp = "C:/tmp/UExample.pas"
open(tmp, "w").write(src)

ast = pda.parse_file(tmp, include_forms=False)
slim = pda.slim_ast(ast)
outline = pda.to_outline(slim)
print(outline)
```

Expected output starts with:
```
[UExample] C:\tmp\UExample.pas unit > TExample(TObject)
```

- [ ] **Step 2: Verify MultiUnit path (directory scan)**

```python
import pydelphiast as pda, os, glob as G

# Assumes project root has .pas files somewhere
paths = sorted(G.glob("src/**/*.pas", recursive=True))
units = [pda.parse_file(p) for p in paths]
ast = {"kind": "MultiUnit", "units": units}
slim = pda.slim_ast(ast)
outline = pda.to_outline(slim)

# Every unit line should contain the absolute path
for line in outline.splitlines():
    if line.startswith("["):
        assert os.sep in line, f"No path in: {line}"

print("All unit headers contain file path")
print(outline[:500])
```

Expected: all `[UnitName]` header lines contain an absolute path with `os.sep`.

- [ ] **Step 3: Run full test suite one final time**

```
pytest -v
```

Expected: all tests pass, zero failures.
