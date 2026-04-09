"""Project walker – follows the .groupproj → .dproj → .dpr → .pas/.dfm hierarchy.

Usage::

    from pydelphiast.project import DelphiProject

    proj = DelphiProject("MyApp.groupproj")
    ast  = proj.parse()

*ast* is a plain dict ready for ``json.dumps``.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set

from .errors import ParseError
from .parsers.dfm_parser import parse_dfm
from .parsers.groupproj_parser import parse_dproj, parse_groupproj
from .parsers.pas_parser import parse_pas


class DelphiProject:
    """Parse an entire Delphi project, following the file hierarchy.

    Accepts any of:
      * ``.groupproj`` – Delphi group project (XML)
      * ``.dproj``    – Delphi project (XML / MSBuild)
      * ``.dpr``      – Delphi project source
      * ``.pas``      – Single unit
      * ``.dfm``      – Single form

    Parameters
    ----------
    root:
        Path to the root file.
    encoding:
        File encoding (default ``utf-8-sig`` to handle BOM).
    include_forms:
        Whether to parse companion .dfm files for each unit (default True).
    stop_on_error:
        When False (default), parse errors are caught and included as error
        nodes in the AST.  When True, the first error raises an exception.
    """

    def __init__(
        self,
        root: str,
        encoding: str = "utf-8-sig",
        include_forms: bool = True,
        stop_on_error: bool = False,
    ) -> None:
        self.root = os.path.abspath(root)
        self.encoding = encoding
        self.include_forms = include_forms
        self.stop_on_error = stop_on_error
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self) -> dict:
        """Return the complete project AST as a nested dict."""
        ext = os.path.splitext(self.root)[1].lower()
        if ext == ".groupproj":
            return self._parse_groupproj(self.root)
        if ext == ".dproj":
            return self._parse_dproj(self.root)
        if ext == ".dpr":
            return self._parse_dpr(self.root)
        if ext == ".pas":
            return self._parse_pas_file(self.root)
        if ext == ".dfm":
            return self._parse_dfm_file(self.root)
        raise ValueError(f"Unsupported file extension: {ext!r}")

    # ------------------------------------------------------------------
    # File-type handlers
    # ------------------------------------------------------------------

    def _parse_groupproj(self, path: str) -> dict:
        src = self._read(path)
        ast = parse_groupproj(src, path)

        resolved_projects: List[dict] = []
        for proj_ref in ast.get("projects", []):
            proj_path = self._resolve_relative(path, proj_ref["path"])
            if proj_path and os.path.isfile(proj_path):
                ext = os.path.splitext(proj_path)[1].lower()
                if ext == ".dproj":
                    resolved_projects.append(self._parse_dproj(proj_path))
                elif ext in (".dpr", ".pas"):
                    resolved_projects.append(self._parse_dpr(proj_path))
                else:
                    resolved_projects.append({"kind": "UnknownProjectRef",
                                              "path": proj_path})
            else:
                proj_ref["missing"] = True
                resolved_projects.append(proj_ref)

        ast["resolvedProjects"] = resolved_projects
        return ast

    def _parse_dproj(self, path: str) -> dict:
        src = self._read(path)
        ast = parse_dproj(src, path)

        base_dir = os.path.dirname(path)
        # Resolve main .dpr source
        dpr_path = self._resolve_relative(path, ast.get("mainSource", ""))
        if dpr_path and os.path.isfile(dpr_path):
            ast["mainSourceAst"] = self._parse_dpr(dpr_path)
        return ast

    def _parse_dpr(self, path: str) -> dict:
        src = self._read(path)
        ast = self._safe_parse_pas(src, path)
        # Follow uses references to .pas files in the same / nearby directories
        base_dir = os.path.dirname(path)
        ast["resolvedUnits"] = self._resolve_units(ast, base_dir)
        return ast

    def _parse_pas_file(self, path: str) -> dict:
        if path in self._seen:
            return {"kind": "CircularRef", "path": path}
        self._seen.add(path)

        src = self._read(path)
        ast = self._safe_parse_pas(src, path)
        ast["filename"] = path

        # Companion DFM
        if self.include_forms:
            dfm_path = os.path.splitext(path)[0] + ".dfm"
            if os.path.isfile(dfm_path):
                ast["form"] = self._parse_dfm_file(dfm_path)
            else:
                # Try .xfm
                xfm_path = os.path.splitext(path)[0] + ".xfm"
                if os.path.isfile(xfm_path):
                    ast["form"] = self._parse_dfm_file(xfm_path)

        return ast

    def _parse_dfm_file(self, path: str) -> dict:
        src = self._read(path)
        try:
            ast = parse_dfm(src, path)
        except Exception as exc:
            if self.stop_on_error:
                raise
            return {"kind": "ParseError", "filename": path, "message": str(exc)}
        ast["filename"] = path
        return ast

    # ------------------------------------------------------------------
    # Unit resolution
    # ------------------------------------------------------------------

    def _resolve_units(self, prog_ast: dict, base_dir: str) -> List[dict]:
        """Find and parse all .pas files referenced in uses clauses."""
        uses_items = self._collect_uses_items(prog_ast)
        resolved: List[dict] = []
        for item in uses_items:
            explicit_path = item.get("path")  # from  'in ...'  clause
            if explicit_path:
                # Use the explicit path first (strip surrounding quotes if present)
                explicit_path = explicit_path.strip("'\"")
                pas_path = self._resolve_relative_from_base(base_dir, explicit_path)
            else:
                pas_path = self._find_pas(item.get("name", ""), base_dir)
            if pas_path and os.path.isfile(pas_path):
                resolved.append(self._parse_pas_file(pas_path))
        return resolved

    def _collect_uses_items(self, node) -> List[dict]:
        """Walk AST and collect all UsesItem dicts."""
        items: List[dict] = []
        if isinstance(node, dict):
            if node.get("kind") == "UsesItem":
                items.append(node)
            else:
                for v in node.values():
                    items.extend(self._collect_uses_items(v))
        elif isinstance(node, list):
            for child in node:
                items.extend(self._collect_uses_items(child))
        return items

    def _find_pas(self, unit_name: str, base_dir: str) -> Optional[str]:
        """Locate a .pas file for *unit_name* relative to *base_dir*.

        Tries both the full dotted path (``System/SysUtils.pas``) and just the
        final component (``SysUtils.pas``).
        """
        file_stem = unit_name.split(".")[-1]
        candidates = [
            os.path.join(base_dir, unit_name.replace(".", os.sep) + ".pas"),
            os.path.join(base_dir, file_stem + ".pas"),
        ]
        for c in candidates:
            c = os.path.normpath(c)
            if os.path.isfile(c):
                return c
        return None

    @staticmethod
    def _resolve_relative_from_base(base_dir: str, rel: str) -> str:
        return os.path.normpath(os.path.join(base_dir, rel))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _read(self, path: str) -> str:
        with open(path, encoding=self.encoding, errors="replace") as fh:
            return fh.read()

    def _safe_parse_pas(self, src: str, filename: str) -> dict:
        try:
            return parse_pas(src, filename)
        except Exception as exc:
            if self.stop_on_error:
                raise
            return {"kind": "ParseError", "filename": filename, "message": str(exc)}

    @staticmethod
    def _resolve_relative(anchor: str, rel: str) -> Optional[str]:
        """Resolve *rel* path relative to the directory of *anchor*."""
        if not rel:
            return None
        base = os.path.dirname(anchor)
        return os.path.normpath(os.path.join(base, rel))
