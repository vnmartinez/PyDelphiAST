"""PyDelphiAST – Delphi 10 source parser and AST generator.

Quick start::

    import pydelphiast as pda
    import json

    # Parse a single .pas unit
    ast = pda.parse_file("MyUnit.pas")
    print(json.dumps(ast, indent=2))

    # Parse a whole project (follows .groupproj → .dproj → .dpr → .pas)
    ast = pda.parse_project("MyApp.groupproj")
    print(json.dumps(ast, indent=2))

    # Parse source string directly
    ast = pda.parse_source(source_text, filename="MyUnit.pas")
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .errors import DelphiError, LexerError, ParseError
from .lexer import Token, tokenize
from .parsers.dfm_parser import parse_dfm
from .parsers.groupproj_parser import parse_dproj, parse_groupproj
from .parsers.pas_parser import parse_pas
from .project import DelphiProject

__version__ = "0.1.0"
__all__ = [
    # High-level API
    "parse_file",
    "parse_source",
    "parse_project",
    # Low-level parsers
    "parse_pas",
    "parse_dfm",
    "parse_groupproj",
    "parse_dproj",
    # Project walker
    "DelphiProject",
    # Tokeniser
    "tokenize",
    "Token",
    # Errors
    "DelphiError",
    "LexerError",
    "ParseError",
    # Slim view
    "slim_ast",
    # Outline view
    "to_outline",
]


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def parse_file(
    path: str,
    encoding: str = "utf-8-sig",
    include_forms: bool = True,
) -> dict:
    """Parse a Delphi file, automatically following the project hierarchy.

    For project files (.dpr, .dproj, .groupproj) this walks the full hierarchy
    and resolves all referenced units and forms.  For .pas and .dfm files it
    parses only that file (plus the companion .dfm when *include_forms* is True).

    Returns a JSON-serialisable dict representing the AST.
    """
    ext = os.path.splitext(path)[1].lower()

    # Project files: walk the full hierarchy
    if ext in (".dpr", ".dproj", ".groupproj"):
        return DelphiProject(
            path,
            encoding=encoding,
            include_forms=include_forms,
        ).parse()

    with open(path, encoding=encoding, errors="replace") as fh:
        src = fh.read()

    if ext in (".pas", ".dpl", ".dpk"):
        ast = parse_pas(src, path)
        if include_forms:
            dfm_path = os.path.splitext(path)[0] + ".dfm"
            if os.path.isfile(dfm_path):
                with open(dfm_path, encoding=encoding, errors="replace") as fh:
                    ast["form"] = parse_dfm(fh.read(), dfm_path)
        return ast

    if ext in (".dfm", ".xfm"):
        return parse_dfm(src, path)

    raise ValueError(f"Unsupported file extension: {ext!r}")


def parse_source(
    src: str,
    filename: str = "<unknown>",
) -> dict:
    """Parse a Delphi source string.

    The file type is inferred from *filename*'s extension.  Defaults to .pas.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".dfm", ".xfm"):
        return parse_dfm(src, filename)
    if ext == ".groupproj":
        return parse_groupproj(src, filename)
    if ext == ".dproj":
        return parse_dproj(src, filename)
    return parse_pas(src, filename)


def parse_project(
    root: str,
    encoding: str = "utf-8-sig",
    include_forms: bool = True,
    stop_on_error: bool = False,
) -> dict:
    """Parse an entire Delphi project, following the file hierarchy.

    *root* may be a ``.groupproj``, ``.dproj``, ``.dpr``, or ``.pas`` file.
    Returns a JSON-serialisable dict with a tree of all parsed units/forms.
    """
    return DelphiProject(
        root,
        encoding=encoding,
        include_forms=include_forms,
        stop_on_error=stop_on_error,
    ).parse()


def to_json(ast: dict, indent: int = 2, ensure_ascii: bool = False) -> str:
    """Serialise an AST dict to a JSON string."""
    return json.dumps(ast, indent=indent, ensure_ascii=ensure_ascii, default=str)


