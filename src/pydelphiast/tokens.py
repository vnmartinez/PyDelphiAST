"""Token types and Delphi 10 reserved word / directive tables."""

from __future__ import annotations

from enum import Enum, auto
from typing import Dict, FrozenSet


class TT(Enum):
    """Token type enumeration covering all Delphi 10 lexical elements."""

    # ── Literals ──────────────────────────────────────────────────────────
    INTEGER = auto()      # 42  $FF
    FLOAT = auto()        # 3.14  1e5
    STRING = auto()       # 'hello'
    CHAR = auto()         # #13  #$0D
    HEX = auto()          # $DEADBEEF (standalone, without alpha prefix)

    # ── Identifier ────────────────────────────────────────────────────────
    IDENT = auto()

    # ── True reserved words (cannot be used as identifiers) ───────────────
    AND = auto()
    ARRAY = auto()
    AS = auto()
    ASM = auto()
    BEGIN = auto()
    CASE = auto()
    CLASS = auto()
    CONST = auto()
    CONSTRUCTOR = auto()
    DESTRUCTOR = auto()
    DISPINTERFACE = auto()
    DIV = auto()
    DO = auto()
    DOWNTO = auto()
    ELSE = auto()
    END = auto()
    EXCEPT = auto()
    EXPORTS = auto()
    FILE = auto()
    FINALIZATION = auto()
    FINALLY = auto()
    FOR = auto()
    FUNCTION = auto()
    GOTO = auto()
    IF = auto()
    IMPLEMENTATION = auto()
    IN = auto()
    INHERITED = auto()
    INITIALIZATION = auto()
    INLINE = auto()
    INTERFACE = auto()
    IS = auto()
    LABEL = auto()
    LIBRARY = auto()
    MOD = auto()
    NIL = auto()
    NOT = auto()
    OBJECT = auto()
    OF = auto()
    ON = auto()
    OPERATOR = auto()
    OR = auto()
    OUT = auto()
    PACKED = auto()
    PROCEDURE = auto()
    PROGRAM = auto()
    PROPERTY = auto()
    RAISE = auto()
    RECORD = auto()
    REPEAT = auto()
    RESOURCESTRING = auto()
    SET = auto()
    SHL = auto()
    SHR = auto()
    STRING_KW = auto()    # 'string' keyword
    THEN = auto()
    THREADVAR = auto()
    TO = auto()
    TRY = auto()
    TYPE = auto()
    UNIT = auto()
    UNTIL = auto()
    USES = auto()
    VAR = auto()
    WHILE = auto()
    WITH = auto()
    XOR = auto()

    # ── Directives (context-sensitive – valid identifiers in most positions) ─
    D_ABSOLUTE = auto()
    D_ABSTRACT = auto()
    D_ASSEMBLER = auto()
    D_AUTOMATED = auto()
    D_CDECL = auto()
    D_CONTAINS = auto()
    D_DEFAULT = auto()
    D_DELAYED = auto()
    D_DEPRECATED = auto()
    D_DISPID = auto()
    D_DYNAMIC = auto()
    D_EXPERIMENTAL = auto()
    D_EXPORT = auto()
    D_EXTERNAL = auto()
    D_FAR = auto()
    D_FINAL = auto()
    D_FORWARD = auto()
    D_HELPER = auto()
    D_IMPLEMENTS = auto()
    D_INDEX = auto()
    D_LOCAL = auto()
    D_MESSAGE = auto()
    D_NAME = auto()
    D_NEAR = auto()
    D_NODEFAULT = auto()
    D_OVERLOAD = auto()
    D_OVERRIDE = auto()
    D_PACKAGE = auto()
    D_PASCAL = auto()
    D_PLATFORM = auto()
    D_PRIVATE = auto()
    D_PROTECTED = auto()
    D_PUBLIC = auto()
    D_PUBLISHED = auto()
    D_READ = auto()
    D_READONLY = auto()
    D_REFERENCE = auto()
    D_REGISTER = auto()
    D_REINTRODUCE = auto()
    D_REQUIRES = auto()
    D_RESIDENT = auto()
    D_SAFECALL = auto()
    D_SEALED = auto()
    D_STATIC = auto()
    D_STDCALL = auto()
    D_STORED = auto()
    D_STRICT = auto()
    D_UNSAFE = auto()
    D_VARARGS = auto()
    D_VIRTUAL = auto()
    D_WINAPI = auto()
    D_WRITE = auto()
    D_WRITEONLY = auto()

    # ── Operators / punctuation ────────────────────────────────────────────
    PLUS = auto()        # +
    MINUS = auto()       # -
    STAR = auto()        # *
    SLASH = auto()       # /
    ASSIGN = auto()      # :=
    EQ = auto()          # =
    NEQ = auto()         # <>
    LT = auto()          # <
    GT = auto()          # >
    LTE = auto()         # <=
    GTE = auto()         # >=
    AT = auto()          # @
    CARET = auto()       # ^
    DOT = auto()         # .
    DOTDOT = auto()      # ..
    COMMA = auto()       # ,
    SEMI = auto()        # ;
    COLON = auto()       # :
    LPAREN = auto()      # (
    RPAREN = auto()      # )
    LBRACKET = auto()    # [
    RBRACKET = auto()    # ]

    # ── Special ────────────────────────────────────────────────────────────
    COMPILER_DIR = auto()   # {$...}  or  (*$...*)
    EOF = auto()


