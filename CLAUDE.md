# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PyDelphiAST is a Python tool for parsing Delphi 10 (Seattle) source code and returning a JSON AST.
It handles the full project hierarchy: `.groupproj` → `.dproj` → `.dpr` → `.pas` / `.dfm`.

## Commands

```bash
# Install (editable)
pip install -e .

# Run tests
pytest

# Run a single test module
pytest tests/test_lexer.py -v

# Parse a single .pas file → writes MyUnit.json next to it
python -m pydelphiast MyUnit.pas

# Parse a whole project (auto-detected by extension, no flag needed)
python -m pydelphiast MyApp.dpr
python -m pydelphiast MyApp.groupproj

# Save AST to a specific file
python -m pydelphiast MyUnit.pas -o ast.json
```

## Architecture

```
src/pydelphiast/
  tokens.py           – TT enum: all Delphi 10 reserved words + directives
                        Key sets: RESERVED, DIRECTIVES, ROUTINE_DIRECTIVES,
                        CALLING_CONVENTIONS, VISIBILITY_TYPES
  lexer.py            – Lexer class: tokenizes source → List[Token]
                        Handles {..} (*...*) // comments, {$..} directives,
                        'string' with '' escaping, #nn char literals, $hex
  parsers/
    base.py           – BaseParser: token navigation (check/match/expect/
                        advance, is_ident, parse_qualified_name, skip_compiler_dirs)
    pas_parser.py     – Recursive-descent parser for .pas / .dpr files
                        PasParser.parse() → Unit | Program | Library | Package
    dfm_parser.py     – Line-based parser for text-mode .dfm form files
    groupproj_parser.py – XML parsers for .groupproj and .dproj (MSBuild)
  project.py          – DelphiProject: walks the file hierarchy, resolves
                        uses-clause references, pairs .pas with .dfm
  __init__.py         – Public API: parse_file(), parse_source(), parse_project(),
                        to_json()
  __main__.py         – CLI entry point
```

### PasParser grammar coverage (Delphi 10)

- **File types**: `unit`, `program`, `library`, `package`
- **Sections**: `interface`, `implementation`, `initialization`/`finalization`
- **Declarations**: `type`, `const`, `var`, `threadvar`, `label`, `resourcestring`, `exports`
- **Type definitions**: class (with `abstract`/`sealed`/`helper`), record, interface,
  dispinterface, object, enum, subrange, set, array, file, pointer, procedure/function
  types, anonymous method references (`reference to procedure/function`), generics
  `TFoo<T, U>`, packed types, variant records
- **Class body**: visibility sections (`private`/`protected`/`public`/`published`,
  `strict` prefix), fields, methods, properties (with all specifiers), class members
- **Routines**: qualified names (e.g. `TClass.Method`), all parameter modifiers
  (`const`/`var`/`out`), open arrays, default values, all calling conventions,
  all directives (`virtual`/`override`/`abstract`/`dynamic`/`final`/`forward`/
  `external`/`inline`/`overload`/`reintroduce`…), anonymous methods
- **Statements**: `begin/end`, `if/then/else`, `case`, `for` (range and `for..in`),
  `while`, `repeat/until`, `try/except/finally`, `with`, `raise`, `goto`, labeled,
  `asm`, `inherited`
- **Expressions**: full Delphi precedence (`or/xor` → `and` → relational → additive
  → multiplicative → unary → postfix → primary), all literals, set constructors `[..]`,
  address `@`, dereference `^`, member access `.`, subscript `[]`, calls `()`

### AST node format

Every node is a plain `dict` with at minimum:
```json
{
  "kind": "NodeTypeName",
  "startPos": {"line": 1, "col": 1},
  "endPos":   {"line": 5, "col": 4},
  ... node-specific fields ...
}
```

Parse errors are non-fatal by default — an `{"kind": "ParseError", ...}` node is
inserted and parsing continues from the next recoverable token.

### Directives (context-sensitive keywords)

In Delphi, directives like `virtual`, `override`, `read`, `write`, `published`, etc.
are context-sensitive: they can appear as identifiers in most positions.
The lexer tokenises them as distinct `TT.D_*` types. `BaseParser.is_ident()` returns
`True` for both `TT.IDENT` and any `TT.D_*` token, so directive words are always
valid in identifier positions.

### DFM parser

`dfm_parser.py` handles text-mode DFM files (not binary). It line-parses the nested
`object … end` hierarchy and produces `DfmObject` nodes containing `DfmProperty`
children. Set literals (`[akLeft, akTop]`), item lists, and hex binary blocks are
recognised.

### GroupProj / dproj

Both use MSBuild XML (`xml.etree.ElementTree`). `.groupproj` lists project
references; `.dproj` records the main `.dpr` source, platform, config, and
`DCCReference` items (units + forms).
