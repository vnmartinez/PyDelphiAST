# TOON Export — Design

**Data:** 2026-10-02
**Status:** Aprovado (decisões de formato, CLI e API vindas do orquestrador)

## Objetivo

Gerar uma exportação enxuta em **TOON** (Token-Oriented Object Notation) da
hierarquia essencial de um código Delphi, para consumo por LLMs com o menor
número de tokens possível:

```
Grupo (.groupproj) > Projetos (.dproj/.dpr) > Units (.pas) > Form (.dfm)
                                                          > Classes/Interfaces/Records
                                                            > Métodos (visibilidade, parâmetros, retorno)
```

Todo nível que corresponde a um arquivo carrega o seu caminho (`path`).

## Decisões aprovadas

1. **TOON oficial**: objetos por indentação, arrays primitivos inline
   `key[N]: a,b`, arrays de objetos uniformes em forma tabular
   `key[N]{f1,f2}:` + linhas, demais arrays em lista `- `. Aspas só quando a
   especificação exige. Zero dependências externas (encoder próprio).
2. **CLI**: `python -m pydelphiast <arquivo> --toon` grava `<stem>.toon` ao lado
   do primeiro arquivo de entrada (`-o` sobrescreve o destino).
3. **API**: `pydelphiast.to_toon()` e `pydelphiast.extract_compact_hierarchy()`.

## Arquitetura

Novo módulo `src/pydelphiast/toon.py` com três unidades independentes:

| Unidade | Responsabilidade | Entrada → Saída |
|---|---|---|
| `encode_toon(value)` | Encoder TOON genérico (não sabe nada de Delphi) | `dict/list/primitivo` → `str` |
| `extract_compact_hierarchy(ast, base_dir=None)` | Reduz o AST (completo **ou** `slim_ast`) à hierarquia essencial | `dict` ou `list[dict]` → `dict` |
| `to_toon(ast, base_dir=None)` | Composição: `encode_toon(extract_compact_hierarchy(ast, base_dir))` | AST → `str` |

`__init__.py` reexporta `to_toon`, `extract_compact_hierarchy` (e `encode_toon`)
e os adiciona a `__all__`. `__main__.py` ganha a flag `--toon`.

Ajustes pontuais em código existente (necessários para "path em cada nível"):

- `DelphiProject._parse_dpr` passa a gravar `ast["filename"] = path` (hoje o nó
  `Program`/`Library` do `.dpr` não tem caminho).
- `parse_file()` (ramo `.pas`) grava `filename` absoluto no form companheiro
  (`ast["form"]["filename"]`), como o `DelphiProject` já faz.

## Esquema compacto (saída de `extract_compact_hierarchy`)

Dict puro, sem `startPos`/`endPos`, sem corpos, sem campos/propriedades/consts.
Chaves com valor vazio (`None`, `""`, `[]`, `{}`) são omitidas, **exceto**
células de linhas tabulares (ver Métodos).

### Raiz

| AST de entrada (`kind`) | Raiz compacta |
|---|---|
| `GroupProject` | `{"base": ..., "group": Group}` |
| `DprojProject` | `{"base": ..., "project": Project}` |
| `Program` / `Library` / `Package` | `{"base": ..., "project": Project}` |
| `Unit` | `{"base": ..., "unit": Unit}` |
| `DfmObject` | `{"base": ..., "form": Form}` |
| `list` (CLI com vários arquivos) | `{"base": ..., "groups": [...], "projects": [...], "units": [...], "forms": [...]}` (só as chaves presentes, na ordem da primeira ocorrência; itens na ordem de entrada) |
| `ParseError` (raiz) | `{"base": ..., "error": {"path": ..., "message": ...}}` |

### Caminhos

- `base`: diretório absoluto em formato POSIX (`C:/Fontes/App`). Padrão: diretório
  do arquivo raiz (`filename` do nó raiz); para `list`, `os.path.commonpath` dos
  diretórios; se nenhum `filename` existir, `os.getcwd()`. O parâmetro
  `base_dir` sobrescreve.
- Todo `path`/`source` é **relativo a `base`**, em POSIX (`src/UMain.pas`).
  Nós sem `filename` (ex.: AST vindo de `parse_source`) simplesmente não têm `path`.
  Se `os.path.relpath` falhar (drive diferente no Windows), usa-se o caminho
  absoluto POSIX.
