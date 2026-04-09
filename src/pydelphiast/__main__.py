"""Command-line interface for PyDelphiAST.

Usage examples::

    # Parse a single file, print JSON to stdout
    python -m pydelphiast MyUnit.pas

    # Parse a whole project
    python -m pydelphiast MyApp.groupproj

    # Save output to a file
    python -m pydelphiast MyApp.groupproj -o ast.json

    # Pretty-print with custom indentation
    python -m pydelphiast MyUnit.pas --indent 4

    # Parse multiple files at once
    python -m pydelphiast Unit1.pas Unit2.pas Form1.dfm
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pydelphiast as pda


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pydelphiast",
        description="Parse Delphi source files and output an AST as JSON.",
    )
    p.add_argument(
        "files",
        metavar="FILE",
        nargs="+",
        help="One or more .pas / .dpr / .dfm / .groupproj / .dproj files",
    )
    p.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Write JSON output to this file instead of stdout",
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        metavar="N",
        help="JSON indentation (default: 2; use 0 for compact)",
    )
    p.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="Source file encoding (default: utf-8-sig)",
    )
    p.add_argument(
        "--no-forms",
        action="store_true",
        help="Do not auto-load companion .dfm files",
    )
    p.add_argument(
        "--project",
        action="store_true",
        help="Treat the first FILE as a project root and follow the hierarchy",
    )
    p.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort on the first parse error instead of inserting error nodes",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"pydelphiast {pda.__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    include_forms = not args.no_forms
    indent = args.indent if args.indent > 0 else None

    _PROJECT_EXTS = {".dpr", ".dproj", ".groupproj"}

    results: list[dict] = []

    for path in args.files:
        if not Path(path).exists():
            print(f"Warning: file not found: {path}", file=sys.stderr)
            continue

        is_project = args.project or Path(path).suffix.lower() in _PROJECT_EXTS
        try:
            if is_project:
                ast = pda.parse_project(
                    path,
                    encoding=args.encoding,
                    include_forms=include_forms,
                    stop_on_error=args.stop_on_error,
                )
            else:
                ast = pda.parse_file(
                    path,
                    encoding=args.encoding,
                    include_forms=include_forms,
                )
            results.append(ast)
        except Exception as exc:
            if args.stop_on_error:
                print(f"Error parsing {path}: {exc}", file=sys.stderr)
                return 1
            results.append({
                "kind": "ParseError",
                "filename": path,
                "message": str(exc),
            })

    output = results[0] if len(results) == 1 else results
    text = json.dumps(output, indent=indent, ensure_ascii=False, default=str)

    if args.output:
        out_path = Path(args.output)
    else:
        # Default: write <first-input-stem>.json next to the input file
        stem = Path(args.files[0]).stem
        out_path = Path(args.files[0]).parent / f"{stem}.json"

    out_path.write_text(text, encoding="utf-8")
    print(f"AST written to {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