# ---------------------------------------------------------------------------
# Slim / structural-only view
# ---------------------------------------------------------------------------

# Node kinds that represent structural declarations worth keeping
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

# Keys that carry bulk statement/body trees — always stripped in slim mode.
# Expression sub-keys (left/right/args/…) are NOT listed here because they
# only appear inside bodies which are already stripped, and stripping them
# globally would also erase useful info like defaultValue literals.
_STRIP_KEYS = {"body", "statements", "condition", "elseStmt",
               "thenStmt", "initStmt", "finalStmt",
               "initSection", "finalSection"}

# Wrapper section kinds whose items are inlined into the parent declarations list
_FLATTEN_KINDS = {"TypeSection", "ConstSection", "VarSection"}


def slim_ast(node: object) -> object:
    """Return a structural-only view of an AST node.

    Removes ``startPos``/``endPos`` from every node, strips routine bodies
    and expression trees, and flattens TypeSection/ConstSection/VarSection
    wrappers so declarations appear directly in their parent list.
    """
    if isinstance(node, list):
        result = [slim_ast(item) for item in node]
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
            # Keep only name + path from UsesItem
            out[key] = [
                {k: v for k, v in slim_ast(i).items() if k in ("kind", "name", "path")}
                for i in (val or [])
                if isinstance(i, dict)
            ]
            continue
        out[key] = slim_ast(val)

    # Drop empty containers produced by stripping
    out = {k: v for k, v in out.items() if v not in (None, [], {})}
    return out


# ---------------------------------------------------------------------------
# Outline view — compact text for LLM consumption
# ---------------------------------------------------------------------------

_SYSTEM_PREFIXES = (
    "System.", "Vcl.", "Winapi.", "FMX.", "Web.", "Xml.",
    "Data.", "FireDAC.", "Soap.", "Datasnap.", "REST.",
    "IdHTTP", "SysUtils", "Classes", "Math", "StrUtils",
    "DateUtils", "IOUtils", "RegularExpressions",
)

_BULK_LABELS = {"sql", "helper"}
_MAX_METHODS = 8


def _outline_label(unit_name: str, ancestors: list) -> str:
    n = unit_name.lower()
    anc = " ".join(a.get("name", "") for a in ancestors if isinstance(a, dict)).lower()
    if n.startswith("udm") or "tdatamodule" in anc:
        return "datamodule"
    if n.startswith("ufrm") or "tform" in anc:
        return "form"
    if n.startswith("upsq") or n.startswith("usql"):
        return "sql"
    if n.startswith("uhel"):
        return "helper"
    if n.startswith("upcta") or "tbasetabela" in anc:
        return "table"
    if n.startswith("ucls") or "facade" in n:
        return "facade"
    return "unit"


def _fmt_params(params: list) -> str:
    parts = []
    for pg in params:
        if not isinstance(pg, dict):
            continue
        names = ",".join(pg.get("names", []))
        tr = pg.get("typeRef", {}) or {}
        tname = tr.get("name", "")
        parts.append(f"{names}:{tname}" if tname else names)
    return ",".join(parts)


def _method_tokens(members: list) -> list:
    out = []
    for m in members:
        if not isinstance(m, dict) or m.get("kind") != "MethodDecl":
            continue
        vis = m.get("visibility", "public")
        prefix = "+" if vis in ("public", "published") else "-"
        if m.get("isClassMember"):
            prefix = "+class "
        name = m.get("name", "?")
        params = m.get("params", [])
        ret = m.get("returnType") or {}
        if params or ret.get("name"):
            ret_str = f":{ret['name']}" if ret.get("name") else ""
            out.append(f"{prefix}{name}({_fmt_params(params)}){ret_str}")
        else:
            out.append(f"{prefix}{name}")
    return out


