# Design: Absolute File Paths in Outline

**Date:** 2026-06-24  
**Scope:** `src/pydelphiast/__init__.py` — 2 functions

## Problem

`to_outline()` / `_outline_unit()` produce a compact text artifact consumed by the `/documentar` skill's Phase 2 (Claude). The outline header per unit currently shows only the unit name and structural info — no file path. When analyzing multi-unit projects, Claude cannot correlate units to their location on disk.

## Goal

Every unit entry in `outline.txt` carries its absolute file path so Phase 2 can reference file locations in its architectural analysis.

## Approach

**Stamp at parse time** — `parse_file()` sets `filename` (absolute path) on the returned AST dict for `.pas`/`.dfm`/`.dpl`/`.dpk` files. `_outline_unit()` reads and renders it. All other pipeline stages are unchanged.

## Changes

### 1. `parse_file()` — stamp `filename`

File: [src/pydelphiast/__init__.py](../../src/pydelphiast/__init__.py)

After parsing `.pas` / `.dpl` / `.dpk` files, add before `return ast`:

```python
ast["filename"] = os.path.abspath(path)
```

After parsing `.dfm` / `.xfm` files, same addition before `return`.

`project.py` already does this for project-resolved units (line 132) — this matches the same pattern for standalone file parsing.

Project files (`.dpr`, `.dproj`, `.groupproj`) go through `DelphiProject` which already stamps them — no change needed there.

### 2. `_outline_unit()` — render `filename`

File: [src/pydelphiast/__init__.py](../../src/pydelphiast/__init__.py)

Header line changes from:
```
[ULoginForm] form > TLoginForm(TForm) uses: USession
```
to:
```
[ULoginForm] C:\Projects\MyApp\src\Forms\ULoginForm.pas form > TLoginForm(TForm) uses: USession
```

Implementation: read `node.get("filename", "")`, insert after `[name]` token if non-empty.

### 3. `slim_ast()` — no change

`filename` is not in `_STRIP_KEYS` and not in position keys, so it already passes through unchanged.

### 4. Skill script — no change

`SKILL.md` Phase 1 builds `MultiUnit` via `[pda.parse_file(p) for p in target]`. Since `parse_file()` now stamps `filename`, each unit carries its absolute path automatically. `to_outline()` picks it up. Zero changes to `SKILL.md`.

## Output example

```
[ULoginForm] C:\Projects\MyApp\src\Forms\ULoginForm.pas form > TLoginForm(TForm) uses: USession, UConfig
  +Create(AOwner:TComponent)
  +Execute:Boolean
  -ValidateFields:Boolean
```

## Constraints

- No commit, no push during implementation
- Revert branch to `d6d4d85` (before last commit) before implementing
- Additive-only API change: new `filename` key on returned dict, no existing keys removed

## Tests

Add assertion to existing unit-level parse tests: after `pda.parse_file("some.pas")`, confirm `ast["filename"] == os.path.abspath("some.pas")`.
