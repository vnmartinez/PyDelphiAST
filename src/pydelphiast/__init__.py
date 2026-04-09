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
