"""Error types for PyDelphiAST."""

from __future__ import annotations


class DelphiError(Exception):
    """Base error for all parser/lexer errors."""

    def __init__(self, message: str, line: int = 0, column: int = 0, filename: str = "") -> None:
        loc = f"{filename}:{line}:{column}" if filename else f"line {line}, col {column}"
        super().__init__(f"{message} [{loc}]")
        self.message = message
        self.line = line
        self.column = column
        self.filename = filename


class LexerError(DelphiError):
    """Raised when the lexer encounters an unexpected character or unterminated token."""


class ParseError(DelphiError):
    """Raised when the parser encounters unexpected tokens."""
