# Dual-Format Pipeline Design

**Date:** 2026-06-24  
**Status:** Approved  
**Scope:** PyDelphiAST + `/documentar` skill

---

## Problem

Two combined issues inflate token cost and reduce coverage:

1. **slim_ast JSON is verbose for LLM consumption** — structural scaffolding (`"kind"`, `"items"`, `"typeRef"`) accounts for ~80% of the token count. Semantic content is ~20%.
2. **DPR parser fails on `{$R *.res}`** — the main project's units are never resolved; the slim AST is incomplete for real-world projects.

**Measured baseline (CP02-PCSIS220):**
- slim_ast.json: 37,378 chars ≈ 9,344 tokens
- Main project units resolved: 0 (DPR parse failure)
- Test project units resolved: 3

---

## Decision: Dual-Format (Approach B)

Keep JSON as canonical representation; add `to_outline()` as a purpose-built compact view for LLM consumption.

```
parse_file()
    │
    ▼
slim_ast()
    │
    ├─► slim_ast.json     canonical — tools, RAG, diff, programmatic agents
    │
    └─► to_outline(slim)  compact text — LLM semantic analysis (~20x smaller)
            │
            ▼
        outline.txt        ~500 tokens vs ~9,000+ for JSON
```

| Artifact | Format | Consumer | Fidelity |
|---|---|---|---|
| `slim_ast.json` | JSON | Tools, RAG, agents, diff | Full |
| `outline.txt` | compact text | LLM analysis, /documentar | Lossy but sufficient |

---

## Changes

### 1. Fix DPR parser — skip `COMPILER_DIR` in program block

**File:** `src/pydelphiast/parsers/pas_parser.py`

`_parse_program_block` currently raises `ParseError` when it encounters `COMPILER_DIR` tokens (e.g., `{$R *.res}`) between statements. Fix: skip them, same as `skip_compiler_dirs()` already does in other contexts.

This unblocks resolution of all units in real-world `.dpr` files.

---

### 2. `slim_ast()` — flatten TypeSection/ConstSection wrappers

**File:** `src/pydelphiast/\_\_init\_\_.py`

`TypeSection` and `ConstSection` are containers that add one nesting level without semantic value. Flatten their `items` directly into the parent `declarations` list.

```json
// before
"declarations": [
  {"kind": "TypeSection", "items": [{"kind": "TypeDecl", "name": "TFoo", ...}]}
]

// after
"declarations": [
  {"kind": "TypeDecl", "name": "TFoo", ...}
]
```

Impact: ~10% reduction in JSON size. Also simplifies downstream programmatic traversal.

---

### 3. `to_outline(ast)` — new public function

**File:** `src/pydelphiast/\_\_init\_\_.py`  
**Export:** add to `__all__`

Accepts the slim AST dict, returns a compact UTF-8 string.

#### Output format

```
// <ProjectName> — <Platform>/<Config> — <N> units

[UnitName] <label> [> TClass(TAncestor)] [uses: Unit1, Unit2]
  props: Field1:Type, Field2:Type
  +PublicMethod(param:Type):Return
  -PrivateMethod()
  CLASS InnerClass: +method1 +method2
```

#### Label detection (heuristic, in order)

| Condition | Label |
|---|---|
| inherits `TDataModule` or name matches `udm*` | `datamodule` |
| inherits `TForm` or name matches `ufrm*` | `form` |
| name matches `uSQL*`, `upsq*` | `sql` |
| name matches `uhel*` | `helper` |
| name matches `uPCTab*`, inherits `TBaseTabela` | `table` |
| name matches `ucls*`, `TFacade` in name | `facade` |
| default | `unit` |

#### Compaction rules

- Methods with no params and no return: group on one line `+Setup +TearDown +Destroy`
- `sql` and `helper` units: count routines only — `— 12 routines` (no method listing)
- Uses clause: omit `System.*`, `Vcl.*`, `Winapi.*`, `FMX.*` — only project-local units
- Properties: only public/published, name+type only (no read/write specifiers)
- If a class has >8 methods: list first 6, append `… +N more`

#### Example output (CP02-PCSIS220)

```
// PCSIS220 — Win32/Debug — 115 units

[udmDados] datamodule uses: uhelDados_Processos
[ufrmPrincipal] form > TfrmPrincipal(TfrmBase) uses: udmDados
  +FormCreate +FormClose +FormShow
[uSQL220] sql — 23 routines
[uTributacaoPedido] unit > TTributacaoPedido
  +Calcular(pedido:TPedido):Boolean
  +ValidarAliquota():Boolean
[uOperacoesMat] unit
  CLASS TRound: +class Arredondar(pValor,pCasas:Double):Double
  CLASS TMultiplic: +class MultiplicarQtde(pQtde,pValor:Double):Double
```

---

### 4. `/documentar` skill — use outline for LLM phase

**File:** `.claude/skills/documentar/SKILL.md` (both global and project copies)

Phase 1 generates both artifacts:
```python
slim = pda.slim_ast(ast)
outline = pda.to_outline(slim)

with open("slim_ast.json", "w", encoding="utf-8") as f:
    json.dump(slim, f, ensure_ascii=False, indent=2)
with open("outline.txt", "w", encoding="utf-8") as f:
    f.write(outline)
```

Phase 2 reads `outline.txt` (not `slim_ast.json`) for LLM semantic analysis.

Token report updated:
```
─────────────────────────────────────────
 /documentar — token report
─────────────────────────────────────────
 slim_ast.json   <N> chars  ≈ <N/4> tokens  (canonical)
 outline.txt     <N> chars  ≈ <N/4> tokens  (LLM input)
 DELPHI_DOCS.md  <N> chars  ≈ <N/4> tokens  (output)
 LLM savings     ~20x vs raw JSON
─────────────────────────────────────────
```

---

## Files Changed

| File | Change |
|---|---|
| `src/pydelphiast/parsers/pas_parser.py` | Skip `COMPILER_DIR` in `_parse_program_block` |
| `src/pydelphiast/__init__.py` | `slim_ast()` flatten TypeSection/ConstSection; add `to_outline()`; export |
| `.claude/skills/documentar/SKILL.md` | Phase 1 generates outline; Phase 2 reads outline |
| `~/.claude/skills/documentar/SKILL.md` | Same update (global copy) |

---

## Out of Scope

- MessagePack / binary serialization
- Streaming AST for very large projects
- `to_outline()` reverse parser (outline → AST)
