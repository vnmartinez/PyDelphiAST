"""Parser for Delphi .groupproj and .dproj (MSBuild XML) files.

Produces lightweight AST dicts.  For ``.groupproj``::

    {
      "kind": "GroupProject",
      "projects": [
        {"kind": "ProjectRef", "path": "Foo.dproj", "config": [...]}
      ]
    }

For ``.dproj``::

    {
      "kind": "DprojProject",
      "mainSource": "Foo.dpr",  # path to .dpr file
      "platform": "Win32",
      "config": "Debug",
      "units": [...],           # DCCReference items
      "forms": [...],           # DCCReference items that have dfm
    }
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from ..errors import ParseError


# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------

# MSBuild namespace used in .dproj / .groupproj
_MSB_NS = "http://schemas.microsoft.com/developer/msbuild/2003"
_NS = {"m": _MSB_NS}


def _tag(local: str) -> str:
    return f"{{{_MSB_NS}}}{local}"


def _find(elem: ET.Element, path: str) -> Optional[ET.Element]:
    return elem.find(path, _NS)


def _findall(elem: ET.Element, path: str) -> List[ET.Element]:
    return elem.findall(path, _NS)


def _text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    return (elem.text or "").strip()


# ---------------------------------------------------------------------------
# .groupproj parser
# ---------------------------------------------------------------------------

def parse_groupproj(src: str, filename: str = "<unknown>") -> dict:
    """Parse a ``.groupproj`` XML source string."""
    try:
        root = ET.fromstring(src)
    except ET.ParseError as exc:
        raise ParseError(f"XML parse error: {exc}", filename=filename) from exc

    projects: List[dict] = []
    # <ItemGroup><Projects Include="..." /></ItemGroup>
    for item_group in _findall(root, "m:ItemGroup"):
        for proj in _findall(item_group, "m:Projects"):
            path = proj.attrib.get("Include", "")
            deps: List[str] = []
            deps_elem = _find(proj, "m:Dependencies")
            if deps_elem is not None:
                for dep in _findall(deps_elem, "m:Projects"):
                    deps.append(dep.attrib.get("Include", ""))

            projects.append({
                "kind": "ProjectRef",
                "path": path,
                "dependencies": deps,
            })

    return {
        "kind": "GroupProject",
        "filename": filename,
        "projects": projects,
    }


# ---------------------------------------------------------------------------
# .dproj parser
# ---------------------------------------------------------------------------

def parse_dproj(src: str, filename: str = "<unknown>") -> dict:
    """Parse a ``.dproj`` MSBuild XML source string."""
    try:
        root = ET.fromstring(src)
    except ET.ParseError as exc:
        raise ParseError(f"XML parse error: {exc}", filename=filename) from exc

    # ── Main source (.dpr path) ─────────────────────────────────────────
    main_source = ""
    main_source_elem = _find(root, "m:PropertyGroup/m:MainSource")
    if main_source_elem is not None:
        main_source = _text(main_source_elem)
    if not main_source:
        # Try to infer from filename
        base = os.path.splitext(os.path.basename(filename))[0]
        main_source = base + ".dpr"

    # ── Platform / config ───────────────────────────────────────────────
    platform = ""
    config = ""
    for pg in _findall(root, "m:PropertyGroup"):
        cond = pg.attrib.get("Condition", "")
        if "Debug" in cond:
            config = "Debug"
        elif "Release" in cond:
            config = "Release"
        p = _find(pg, "m:Platform")
        if p is not None:
            platform = _text(p)
        c = _find(pg, "m:Config")
        if c is not None and not config:
            config = _text(c)

    # ── Referenced units / forms ────────────────────────────────────────
    units: List[dict] = []
    forms: List[dict] = []

    for item_group in _findall(root, "m:ItemGroup"):
        for ref in _findall(item_group, "m:DCCReference"):
            inc = ref.attrib.get("Include", "")
            form_name = _text(_find(ref, "m:FormName"))
            entry: dict = {"path": inc}
            if form_name:
                entry["formName"] = form_name
                forms.append(entry)
            else:
                units.append(entry)

    return {
        "kind": "DprojProject",
        "filename": filename,
        "mainSource": main_source,
        "platform": platform,
        "config": config,
        "units": units,
        "forms": forms,
    }
