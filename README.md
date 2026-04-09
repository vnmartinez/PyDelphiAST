# PyDelphiAST

[Português](#português) | [English](#english)

---

## Português

PyDelphiAST é um parser em Python para código-fonte Delphi que gera uma AST serializável em JSON.

Suporta parsing de arquivo único e travessia completa de projeto:

- `.groupproj` → `.dproj` → `.dpr` → `.pas` / `.dfm`
- `.pas`, `.dpr`, `.dpk`, `.dpl`
- `.dfm` / `.xfm` em modo texto

### Funcionalidades

- Parser recursivo descendente para Delphi 10 (`unit`, `program`, `library`, `package`).
- Lexer com palavras reservadas, diretivas, literais, operadores, comentários e diretivas de compilador.
- Nós AST com posições no código-fonte (`startPos`, `endPos`).
- Modo não-fatal por padrão — insere nós `ParseError` e continua.
- Travessia automática de projeto ao receber `.dpr`, `.dproj` ou `.groupproj`.
- Resolve units do `uses` e anexa formulários `.dfm` companheiros automaticamente.
- CLI e API Python.

### Instalação

```bash
pip install -e .
```

Requer Python `>=3.10`.

### Uso via CLI

```bash
python -m pydelphiast FILE
pydelphiast FILE
```

O resultado é sempre gravado em um arquivo JSON — nada é impresso no terminal.

```bash
# Parse de um único arquivo .pas → gera MyUnit.json
pydelphiast MyUnit.pas

# Parse de projeto completo a partir do .dpr → gera MyApp.json
pydelphiast MyApp.dpr

# Parse da hierarquia completa a partir do .groupproj → gera MyApp.json
pydelphiast MyApp.groupproj

# Especificar arquivo de saída
pydelphiast MyApp.groupproj -o ast.json

# Desativar carregamento automático de .dfm companheiro
pydelphiast MyUnit.pas --no-forms

# Interromper no primeiro erro de parse
pydelphiast MyApp.dpr --stop-on-error
```

| Opção | Descrição |
|---|---|
| `-o FILE` | Arquivo de saída (padrão: `<stem>.json` junto ao arquivo de entrada) |
| `--encoding` | Codificação dos arquivos fonte (padrão `utf-8-sig`) |
| `--indent N` | Indentação JSON (padrão `2`; use `0` para compacto) |
| `--no-forms` | Não carregar formulários `.dfm` companheiros |
| `--stop-on-error` | Falhar imediatamente no primeiro erro de parse |

### API Python

```python
import pydelphiast as pda

# parse_file percorre hierarquia automaticamente para project files
ast = pda.parse_file("MyApp.dpr")         # percorre todo o projeto
ast = pda.parse_file("MyUnit.pas")        # unit única + .dfm companheiro
ast = pda.parse_file("MyApp.groupproj")   # hierarquia completa

# Parse de string de código-fonte
ast = pda.parse_source("unit U; interface implementation end.", "U.pas")

# Converter para texto JSON
json_text = pda.to_json(ast, indent=2)
```

- `parse_file(path, encoding="utf-8-sig", include_forms=True)`
- `parse_source(src, filename="<unknown>")`
- `parse_project(root, encoding, include_forms, stop_on_error)`
- `to_json(ast, indent=2, ensure_ascii=False)`
- helpers de baixo nível: `parse_pas`, `parse_dfm`, `parse_groupproj`, `parse_dproj`, `tokenize`

### Formato da AST

```json
{
  "kind": "NodeType",
  "startPos": { "line": 1, "col": 1 },
  "endPos":   { "line": 1, "col": 10 }
}
```

Tipos de nó comuns: `Unit`, `Program`, `ClassType`, `RecordType`, `InterfaceType`,
`MethodDecl`, `FieldDecl`, `PropertyDecl`, `RoutineDecl`, `TypeDecl`,
`DfmObject`, `DfmProperty`, `ParseError`.

### Comportamento de travessia

| Extensão | Comportamento |
|---|---|
| `.groupproj` | Resolve referências de projeto → percorre cada `.dproj` |
| `.dproj` | Lê metadados MSBuild → percorre `.dpr` principal |
| `.dpr` | Percorre todas as units referenciadas no `uses` |
| `.pas` | Unit única + `.dfm`/`.xfm` companheiro (se existir) |
| `.dfm` | Formulário único |

### Limitações

- `.dfm` binário não é suportado; use `.dfm` em modo texto.
- Alvo sintático é Delphi 10 (Seattle).
- Resolução de units usa caminhos relativos à estrutura do projeto.

### Desenvolvimento

```bash
pytest
pytest tests/test_lexer.py -v
pytest tests/test_parser.py -v
```

---

## English

PyDelphiAST is a Python parser for Delphi source files that produces a JSON-serializable AST.

Supports single-file parsing and full project traversal across:

- `.groupproj` → `.dproj` → `.dpr` → `.pas` / `.dfm`
- `.pas`, `.dpr`, `.dpk`, `.dpl`
- text-mode `.dfm` / `.xfm`

### Features

- Recursive-descent parser for Delphi 10 (`unit`, `program`, `library`, `package`).
- Lexer covering all reserved words, directives, literals, operators, comments, and compiler directives.
- AST nodes carry source positions (`startPos`, `endPos`) for downstream tooling.
- Non-fatal parse mode by default — inserts `ParseError` nodes and continues.
- Automatic project traversal when given a `.dpr`, `.dproj`, or `.groupproj` file.
- Resolves `uses`-clause units and attaches companion `.dfm` forms automatically.
- CLI and Python API.

### Installation

```bash
pip install -e .
```

Requires Python `>=3.10`.

### CLI Usage

```bash
python -m pydelphiast FILE
pydelphiast FILE
```

Output is always written to a JSON file — nothing is printed to the terminal.

```bash
# Parse a single .pas file → produces MyUnit.json
pydelphiast MyUnit.pas

# Parse full project from .dpr → produces MyApp.json
pydelphiast MyApp.dpr

# Parse full hierarchy from .groupproj → produces MyApp.json
pydelphiast MyApp.groupproj

# Specify output file
pydelphiast MyApp.groupproj -o ast.json

# Disable companion .dfm loading
pydelphiast MyUnit.pas --no-forms

# Abort on first parse error
pydelphiast MyApp.dpr --stop-on-error
```

| Option | Description |
|---|---|
| `-o FILE` | Output file (default: `<stem>.json` next to the input file) |
| `--encoding` | Source file encoding (default `utf-8-sig`) |
| `--indent N` | JSON indentation (default `2`; `0` for compact) |
| `--no-forms` | Do not auto-load companion `.dfm` forms |
| `--stop-on-error` | Abort on the first parse error |

### Python API

```python
import pydelphiast as pda

# parse_file auto-walks the hierarchy for project files
ast = pda.parse_file("MyApp.dpr")         # walks full project
ast = pda.parse_file("MyUnit.pas")        # single unit + companion .dfm
ast = pda.parse_file("MyApp.groupproj")   # full hierarchy

# Parse from a source string
ast = pda.parse_source("unit U; interface implementation end.", "U.pas")

# Serialize to JSON
json_text = pda.to_json(ast, indent=2)
```

- `parse_file(path, encoding="utf-8-sig", include_forms=True)`
- `parse_source(src, filename="<unknown>")`
- `parse_project(root, encoding, include_forms, stop_on_error)`
- `to_json(ast, indent=2, ensure_ascii=False)`
- low-level helpers: `parse_pas`, `parse_dfm`, `parse_groupproj`, `parse_dproj`, `tokenize`

### AST Shape

```json
{
  "kind": "NodeType",
  "startPos": { "line": 1, "col": 1 },
  "endPos":   { "line": 1, "col": 10 }
}
```

Common node kinds: `Unit`, `Program`, `ClassType`, `RecordType`, `InterfaceType`,
`MethodDecl`, `FieldDecl`, `PropertyDecl`, `RoutineDecl`, `TypeDecl`,
`DfmObject`, `DfmProperty`, `ParseError`.

### Project Traversal

| Extension | Behaviour |
|---|---|
| `.groupproj` | Resolves project references → walks each `.dproj` |
| `.dproj` | Reads MSBuild metadata → walks main `.dpr` |
| `.dpr` | Parses program/library → resolves all `uses` units |
| `.pas` | Single unit + companion `.dfm`/`.xfm` if present |
| `.dfm` | Single form file |

### Limitations

- Binary `.dfm` is not supported; use text-mode `.dfm`.
- Grammar targets Delphi 10 (Seattle).
- Unit resolution is path-based relative to the project directory.

### Development

```bash
pytest
pytest tests/test_lexer.py -v
pytest tests/test_parser.py -v
```

## License

MIT
