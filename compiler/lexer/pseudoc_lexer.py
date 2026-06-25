"""
compiler/lexer/pseudoc_lexer.py
Lexer for the 8m pseudo-C DSL (8mSpec_0821.c).
Tokenises the source into a list of Token objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Dict, List, Optional


# ======================================================================
# TokenType
# ======================================================================

class TokenType(IntEnum):
    """All token types for the 8m pseudo-C DSL."""

    # -- keywords --
    PROCESS   = auto()
    VOID      = auto()
    WHILE     = auto()
    FOR       = auto()
    SWITCH    = auto()
    CASE      = auto()
    BREAK     = auto()
    DEFAULT   = auto()
    IF        = auto()
    ELSE      = auto()
    RETURN    = auto()
    STRUCT    = auto()
    BOOL      = auto()
    TABLE     = auto()
    DELAY     = auto()
    ENQUEUE   = auto()
    REPLACE   = auto()
    INSERT    = auto()
    REMOVE    = auto()
    UPDATE    = auto()
    SEND      = auto()
    USING     = auto()
    AT        = auto()
    TO        = auto()
    AFTER     = auto()

    # -- type keyword --
    UINT_TYPE = auto()

    # -- literals --
    IDENTIFIER  = auto()
    INT_LITERAL = auto()
    HEX_LITERAL = auto()
    BIN_LITERAL = auto()

    # -- operators / delimiters --
    ASSIGN       = auto()  # =
    EQ           = auto()  # ==
    NE           = auto()  # !=
    LOGICAL_AND  = auto()  # &&
    LOGICAL_OR   = auto()  # ||
    LOGICAL_NOT  = auto()  # !
    BITWISE_AND  = auto()  # &
    BITWISE_OR   = auto()  # |
    BITWISE_NOT  = auto()  # ~
    BITWISE_XOR  = auto()  # ^
    SHIFT_LEFT   = auto()  # <<
    SHIFT_RIGHT  = auto()  # >>
    LT           = auto()  # <
    GT           = auto()  # >
    LE           = auto()  # <=
    GE           = auto()  # >=
    PLUS         = auto()  # +
    MINUS        = auto()  # -
    STAR         = auto()  # *
    SLASH        = auto()  # /
    MOD          = auto()  # %
    INC          = auto()  # ++
    DEC          = auto()  # --
    ADD_ASSIGN   = auto()  # +=
    SUB_ASSIGN   = auto()  # -=
    AND_ASSIGN   = auto()  # &=
    OR_ASSIGN    = auto()  # |=
    LBRACE       = auto()  # {
    RBRACE       = auto()  # }
    LBRACKET     = auto()  # [
    RBRACKET     = auto()  # ]
    LPAREN       = auto()  # (
    RPAREN       = auto()  # )
    DOT          = auto()  # .
    COLON        = auto()  # :
    SEMICOLON    = auto()  # ;
    COMMA        = auto()  # ,
    QUESTION     = auto()  # ?
    RANGE        = auto()  # ~  (context-sensitive: ~ between numbers)
    ELLIPSIS     = auto()  # ...

    # -- special --
    NEWLINE = auto()
    EOF     = auto()


# ======================================================================
# Keyword → TokenType mapping
# ======================================================================

_KEYWORDS: Dict[str, TokenType] = {
    "process": TokenType.PROCESS,
    "void":    TokenType.VOID,
    "while":   TokenType.WHILE,
    "for":     TokenType.FOR,
    "switch":  TokenType.SWITCH,
    "case":    TokenType.CASE,
    "break":   TokenType.BREAK,
    "default": TokenType.DEFAULT,
    "if":      TokenType.IF,
    "else":    TokenType.ELSE,
    "return":  TokenType.RETURN,
    "struct":  TokenType.STRUCT,
    "bool":    TokenType.BOOL,
    "table":   TokenType.TABLE,
    "delay":   TokenType.DELAY,
    "enqueue": TokenType.ENQUEUE,
    "replace": TokenType.REPLACE,
    "insert":  TokenType.INSERT,
    "remove":  TokenType.REMOVE,
    "update":  TokenType.UPDATE,
    "send":    TokenType.SEND,
    "using":   TokenType.USING,
    "at":      TokenType.AT,
    "to":      TokenType.TO,
    "after":   TokenType.AFTER,
}


# ======================================================================
# Token
# ======================================================================

@dataclass
class Token:
    """A single lexical token."""
    type: TokenType
    value: str
    line: int
    column: int


# ======================================================================
# Two-char operator map  (lookahead string → (length, TokenType))
# ======================================================================

_TWO_CHAR_OPS: Dict[str, TokenType] = {
    "==": TokenType.EQ,
    "!=": TokenType.NE,
    "&&": TokenType.LOGICAL_AND,
    "||": TokenType.LOGICAL_OR,
    "<<": TokenType.SHIFT_LEFT,
    ">>": TokenType.SHIFT_RIGHT,
    "<=": TokenType.LE,
    ">=": TokenType.GE,
    "++": TokenType.INC,
    "--": TokenType.DEC,
    "+=": TokenType.ADD_ASSIGN,
    "-=": TokenType.SUB_ASSIGN,
    "&=": TokenType.AND_ASSIGN,
    "|=": TokenType.OR_ASSIGN,
}

# Single-char operator map
_ONE_CHAR_OPS: Dict[str, TokenType] = {
    "=": TokenType.ASSIGN,
    "!": TokenType.LOGICAL_NOT,
    "&": TokenType.BITWISE_AND,
    "|": TokenType.BITWISE_OR,
    "~": TokenType.RANGE,          # ~ as in 0x11~1F
    "^": TokenType.BITWISE_XOR,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.MOD,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ".": TokenType.DOT,
    ":": TokenType.COLON,
    ";": TokenType.SEMICOLON,
    ",": TokenType.COMMA,
    "?": TokenType.QUESTION,
}


# ======================================================================
# PseudoCLexer
# ======================================================================

class PseudoCLexer:
    """
    Lexer for the 8m pseudo-C DSL (8mSpec_0821.c).

    Usage:
        lexer = PseudoCLexer(source_text)
        tokens = lexer.tokenize()   # → List[Token]  (ends with EOF)
    """

    def __init__(self, source: str) -> None:
        self.source: str = source
        self.pos: int = 0
        self.line: int = 1
        self.column: int = 1

    # ------------------------------------------------------------------
    # Character-level helpers
    # ------------------------------------------------------------------

    def _peek(self, offset: int = 0) -> str:
        """Return character at pos+offset, or '' if past end."""
        idx = self.pos + offset
        if idx < len(self.source):
            return self.source[idx]
        return ""

    def _advance(self, n: int = 1) -> None:
        """Move pos forward by n characters, updating column."""
        for _ in range(n):
            if self.pos < len(self.source) and self.source[self.pos] == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1
            self.pos += 1

    def _current(self) -> str:
        """Return character at current pos, or '' if EOF."""
        return self._peek(0)

    def _make_token(self, ttype: TokenType, value: str, line: int, col: int) -> Token:
        return Token(type=ttype, value=value, line=line, column=col)

    # ------------------------------------------------------------------
    # Whitespace / newline / comment
    # ------------------------------------------------------------------

    def _skip_whitespace_and_comments(self) -> Optional[Token]:
        """
        Consume whitespace, comments, and newlines.
        Returns a NEWLINE token for each physical newline, or None.
        """
        while self.pos < len(self.source):
            ch = self._current()

            # -- space / tab / carriage-return --
            if ch in (" ", "\t", "\r"):
                self._advance()
                continue

            # -- newline → emit NEWLINE token --
            if ch == "\n":
                line = self.line
                col = self.column
                self._advance()  # advances past \n, sets line++
                return self._make_token(TokenType.NEWLINE, "\\n", line, col)

            # -- // line comment --
            if ch == "/" and self._peek(1) == "/":
                self._advance(2)
                while self.pos < len(self.source) and self._current() != "\n":
                    self._advance()
                continue

            # -- /* block comment --
            if ch == "/" and self._peek(1) == "*":
                self._advance(2)
                while self.pos < len(self.source):
                    if self._current() == "*" and self._peek(1) == "/":
                        self._advance(2)
                        break
                    self._advance()
                continue

            # Non-whitespace character → stop here
            break

        return None

    # ------------------------------------------------------------------
    # Number / identifier scanning
    # ------------------------------------------------------------------

    def _try_scan_number(self) -> Optional[Token]:
        """
        Attempt to scan a numeric literal: BIN_LITERAL, HEX_LITERAL, or INT_LITERAL.

        Detection order:
          1. N'b...  or  N'B... → BIN_LITERAL
          2. 0x...   or  0X...  → HEX_LITERAL
          3. [0-9]...           → INT_LITERAL (may be prefix of cases above)
        """
        start_pos = self.pos
        line = self.line
        col = self.column

        ch = self._current()

        # -- Try N'b / N'B / N'h / N'H (Verilog literal) --
        # Scan digits first
        if ch.isdigit():
            saved_pos = self.pos
            saved_line = self.line
            saved_col = self.column
            digits = ""
            while self._current().isdigit():
                digits += self._current()
                self._advance()
            if self._current() == "'" and self._peek(1) in ("b", "B", "h", "H"):
                radix_ch = self._peek(1).lower()  # 'b' or 'h'
                self._advance(2)  # skip 'b / 'h
                lit_body = ""
                if radix_ch == "b":
                    while self.pos < len(self.source) and (
                        self._current() in ("0", "1", "_", "?")
                    ):
                        lit_body += self._current()
                        self._advance()
                else:  # hex
                    while self.pos < len(self.source) and (
                        self._current().isalnum() or self._current() == "_"
                    ):
                        lit_body += self._current()
                        self._advance()
                value = digits + "'" + ("b" if radix_ch == "b" else "h") + lit_body
                return self._make_token(
                    TokenType.BIN_LITERAL, value, line, col
                )
            # Not N'b / N'h → unwind and fall through
            self.pos = saved_pos
            self.line = saved_line
            self.column = saved_col

        # -- Try 0x / 0X (hex literal) --
        if ch == "0" and self._peek(1) in ("x", "X"):
            self._advance(2)
            hex_body = ""
            while self.pos < len(self.source) and (
                self._current().isalnum() or self._current() == "_"
            ):
                hex_body += self._current()
                self._advance()
            value = "0x" + hex_body
            return self._make_token(TokenType.HEX_LITERAL, value, line, col)

        # -- Decimal integer (or bare hex like 1f / FF) --
        if ch.isdigit():
            int_body = ""
            while self._current().isdigit():
                int_body += self._current()
                self._advance()
            # Check for bare hex suffix: digits followed by hex letters (no 0x prefix)
            # e.g., 1f, 0FF, ABC (in case labels)
            if self._current().lower() in "abcdef":
                hex_body = int_body
                while self.pos < len(self.source) and (
                    self._current().isalnum() or self._current() == "_"
                ):
                    hex_body += self._current()
                    self._advance()
                value = "0x" + hex_body
                return self._make_token(TokenType.HEX_LITERAL, value, line, col)
            return self._make_token(TokenType.INT_LITERAL, int_body, line, col)

        # Restore position if nothing matched
        self.pos = start_pos
        return None

    def _try_scan_identifier_or_keyword(self) -> Optional[Token]:
        """
        Scan [a-zA-Z_][a-zA-Z0-9_]*.
        Returns a keyword Token, UINT_TYPE Token, or IDENTIFIER Token.
        """
        ch = self._current()
        if not (ch.isalpha() or ch == "_"):
            return None

        line = self.line
        col = self.column
        ident = ""
        while self.pos < len(self.source) and (
            self._current().isalnum() or self._current() == "_"
        ):
            ident += self._current()
            self._advance()

        # -- uintN pattern → UINT_TYPE --
        if ident.startswith("uint"):
            suffix = ident[4:]
            if suffix.isdigit():
                return self._make_token(TokenType.UINT_TYPE, ident, line, col)

        # -- keyword lookup --
        lower = ident.lower()
        if lower in _KEYWORDS:
            return self._make_token(_KEYWORDS[lower], ident, line, col)

        return self._make_token(TokenType.IDENTIFIER, ident, line, col)

    # ------------------------------------------------------------------
    # Operator / delimiter scanning
    # ------------------------------------------------------------------

    def _try_scan_operator(self) -> Optional[Token]:
        """Try to match a 2-char operator, then 3-char ellipsis, then 1-char."""
        line = self.line
        col = self.column
        ch = self._current()

        if not ch:
            return None

        # -- 2-char operators --
        two = ch + self._peek(1)
        if two in _TWO_CHAR_OPS:
            self._advance(2)
            return self._make_token(_TWO_CHAR_OPS[two], two, line, col)

        # -- 3-char ellipsis  ... --
        if ch == "." and self._peek(1) == "." and self._peek(2) == ".":
            self._advance(3)
            return self._make_token(TokenType.ELLIPSIS, "...", line, col)

        # -- 1-char operators --
        if ch in _ONE_CHAR_OPS:
            self._advance(1)
            return self._make_token(_ONE_CHAR_OPS[ch], ch, line, col)

        return None

    # ------------------------------------------------------------------
    # Main tokenize
    # ------------------------------------------------------------------

    def tokenize(self) -> List[Token]:
        """
        Scan the full source and return the complete Token list.

        Returns:
            List[Token] ending with a single EOF token.
        """
        tokens: List[Token] = []

        while self.pos < len(self.source):
            line = self.line
            col = self.column

            # -- whitespace / comments / newlines --
            nl_token = self._skip_whitespace_and_comments()
            if nl_token is not None:
                tokens.append(nl_token)
                continue

            # -- numeric literal --
            num_token = self._try_scan_number()
            if num_token is not None:
                tokens.append(num_token)
                continue

            # -- identifier / keyword --
            ident_token = self._try_scan_identifier_or_keyword()
            if ident_token is not None:
                tokens.append(ident_token)
                continue

            # -- operator / delimiter --
            op_token = self._try_scan_operator()
            if op_token is not None:
                tokens.append(op_token)
                continue

            # -- unrecognised character --
            ch = self._current()
            raise SyntaxError(
                f"Unrecognised character {ch!r} at line {self.line}, column {self.column}"
            )

        # -- trailing EOF --
        tokens.append(
            self._make_token(TokenType.EOF, "", self.line, self.column)
        )
        return tokens