- Motivo: em TOON, `\` exige aspas + escape; caminhos absolutos repetidos
  gastam muitos tokens. Assim só `base` precisa de aspas (contém `:`).

### Group

```
{"name": <stem do .groupproj>, "path": <rel>, "projects": [Project, ...]}
```

Itens de `resolvedProjects`:
- `DprojProject` / `Program` / `Library` → `Project`.
- `ProjectRef` com `missing: true` → `{"name": stem, "path": rel(resolvido contra o dir do .groupproj), "missing": true}`.
- `UnknownProjectRef` → `{"name": stem, "path": rel}`.
- `ParseError` → `{"name": stem, "path": rel, "error": message}`.

### Project

```
{"name", "path", "source", "platform", "config", "units": [Unit, ...]}
```

- De `DprojProject`: `name` = nome do programa em `mainSourceAst.name` (ou stem
  do `.dproj`), `path` = `.dproj`, `source` = `.dpr` (`mainSourceAst.filename`, ou
  `mainSource` resolvido contra o dir do `.dproj`), `platform`, `config`,
  `units` = `mainSourceAst.resolvedUnits`.
- De `Program`/`Library`/`Package` (`.dpr` direto): `name`, `path` = `.dpr`
  (`filename`), sem `source`/`platform`/`config`; `units` = `resolvedUnits`.

### Unit

```
{"name", "path", "form": Form, "types": [Type, ...]}
```

- `types` vem de `interface.declarations` + `implementation.declarations`
  (nessa ordem). Aceita tanto a forma com `TypeSection{items}` (AST completo)
  quanto a achatada do `slim_ast`.
- Item `CircularRef` (unit já listada em outro projeto do grupo) →
  `{"name": stem, "path": rel, "ref": true}`.
- Item `ParseError` → `{"name": stem, "path": rel, "error": message}`.

### Form

```
{"name": <DfmObject.name>, "class": <className>, "path": <rel do .dfm>}
```

Sem propriedades nem componentes filhos (fora de escopo). Se o nó do form não
tiver `filename`, o caminho é derivado do `.pas` trocando a extensão por `.dfm`.

### Type

Só `TypeDecl` cujo `typeDefinition.kind` ∈ {`ClassType`, `InterfaceType`,
`DispinterfaceType`, `RecordType`, `ObjectType`}; declarações `forward`
(`isForward: true`) são ignoradas. `PackedType` é desembrulhado (`inner`).

```
{"name", "kind", "for": str, "ancestors": [str, ...], "methods": [Method, ...]}
```

- `kind`: `class` | `interface` | `dispinterface` | `record` | `object`;
  sufixo ` helper` quando `isHelper`.
- `for`: tipo estendido (`helperFor`), só em helpers.
- `ancestors`: nomes formatados por `_type_str` (classe base e interfaces).
- Membros vêm de `members` (classe/interface/object) ou `fields` (record);
  só `MethodDecl` vira método.

### Method (linha tabular)

Campos fixos, nessa ordem: `vis,kind,name,params,returns`.

- `vis`: `visibility` do nó (`private`, `strict private`, `protected`,
  `public`, `published`); default `public`.
- `kind`: `methodKind` (`procedure`, `function`, `constructor`, `destructor`,
  `operator`); prefixo `class ` quando `isClassMember`.
- `params`: grupos separados por `; `, cada um `[modificador ]nomes:tipo`
  com nomes separados por `,` (ex.: `const A,B:string; var C:Integer`).
  `OpenArrayParam` → `[mod ]array of T` / `array of const`. Valores default
  são omitidos. Sem parâmetros → `""`.
- `returns`: `_type_str(returnType)`; sem retorno → `""`.

### `_type_str` (formatação de tipos)

| Nó | Texto |
|---|---|
| `TypeRef` | `name` + `<a,b>` se houver `typeArgs` |
| `StringType` | `string` |
| `OpenArrayType` | `array of T` / `array of const` |
| `ArrayType` | `array of T` (dimensões omitidas) |
| `SetType` | `set of T` |
| `PointerType` | `^T` |
| `ProcType` / `MethodReference` | `procedure` / `function` / `reference to …` |
| `None` | `""` |
| outro | valor de `kind` |

## Encoder TOON (`encode_toon`)

Regras implementadas (subconjunto do spec oficial suficiente para este uso,
delimitador `,`, indentação de 2 espaços, `\n`, sem newline final):

- **Objeto**: `key: valor` por linha; objeto aninhado → `key:` e filhos
  indentados; objeto vazio → `key:`.
- **Array de primitivos**: `key[N]: v1,v2` (vazio → `key[0]:`).
- **Array tabular**: quando todos os itens são dicts com o mesmo conjunto
  ordenado de chaves e só valores primitivos → `key[N]{f1,f2}:` e uma linha
  por item, indentada, com células separadas por `,`.
- Consequência: uma lista de units só com `{name,path,ref}` sai tabular — correto pelo spec.
- **Lista**: demais arrays → `key[N]:` e itens `- `. Item objeto: primeira
  chave na linha do hífen (`- name: X`), restantes alinhadas com ela
  (indentação do hífen + 2). Item primitivo: `- v`.
- **Raiz**: dict é emitido sem cabeçalho; lista na raiz → `[N]:` + itens.
- **Primitivos**: `None`→`null`, `True/False`→`true/false`, números em forma
  canônica (`int` direto; `float` sem notação científica, sem zeros à direita,
  `-0`→`0`).
- **Chaves**: sem aspas se casarem `^[A-Za-z_][A-Za-z0-9_.]*$`; senão quotadas.
- **Strings exigem aspas** quando: vazias; espaço no início/fim; iguais a
  `true`/`false`/`null`; parecem número (`^-?\d+(\.\d+)?([eE][+-]?\d+)?$` ou
  zero à esquerda `^0\d+$`); contêm `:`, `"`, `\`, `[`, `]`, `{`, `}`, `,`,
  `\n`, `\r`, `\t`; ou começam com `-`.