# ---------------------------------------------------------------------------
# Reserved-word lookup tables
# ---------------------------------------------------------------------------

#: Strict reserved words – cannot be used as identifiers
RESERVED: Dict[str, TT] = {
    "and": TT.AND,
    "array": TT.ARRAY,
    "as": TT.AS,
    "asm": TT.ASM,
    "begin": TT.BEGIN,
    "case": TT.CASE,
    "class": TT.CLASS,
    "const": TT.CONST,
    "constructor": TT.CONSTRUCTOR,
    "destructor": TT.DESTRUCTOR,
    "dispinterface": TT.DISPINTERFACE,
    "div": TT.DIV,
    "do": TT.DO,
    "downto": TT.DOWNTO,
    "else": TT.ELSE,
    "end": TT.END,
    "except": TT.EXCEPT,
    "exports": TT.EXPORTS,
    "file": TT.FILE,
    "finalization": TT.FINALIZATION,
    "finally": TT.FINALLY,
    "for": TT.FOR,
    "function": TT.FUNCTION,
    "goto": TT.GOTO,
    "if": TT.IF,
    "implementation": TT.IMPLEMENTATION,
    "in": TT.IN,
    "inherited": TT.INHERITED,
    "initialization": TT.INITIALIZATION,
    "inline": TT.INLINE,
    "interface": TT.INTERFACE,
    "is": TT.IS,
    "label": TT.LABEL,
    "library": TT.LIBRARY,
    "mod": TT.MOD,
    "nil": TT.NIL,
    "not": TT.NOT,
    "object": TT.OBJECT,
    "of": TT.OF,
    "on": TT.ON,
    "operator": TT.OPERATOR,
    "or": TT.OR,
    "out": TT.OUT,
    "packed": TT.PACKED,
    "procedure": TT.PROCEDURE,
    "program": TT.PROGRAM,
    "property": TT.PROPERTY,
    "raise": TT.RAISE,
    "record": TT.RECORD,
    "repeat": TT.REPEAT,
    "resourcestring": TT.RESOURCESTRING,
    "set": TT.SET,
    "shl": TT.SHL,
    "shr": TT.SHR,
    "string": TT.STRING_KW,
    "then": TT.THEN,
    "threadvar": TT.THREADVAR,
    "to": TT.TO,
    "try": TT.TRY,
    "type": TT.TYPE,
    "unit": TT.UNIT,
    "until": TT.UNTIL,
    "uses": TT.USES,
    "var": TT.VAR,
    "while": TT.WHILE,
    "with": TT.WITH,
    "xor": TT.XOR,
}

