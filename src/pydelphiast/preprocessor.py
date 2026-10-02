"""Delphi conditional compilation preprocessor.

Handles compiler directives ($IFDEF, $IFNDEF, $IF, $ELSE, $ELSEIF, $ENDIF, $IFEND,
$DEFINE, $UNDEF) on a flat list of tokens, filtering out inactive branches and
handling build-break assertions gracefully.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set, Tuple

from .lexer import Token
from .tokens import TT

#: Default conditional defines for Delphi 10 (Win32 target)
DEFAULT_DEFINES: frozenset[str] = frozenset({
    "WIN32",
    "MSWINDOWS",
    "CPU386",
    "CPU32",
    "CONDITIONALEXPRESSIONS",
    "DCC",
    "VER300",
})


def parse_directive(val: str) -> Tuple[Optional[str], str]:
    """Parse compiler directive text. Returns (cmd, arg) in uppercase, or (None, '')."""
    s = val.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1].strip()
    elif s.startswith("(*") and s.endswith("*)"):
        s = s[2:-2].strip()
    else:
        return None, ""

    if not s.startswith("$"):
        return None, ""
    s = s[1:].strip()

    parts = s.split(None, 1)
    if not parts:
        return None, ""
    cmd = parts[0].upper()
    arg = parts[1].strip() if len(parts) > 1 else ""
    return cmd, arg


def eval_simple_condition(expr: str, defines: Set[str]) -> bool:
    """Evaluate simple Delphi condition expression like DEFINED(FOO), NOT DEFINED(FOO), FOO."""
    s = expr.strip()
    is_not = False
    if s.upper().startswith("NOT "):
        is_not = True
        s = s[4:].strip()

    m = re.match(r"(?i)^DEFINED\s*\(\s*([A-Za-z0-9_]+)\s*\)$", s)
    if m:
        sym = m.group(1).upper()
        res = sym in defines
        return not res if is_not else res

    sym = s.split()[0].upper() if s else ""
    res = sym in defines
    return not res if is_not else res


def is_build_break_ahead(tokens: List[Token], start_idx: int) -> bool:
    """Check if the conditional block starting after start_idx contains an exclamation mark or error idiom."""
    depth = 1
    idx = start_idx + 1
    while idx < len(tokens):
        t = tokens[idx]
        if t.type == TT.COMPILER_DIR:
            cmd, _ = parse_directive(t.value)
            if cmd in ("IFDEF", "IFNDEF", "IF"):
                depth += 1
            elif cmd in ("ENDIF", "IFEND"):
                depth -= 1
                if depth == 0:
                    break
            elif cmd in ("ELSE", "ELSEIF") and depth == 1:
                break
        elif depth == 1 and (t.type == TT.EXCLAMATION or t.value == "!"):
            return True
        idx += 1
    return False


def preprocess_tokens(
    tokens: List[Token],
    defines: Optional[Iterable[str]] = None,
) -> List[Token]:
    """Filter *tokens* by evaluating Delphi conditional compilation directives.

    Tokens inside inactive branches are removed. If an ``{$IFNDEF SYMBOL}`` block
    contains an intentional compiler-break message (ending with ``!``), ``SYMBOL``
    is inferred as a required define for this project and the break block is skipped.
    """
    cur_defines: Set[str] = set(DEFAULT_DEFINES)
    if defines:
        cur_defines.update(d.upper() for d in defines if d)

    stack: List[List[bool]] = []  # each entry is [active_bool, branch_matched_bool]
    out: List[Token] = []

    for i, tok in enumerate(tokens):
        if tok.type == TT.COMPILER_DIR:
            cmd, arg = parse_directive(tok.value)

            if cmd in ("IFDEF", "IFNDEF", "IF"):
                parent_active = stack[-1][0] if stack else True
                if cmd == "IFDEF":
                    sym = arg.split()[0].upper() if arg else ""
                    cond = sym in cur_defines
                elif cmd == "IFNDEF":
                    sym = arg.split()[0].upper() if arg else ""
                    if sym not in cur_defines and is_build_break_ahead(tokens, i):
                        # Required project define! Auto-define it and skip the break message
                        cur_defines.add(sym)
                        cond = False
                    else:
                        cond = sym not in cur_defines
                else:  # IF
                    cond = eval_simple_condition(arg, cur_defines)

                active = parent_active and cond
                stack.append([active, cond if parent_active else True])
                continue

            elif cmd == "ELSEIF":
                if stack:
                    parent_active = stack[-2][0] if len(stack) > 1 else True
                    already_matched = stack[-1][1]
                    cond = eval_simple_condition(arg, cur_defines)
                    active = parent_active and (not already_matched) and cond
                    stack[-1][0] = active
                    if cond and parent_active:
                        stack[-1][1] = True
                continue

            elif cmd == "ELSE":
                if stack:
                    parent_active = stack[-2][0] if len(stack) > 1 else True
                    already_matched = stack[-1][1]
                    active = parent_active and (not already_matched)
                    stack[-1][0] = active
                    stack[-1][1] = True
                continue

            elif cmd in ("ENDIF", "IFEND"):
                if stack:
                    stack.pop()
                continue

            elif cmd == "DEFINE":
                if not stack or stack[-1][0]:
                    sym = arg.split()[0].upper() if arg else ""
                    if sym:
                        cur_defines.add(sym)
                continue

            elif cmd == "UNDEF":
                if not stack or stack[-1][0]:
                    sym = arg.split()[0].upper() if arg else ""
                    if sym:
                        cur_defines.discard(sym)
                continue

        # If we're inside an active branch (or at root level), keep the token
        if not stack or stack[-1][0]:
            out.append(tok)

    return out