- **Escapes** dentro de aspas: `\\`, `\"`, `\n`, `\r`, `\t`.

## Exemplo de saída

```
base: "C:/Fontes/MyApp"
group:
  name: MyGroup
  path: MyGroup.groupproj
  projects[1]:
    - name: MyApp
      path: MyApp.dproj
      source: MyApp.dpr
      platform: Win32
      config: Debug
      units[1]:
        - name: UMain
          path: UMain.pas
          form:
            name: MainForm
            class: TMainForm
            path: UMain.dfm
          types[1]:
            - name: TMainForm
              kind: class
              ancestors[1]: TForm
              methods[2]{vis,kind,name,params,returns}:
                published,procedure,FormCreate,"Sender:TObject",""
                public,class function,Make,"",TMainForm
```

## CLI

- Nova flag `--toon` em `_build_parser()`: "Output compact hierarchy in TOON
  format (.toon)".
- Com `--toon`: `text = pda.to_toon(output)` (ignora `--slim` e `--indent`);
  destino padrão `<dir do 1º arquivo>/<stem>.toon`; `-o` sobrescreve;
  mensagem `TOON written to <path>` em stderr.
- Sem `--toon`: comportamento atual inalterado.

## Tratamento de erros

- Extração nunca levanta exceção por nó desconhecido: kinds não reconhecidos
  são ignorados; nós `ParseError` viram campo `error`.
- `encode_toon` levanta `TypeError` para tipos não serializáveis (ex.: `set`,
  objetos arbitrários); a extração só produz `str/int/float/bool/None/dict/list`.

## Testes (`tests/test_toon.py`)

- Encoder: primitivos, regras de aspas/escape, objeto aninhado, array
  primitivo, tabular, lista com objetos, lista vazia, chave que exige aspas,
  `TypeError`.
- `_type_str` e formatação de parâmetros.
- Extração a partir de `parse_source` (unit com class/interface/record,
  helpers, forward, packed record, métodos de classe, visibilidade).
- Extração a partir de AST completo **e** de `slim_ast` dão o mesmo resultado.
- Projeto real em `tmp_path`: `.groupproj` → `.dproj` → `.dpr` → `.pas` +
  `.dfm` (paths relativos em todos os níveis, `base` correto, `missing`,
  `ref` para unit compartilhada).
- `to_toon` ponta a ponta (texto esperado exato para um caso pequeno).
- CLI: `--toon` gera `<stem>.toon`; `-o` respeitado; sem `--toon` continua JSON.
- Regressões: `_parse_dpr` grava `filename`; `parse_file` grava `filename` no form.

## Fora de escopo (YAGNI)

Decodificador TOON; `string[N]`; propriedades/campos/consts/vars; rotinas soltas;
componentes do DFM; valores default de parâmetros; dimensões de arrays;
delimitadores alternativos (`\t`, `|`); key folding.