#: Directives – context-sensitive; treated as identifiers in most positions
DIRECTIVES: Dict[str, TT] = {
    "absolute": TT.D_ABSOLUTE,
    "abstract": TT.D_ABSTRACT,
    "assembler": TT.D_ASSEMBLER,
    "automated": TT.D_AUTOMATED,
    "cdecl": TT.D_CDECL,
    "contains": TT.D_CONTAINS,
    "default": TT.D_DEFAULT,
    "delayed": TT.D_DELAYED,
    "deprecated": TT.D_DEPRECATED,
    "dispid": TT.D_DISPID,
    "dynamic": TT.D_DYNAMIC,
    "experimental": TT.D_EXPERIMENTAL,
    "export": TT.D_EXPORT,
    "external": TT.D_EXTERNAL,
    "far": TT.D_FAR,
    "final": TT.D_FINAL,
    "forward": TT.D_FORWARD,
    "helper": TT.D_HELPER,
    "implements": TT.D_IMPLEMENTS,
    "index": TT.D_INDEX,
    "local": TT.D_LOCAL,
    "message": TT.D_MESSAGE,
    "name": TT.D_NAME,
    "near": TT.D_NEAR,
    "nodefault": TT.D_NODEFAULT,
    "overload": TT.D_OVERLOAD,
    "override": TT.D_OVERRIDE,
    "package": TT.D_PACKAGE,
    "pascal": TT.D_PASCAL,
    "platform": TT.D_PLATFORM,
    "private": TT.D_PRIVATE,
    "protected": TT.D_PROTECTED,
    "public": TT.D_PUBLIC,
    "published": TT.D_PUBLISHED,
    "read": TT.D_READ,
    "readonly": TT.D_READONLY,
    "reference": TT.D_REFERENCE,
    "register": TT.D_REGISTER,
    "reintroduce": TT.D_REINTRODUCE,
    "requires": TT.D_REQUIRES,
    "resident": TT.D_RESIDENT,
    "safecall": TT.D_SAFECALL,
    "sealed": TT.D_SEALED,
    "static": TT.D_STATIC,
    "stdcall": TT.D_STDCALL,
    "stored": TT.D_STORED,
    "strict": TT.D_STRICT,
    "unsafe": TT.D_UNSAFE,
    "varargs": TT.D_VARARGS,
    "virtual": TT.D_VIRTUAL,
    "winapi": TT.D_WINAPI,
    "write": TT.D_WRITE,
    "writeonly": TT.D_WRITEONLY,
}

#: Combined lookup (reserved + directives)
ALL_KEYWORDS: Dict[str, TT] = {**RESERVED, **DIRECTIVES}

#: Set of all directive TT values (for quick membership test)
DIRECTIVE_TYPES: FrozenSet[TT] = frozenset(DIRECTIVES.values())

#: Calling-convention directives
CALLING_CONVENTIONS: FrozenSet[TT] = frozenset({
    TT.D_CDECL, TT.D_PASCAL, TT.D_REGISTER, TT.D_SAFECALL,
    TT.D_STDCALL, TT.D_WINAPI, TT.D_EXPORT, TT.D_FAR, TT.D_NEAR,
    TT.D_ASSEMBLER, TT.D_LOCAL,
})

#: Method / procedure directives
ROUTINE_DIRECTIVES: FrozenSet[TT] = frozenset({
    TT.D_ABSTRACT, TT.D_DYNAMIC, TT.D_FINAL, TT.D_FORWARD,
    TT.D_MESSAGE, TT.D_OVERLOAD, TT.D_OVERRIDE,
    TT.D_REINTRODUCE, TT.D_STATIC, TT.D_VIRTUAL, TT.D_VARARGS,
    TT.D_DEPRECATED, TT.D_EXPERIMENTAL, TT.D_PLATFORM, TT.D_UNSAFE,
    TT.D_DISPID, TT.D_DELAYED,
    TT.INLINE,  # 'inline' is a true reserved word but also a directive
}) | CALLING_CONVENTIONS

#: Visibility section starters
VISIBILITY_TYPES: FrozenSet[TT] = frozenset({
    TT.D_PRIVATE, TT.D_PROTECTED, TT.D_PUBLIC, TT.D_PUBLISHED, TT.D_AUTOMATED,
})