def _render_members(members: list, lines: list, indent: str = "  ") -> None:
    tokens = _method_tokens(members)
    if not tokens:
        return
    simple = [t for t in tokens if "(" not in t]
    complex_ = [t for t in tokens if "(" in t]
    for i in range(0, len(simple), 6):
        lines.append(indent + " ".join(simple[i:i + 6]))
    for t in complex_[:_MAX_METHODS]:
        lines.append(indent + t)
    if len(tokens) > _MAX_METHODS:
        lines.append(f"{indent}… +{len(tokens) - _MAX_METHODS} more")


def _outline_unit(node: dict) -> str:
    name = node.get("name", "?")
    iface = node.get("interface", {})
    uses_clause = iface.get("uses", {})
    decls = iface.get("declarations", [])

    local_uses = [
        i["name"] for i in uses_clause.get("items", [])
        if isinstance(i, dict)
        and not any(i.get("name", "").startswith(p) for p in _SYSTEM_PREFIXES)
    ]

    all_ancestors: list = []
    for d in decls:
        if isinstance(d, dict) and d.get("kind") == "TypeDecl":
            all_ancestors.extend(
                d.get("typeDefinition", {}).get("ancestors", [])
            )

    label = _outline_label(name, all_ancestors)

    primary: dict | None = None
    for d in decls:
        if isinstance(d, dict) and d.get("kind") == "TypeDecl":
            if d.get("typeDefinition", {}).get("kind") in (
                "ClassType", "RecordType", "InterfaceType"
            ):
                primary = d
                break

    header = f"[{name}] {label}"
    if primary:
        td = primary["typeDefinition"]
        ancs = [a.get("name") for a in td.get("ancestors", []) if a.get("name")]
        anc_str = f"({',' .join(ancs)})" if ancs else ""
        header += f" > {primary['name']}{anc_str}"
    if local_uses:
        header += f" uses: {', '.join(local_uses)}"

    lines = [header]

    if label in _BULK_LABELS:
        n = sum(1 for d in decls if isinstance(d, dict) and d.get("kind") == "RoutineDecl")
        if n:
            lines.append(f"  — {n} routines")
        return "\n".join(lines)

    if primary:
        _render_members(primary["typeDefinition"].get("members", []), lines)

    for d in decls:
        if d is primary or not isinstance(d, dict):
            continue
        if d.get("kind") == "TypeDecl" and d.get("typeDefinition", {}).get("kind") in (
            "ClassType", "RecordType", "InterfaceType"
        ):
            tokens = _method_tokens(d["typeDefinition"].get("members", []))
            if tokens:
                lines.append(f"  CLASS {d['name']}: {' '.join(tokens[:6])}")

    return "\n".join(lines)


def to_outline(ast: dict) -> str:
    """Return a compact text outline of a slim AST for LLM consumption.

    Accepts the output of ``slim_ast()``. Typically 15-25x fewer tokens
    than the JSON representation.
    """
    lines: list = []
    kind = ast.get("kind", "")

    if kind == "Unit":
        lines.append(_outline_unit(ast))

    elif kind == "GroupProject":
        for proj in ast.get("resolvedProjects", []):
            src = proj.get("mainSource", proj.get("filename", "?"))
            plat = proj.get("platform", "")
            cfg = proj.get("config", "")
            # Units may be at dproj level or nested inside mainSourceAst
            main_ast = proj.get("mainSourceAst", {})
            resolved = proj.get("resolvedUnits") or main_ast.get("resolvedUnits", [])
            unit_count = len(proj.get("units", resolved))
            lines.append(f"// {src} — {plat}/{cfg} — {unit_count} units")
            for u in resolved:
                if isinstance(u, dict) and u.get("kind") == "Unit":
                    lines.append(_outline_unit(u))
            lines.append("")

    elif kind in ("Program", "Library"):
        lines.append(f"// {ast.get('name', '?')}")
        for u in ast.get("resolvedUnits", []):
            if isinstance(u, dict) and u.get("kind") == "Unit":
                lines.append(_outline_unit(u))

    elif kind == "MultiUnit":
        for u in ast.get("units", []):
            if isinstance(u, dict) and u.get("kind") == "Unit":
                lines.append(_outline_unit(u))

    return "\n".join(lines)
