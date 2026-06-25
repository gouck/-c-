"""
compiler/parser/pseudoc_parser.py
Recursive-descent parser for the 8m pseudo-C DSL (8mSpec_0821.c).
Converts Token list → PseudoCModel AST.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union

from compiler.lexer.pseudoc_lexer import Token, TokenType
from compiler.parser.ast_nodes import (
    # types
    BitVectorType, BoolType, StructType, ArrayType, Type,
    # expressions
    IdentifierExpr, IntLiteral, BinLiteral, HexLiteral,
    BinaryOpExpr, UnaryOpExpr, FieldAccessExpr, BitSliceExpr,
    BitIndexExpr, FieldIndexExpr, CompositeFieldExpr,
    ConcatExpr, FunctionCallExpr, MaxMinExpr, RangeExpr, CompoundExpr,
    Expr,
    # statements
    CompoundStmt, WhileStmt, ForStmt, IfStmt, SwitchStmt, CaseStmt,
    AssignStmt, CompoundAssignStmt, IncDecStmt,
    TableReadStmt, TableWriteStmt, ExprStmt, VarDeclStmt,
    DelayStmt, EnqueueStmt, ReplaceStmt, InsertStmt, RemoveStmt,
    SendStmt, ReturnStmt, BreakStmt,
    Stmt,
    # top-level
    GlobalVarDecl, StructDef, FieldDecl, ParamDecl,
    ProcessDef, FunctionDef, PseudoCModel,
)


# ======================================================================
# ParseError
# ======================================================================

class ParseError(Exception):
    """Error raised during parsing, with source location."""

    def __init__(self, message: str, token: Optional[Token] = None) -> None:
        if token is not None:
            loc = f" at line {token.line}, column {token.column}"
            near = f" near {token.value!r}"
        else:
            loc = ""
            near = ""
        super().__init__(f"ParseError{loc}{near}: {message}")


# ======================================================================
# Operator precedence table (higher int = tighter binding)
# ======================================================================

_PRECEDENCE: Dict[TokenType, int] = {
    # level 2  – ternary
    TokenType.QUESTION: 2,
    # level 3  – logical or
    TokenType.LOGICAL_OR: 3,
    # level 4  – logical and
    TokenType.LOGICAL_AND: 4,
    # level 5  – bitwise or
    TokenType.BITWISE_OR: 5,
    # level 6  – bitwise xor
    TokenType.BITWISE_XOR: 6,
    # level 7  – bitwise and
    TokenType.BITWISE_AND: 7,
    # level 8  – equality
    TokenType.EQ: 8,
    TokenType.NE: 8,
    # level 9  – comparison
    TokenType.LT: 9,
    TokenType.GT: 9,
    TokenType.LE: 9,
    TokenType.GE: 9,
    # level 10 – shift
    TokenType.SHIFT_LEFT: 10,
    TokenType.SHIFT_RIGHT: 10,
    # level 11 – additive
    TokenType.PLUS: 11,
    TokenType.MINUS: 11,
    # level 12 – multiplicative
    TokenType.STAR: 12,
    TokenType.SLASH: 12,
    TokenType.MOD: 12,
}

# Tokens that can appear as prefix unary operators
_UNARY_PREFIX: Dict[TokenType, str] = {
    TokenType.LOGICAL_NOT: "!",
    TokenType.RANGE: "~",          # also used as bitwise-not
    TokenType.MINUS: "-",
    TokenType.PLUS: "+",
}

# Compound-assign token → stripped operator string
_COMPOUND_ASSIGN_OPS: Dict[TokenType, str] = {
    TokenType.ADD_ASSIGN: "+=",
    TokenType.SUB_ASSIGN: "-=",
    TokenType.AND_ASSIGN: "&=",
    TokenType.OR_ASSIGN: "|=",
}


# ======================================================================
# PseudoCParser
# ======================================================================

class PseudoCParser:
    """
    Recursive-descent parser for the 8m pseudo-C DSL.

    Usage:
        parser = PseudoCParser(tokens)
        model = parser.parse()   # → PseudoCModel
    """

    def __init__(self, tokens: List[Token]) -> None:
        self.tokens: List[Token] = tokens
        self.pos: int = 0
        self._in_switch: bool = False  # context flag for case labels

    # ==================================================================
    # Token helpers
    # ==================================================================

    def _peek(self) -> Token:
        """Return current token without consuming."""
        return self.tokens[self.pos]

    def _peek_type(self) -> TokenType:
        return self._peek().type

    def _advance(self) -> Token:
        """Consume and return current token."""
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def _check(self, ttype: TokenType) -> bool:
        """True if current token matches ttype."""
        return not self._eof() and self._peek_type() == ttype

    def _match(self, ttype: TokenType) -> bool:
        """If current matches ttype, consume and return True."""
        if self._check(ttype):
            self._advance()
            return True
        return False

    def _expect(self, ttype: TokenType) -> Token:
        """Consume token of ttype or raise ParseError."""
        if self._check(ttype):
            return self._advance()
        # lenient: treat NEWLINE / RBRACE / EOF / start-of-next-stmt as implicit semicolon
        if ttype == TokenType.SEMICOLON:
            if (self._check(TokenType.NEWLINE) or
                self._check(TokenType.RBRACE) or
                self._eof() or
                self._peek_type() in (TokenType.IDENTIFIER, TokenType.IF,
                    TokenType.WHILE, TokenType.FOR, TokenType.SWITCH,
                    TokenType.CASE, TokenType.DEFAULT, TokenType.RETURN,
                    TokenType.BREAK, TokenType.DELAY, TokenType.REPLACE,
                    TokenType.INSERT, TokenType.REMOVE, TokenType.SEND,
                    TokenType.ENQUEUE, TokenType.UPDATE, TokenType.PROCESS,
                    TokenType.VOID, TokenType.UINT_TYPE, TokenType.STRUCT,
                    TokenType.LBRACE, TokenType.INC, TokenType.DEC)):
                return Token(ttype, ";", self._peek().line, self._peek().column)
        actual = self._peek()
        raise ParseError(
            f"Expected {ttype.name}, got {actual.type.name}",
            actual,
        )

    def _eof(self) -> bool:
        return self.pos >= len(self.tokens) or self._peek_type() == TokenType.EOF

    def _skip_newlines(self) -> None:
        """Skip over NEWLINE tokens (used between statements)."""
        while self._check(TokenType.NEWLINE):
            self._advance()

    # ==================================================================
    # parse() – top-level entry
    # ==================================================================

    def parse(self) -> PseudoCModel:
        """
        Parse the token stream into a PseudoCModel.

        grammar:
            translation_unit → (global_decl | struct_def | process_def | function_def)*
        """
        processes: List[ProcessDef] = []
        functions: List[FunctionDef] = []
        globals: List[GlobalVarDecl] = []
        structs: List[StructDef] = []

        while not self._eof():
            self._skip_newlines()
            if self._eof():
                break

            tt = self._peek_type()

            if tt == TokenType.UINT_TYPE or tt == TokenType.BOOL:
                # global variable declaration
                g = self._parse_global_var()
                if g is not None:
                    globals.append(g)
            elif tt == TokenType.STRUCT:
                structs.append(self._parse_struct())
            elif tt == TokenType.PROCESS:
                processes.append(self._parse_process())
            elif tt == TokenType.VOID or tt == TokenType.IDENTIFIER:
                # function (void name / type name) or process-like
                # peek ahead to distinguish
                if self._try_parse_function():
                    functions.append(self._parse_function())
                else:
                    # must be a process (process keyword missing? skip)
                    raise ParseError("Unexpected token at top level", self._peek())
            else:
                raise ParseError(
                    f"Unexpected token at top level: {tt.name}",
                    self._peek(),
                )

        return PseudoCModel(
            name="8mSpec",
            processes=processes,
            functions=functions,
        )

    def _try_parse_function(self) -> bool:
        """Peek ahead: is this a function definition (void name (...)? """
        saved = self.pos
        try:
            if self._check(TokenType.VOID):
                self._advance()
            elif self._check(TokenType.IDENTIFIER):
                self._advance()
            else:
                return False
            # expect a function name (IDENTIFIER)
            if self._check(TokenType.IDENTIFIER):
                self._advance()
            else:
                return False
            # expect '('
            if self._check(TokenType.LPAREN):
                return True
            return False
        finally:
            self.pos = saved

    # ==================================================================
    # Global variable
    # ==================================================================

    def _parse_global_var(self) -> Optional[GlobalVarDecl]:
        """
        uint8  PacketByte[];
        uint16 piSrcPort[2:0] = channelId[2:0];
        """
        # type
        var_type = self._parse_type()
        name_tok = self._expect(TokenType.IDENTIFIER)

        init: Optional[Expr] = None

        if self._match(TokenType.LBRACKET):
            if self._match(TokenType.RBRACKET):
                # PacketByte[]
                pass
            else:
                # piSrcPort[2:0]
                _hi = self.parse_expression()
                self._expect(TokenType.COLON)
                _lo = self.parse_expression()
                self._expect(TokenType.RBRACKET)
                if self._match(TokenType.ASSIGN):
                    init = self.parse_expression()
        elif self._match(TokenType.ASSIGN):
            init = self.parse_expression()

        self._expect(TokenType.SEMICOLON)
        return GlobalVarDecl(name=name_tok.value, var_type=var_type, init=init)

    # ==================================================================
    # Type parsing
    # ==================================================================

    def _parse_type(self) -> Optional[Type]:
        """Parse a type: uintN, bool, or struct name."""
        tt = self._peek_type()
        if tt == TokenType.UINT_TYPE:
            tok = self._advance()
            width = int(tok.value[4:])  # "uint8" → 8
            return BitVectorType(width=width)
        elif tt == TokenType.BOOL:
            self._advance()
            return BoolType()
        elif tt == TokenType.IDENTIFIER:
            # Could be a struct type name — consume and return StructType
            name = self._advance().value
            return StructType(name=name)
        return None

    # ==================================================================
    # Struct
    # ==================================================================

    def _parse_struct(self) -> StructDef:
        """struct Name { field; ... }"""
        self._expect(TokenType.STRUCT)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACE)
        self._skip_newlines()

        fields: List[FieldDecl] = []
        while not self._check(TokenType.RBRACE) and not self._eof():
            self._skip_newlines()
            if self._check(TokenType.RBRACE):
                break
            ftype = self._parse_type()
            fname_tok = self._expect(TokenType.IDENTIFIER)
            self._expect(TokenType.SEMICOLON)
            fields.append(FieldDecl(
                name=fname_tok.value,
                field_type=ftype,
            ))
            self._skip_newlines()

        self._expect(TokenType.RBRACE)
        # Note: no semicolon after struct in this DSL
        return StructDef(name=name_tok.value, fields=fields)

    # ==================================================================
    # Process
    # ==================================================================

    def _parse_process(self) -> ProcessDef:
        """process name() { body }"""
        self._expect(TokenType.PROCESS)
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LPAREN)
        self._expect(TokenType.RPAREN)
        body: Optional[CompoundStmt] = None
        self._skip_newlines()
        if self._check(TokenType.LBRACE):
            body = self._parse_compound_stmt()
        return ProcessDef(name=name_tok.value, body=body)

    # ==================================================================
    # Function
    # ==================================================================

    def _parse_function(self) -> FunctionDef:
        """void name(params) { body }   or   void name() { body }"""
        # return type
        ret_type: Optional[Type] = None
        if self._check(TokenType.VOID):
            self._advance()
        else:
            ret_type = self._parse_type()

        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LPAREN)

        # params (comma-separated identifiers)
        params: List[ParamDecl] = []
        if not self._check(TokenType.RPAREN):
            while True:
                pname = self._expect(TokenType.IDENTIFIER)
                params.append(ParamDecl(name=pname.value))
                if not self._match(TokenType.COMMA):
                    break
        self._expect(TokenType.RPAREN)

        body: Optional[CompoundStmt] = None
        self._skip_newlines()
        if self._check(TokenType.LBRACE):
            body = self._parse_compound_stmt()

        return FunctionDef(
            name=name_tok.value,
            params=params,
            return_type=ret_type,
            body=body,
        )

    # ==================================================================
    # Compound statement
    # ==================================================================

    def _parse_compound_stmt(self) -> CompoundStmt:
        """{ stmt* }"""
        self._expect(TokenType.LBRACE)
        self._skip_newlines()
        stmts: List[Stmt] = []
        while not self._check(TokenType.RBRACE) and not self._eof():
            self._skip_newlines()
            if self._check(TokenType.RBRACE):
                break
            s = self._parse_statement()
            if s is not None:
                stmts.append(s)
            self._skip_newlines()
        self._expect(TokenType.RBRACE)
        return CompoundStmt(stmts=stmts)

    # ==================================================================
    # Statement dispatch
    # ==================================================================

    def _parse_statement(self) -> Optional[Stmt]:
        """Dispatch to the correct statement parser based on the first token."""
        self._skip_newlines()
        if self._eof():
            return None

        tt = self._peek_type()

        # -- block --
        if tt == TokenType.LBRACE:
            return self._parse_compound_stmt()

        # -- if / is --
        if tt == TokenType.IF:
            return self._parse_if()
        if tt == TokenType.IDENTIFIER and self._peek().value == "is":
            return self._parse_if(is_keyword=True)

        # -- while --
        if tt == TokenType.WHILE:
            return self._parse_while()

        # -- for --
        if tt == TokenType.FOR:
            return self._parse_for()

        # -- switch --
        if tt == TokenType.SWITCH:
            return self._parse_switch()

        # -- case / default (inside switch) --
        if tt == TokenType.CASE or tt == TokenType.DEFAULT:
            return self._parse_case()

        # -- return --
        if tt == TokenType.RETURN:
            self._advance()
            expr: Optional[Expr] = None
            if not self._check(TokenType.SEMICOLON):
                expr = self.parse_expression()
            self._expect(TokenType.SEMICOLON)
            return ReturnStmt(expr=expr)

        # -- break --
        if tt == TokenType.BREAK:
            self._advance()
            self._expect(TokenType.SEMICOLON)
            return BreakStmt()

        # -- empty statement --
        if tt == TokenType.SEMICOLON:
            self._advance()
            return None

        # -- hardware primitives --
        if tt in (TokenType.DELAY, TokenType.ENQUEUE, TokenType.REPLACE,
                   TokenType.INSERT, TokenType.REMOVE, TokenType.SEND,
                   TokenType.UPDATE):
            return self._parse_hw_primitive()

        # -- variable declaration / assignment / table-read / expression --
        if tt == TokenType.IDENTIFIER:
            return self._parse_ident_statement()

        # -- prefix inc/dec  e.g. ++x; --
        if tt in (TokenType.INC, TokenType.DEC):
            op_tok = self._advance()
            operand = self.parse_expression()
            self._expect(TokenType.SEMICOLON)
            return IncDecStmt(op=op_tok.value, operand=operand, prefix=True)

        # -- expression statement (literal-starting, function call, etc.) --
        expr = self.parse_expression()
        self._expect(TokenType.SEMICOLON)
        return ExprStmt(expr=expr)

    # ==================================================================
    # Identifier-started statement (var_decl, table_read, assignment, etc.)
    # ==================================================================

    def _parse_ident_statement(self) -> Stmt:
        """
        Dispatch an identifier-started statement.

        Patterns:
            IDENT [hi:lo] = expr ;       → VarDeclStmt
            IDENT = IDENT Table[expr] ;  → TableReadStmt
            IDENT = expr ;               → AssignStmt
            IDENT++ / IDENT-- ;          → IncDecStmt
            IDENT += expr ;              → CompoundAssignStmt
            IDENT (expr) ;               → ExprStmt (function call)
            other                        → ExprStmt
        """
        saved_pos = self.pos

        # -- Try var_decl pattern: IDENT [ expr : expr ] = expr ; --
        if (self._check(TokenType.IDENTIFIER) and
                self._peek_type_at(1) == TokenType.LBRACKET):
            id_tok = self._advance()  # name
            self._advance()           # [
            # check if next-next is COLON (bit-slice decl [hi:lo]) vs expr
            self.pos = saved_pos
            # we need a deeper check; just try to parse and rewind on failure
            try:
                return self._parse_var_decl()
            except ParseError:
                self.pos = saved_pos

        # -- Parse LHS expression --
        lhs = self.parse_expression()

        # -- After LHS, check for table-read pattern: = IDENT Table[expr] --
        if (isinstance(lhs, IdentifierExpr) and
                self._check(TokenType.ASSIGN) and
                self._peek_type_at(1) == TokenType.IDENTIFIER):
            # peek further for Table keyword
            peek2 = self._peek_type_at(2)
            if peek2 == TokenType.TABLE:
                return self._parse_table_read(lhs.name)

        # -- Assignment --
        if self._check(TokenType.ASSIGN):
            self._advance()
            rhs = self.parse_expression()
            self._expect(TokenType.SEMICOLON)
            return AssignStmt(lhs=lhs, rhs=rhs)

        # -- Compound assignment --
        for ctt, op_str in _COMPOUND_ASSIGN_OPS.items():
            if self._check(ctt):
                self._advance()
                rhs = self.parse_expression()
                self._expect(TokenType.SEMICOLON)
                return CompoundAssignStmt(op=op_str, lhs=lhs, rhs=rhs)

        # -- Postfix inc/dec --
        if self._check(TokenType.INC) or self._check(TokenType.DEC):
            op_tok = self._advance()
            self._expect(TokenType.SEMICOLON)
            return IncDecStmt(op=op_tok.value, operand=lhs, prefix=False)

        # -- Expression statement --
        self._expect(TokenType.SEMICOLON)
        return ExprStmt(expr=lhs)

    def _peek_type_at(self, offset: int) -> TokenType:
        """Peek token type at pos + offset (skip NEWLINE)."""
        idx = self.pos + offset
        # simple version: just look ahead
        actual_offset = 0
        i = self.pos
        while actual_offset < offset and i < len(self.tokens):
            if self.tokens[i].type != TokenType.NEWLINE:
                actual_offset += 1
            i += 1
        if i < len(self.tokens):
            return self.tokens[i].type
        return TokenType.EOF

    # ==================================================================
    # Variable declaration
    # ==================================================================

    def _parse_var_decl(self) -> VarDeclStmt:
        """IDENT [ hi : lo ] = init ;"""
        name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.LBRACKET)
        _hi = self.parse_expression()
        self._expect(TokenType.COLON)
        _lo = self.parse_expression()
        self._expect(TokenType.RBRACKET)
        self._expect(TokenType.ASSIGN)
        init = self.parse_expression()
        self._expect(TokenType.SEMICOLON)
        return VarDeclStmt(name=name_tok.value, init=init)

    # ==================================================================
    # Table read / write
    # ==================================================================

    def _parse_table_read(self, target_var: str) -> TableReadStmt:
        """target_var = table_name Table[ index ] ;   or   Table{ index }"""
        self._expect(TokenType.ASSIGN)
        table_name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.TABLE)
        # support both Table[expr] and Table{expr}
        if self._check(TokenType.LBRACKET):
            self._advance()
            index = self.parse_expression()
            self._expect(TokenType.RBRACKET)
        elif self._check(TokenType.LBRACE):
            self._advance()
            index = self.parse_expression()
            self._expect(TokenType.RBRACE)
        else:
            raise ParseError("Expected '[' or '{' after Table", self._peek())
        self._expect(TokenType.SEMICOLON)
        return TableReadStmt(
            table_name=table_name_tok.value,
            index=index,
            target_var=target_var,
        )

    def _parse_table_write(self) -> Stmt:
        """update TableName using value at addr ;"""
        self._expect(TokenType.UPDATE)
        table_name_tok = self._expect(TokenType.IDENTIFIER)
        self._expect(TokenType.USING)
        value = self.parse_expression()
        self._expect(TokenType.AT)
        # address expression (possibly {a}.{b} composite)
        addr = self.parse_expression()
        self._expect(TokenType.SEMICOLON)
        return TableWriteStmt(
            table_name=table_name_tok.value,
            index=addr,
            value=value,
        )

    # ==================================================================
    # If / While / For
    # ==================================================================

    def _parse_if(self, is_keyword: bool = False) -> IfStmt:
        """if (cond) stmt [else stmt]   or   is(cond) stmt"""
        if is_keyword:
            self._advance()  # consume "is"
        else:
            self._expect(TokenType.IF)
        self._expect(TokenType.LPAREN)
        cond = self.parse_expression()
        self._expect(TokenType.RPAREN)
        then_stmt = self._parse_statement()
        else_stmt: Optional[Stmt] = None
        if self._check(TokenType.ELSE):
            self._advance()
            else_stmt = self._parse_statement()
        return IfStmt(cond=cond, then_stmt=then_stmt, else_stmt=else_stmt)

    def _parse_while(self) -> WhileStmt:
        """while (cond) body"""
        self._expect(TokenType.WHILE)
        self._expect(TokenType.LPAREN)
        cond = self.parse_expression()
        self._expect(TokenType.RPAREN)
        body = self._parse_statement()
        return WhileStmt(cond=cond, body=body)

    def _parse_for(self) -> ForStmt:
        """for (init; cond; incr) body"""
        self._expect(TokenType.FOR)
        self._expect(TokenType.LPAREN)
        init: Optional[Stmt] = None
        if not self._check(TokenType.SEMICOLON):
            init = self._parse_statement()
        else:
            self._advance()
        cond: Optional[Expr] = None
        if not self._check(TokenType.SEMICOLON):
            cond = self.parse_expression()
        self._expect(TokenType.SEMICOLON)
        incr: Optional[Stmt] = None
        if not self._check(TokenType.RPAREN):
            incr_expr = self.parse_expression()
            incr = ExprStmt(expr=incr_expr)
        self._expect(TokenType.RPAREN)
        body = self._parse_statement()
        return ForStmt(init=init, cond=cond, incr=incr, body=body)

    # ==================================================================
    # Switch / Case
    # ==================================================================

    def _parse_switch(self) -> SwitchStmt:
        """switch (expr) { case* }"""
        self._expect(TokenType.SWITCH)
        self._expect(TokenType.LPAREN)
        expr = self.parse_expression()
        self._expect(TokenType.RPAREN)
        self._expect(TokenType.LBRACE)
        self._skip_newlines()

        cases: List[CaseStmt] = []
        old_in_switch = self._in_switch
        self._in_switch = True
        try:
            while not self._check(TokenType.RBRACE) and not self._eof():
                self._skip_newlines()
                if self._check(TokenType.RBRACE):
                    break
                cs = self._parse_case()
                if cs is not None:
                    cases.append(cs)
                self._skip_newlines()
        finally:
            self._in_switch = old_in_switch

        self._expect(TokenType.RBRACE)
        return SwitchStmt(expr=expr, cases=cases)

    def _parse_case(self) -> Optional[CaseStmt]:
        """
        case expr : stmt
        case expr ~ expr : stmt  (range case)
        default : stmt
        expr : stmt              (switch body without 'case' keyword)
        """
        # -- case keyword --
        if self._match(TokenType.CASE):
            return self._parse_case_body()
        # -- default --
        if self._match(TokenType.DEFAULT):
            self._expect(TokenType.COLON)
            stmt = self._parse_statement()
            return CaseStmt(value=None, stmt=stmt)
        # -- bare expr: in switch body --
        if self._in_switch:
            tt = self._peek_type()
            if tt in (TokenType.INT_LITERAL, TokenType.HEX_LITERAL,
                       TokenType.BIN_LITERAL, TokenType.IDENTIFIER):
                return self._parse_case_body()
        return None

    def _parse_case_body(self) -> CaseStmt:
        """Parse value [~ value] : stmt"""
        value: Expr = self.parse_expression()
        # range case: value ~ value
        if self._check(TokenType.RANGE):
            self._advance()  # ~
            end_val = self.parse_expression()
            value = RangeExpr(start=value, end=end_val)
        self._expect(TokenType.COLON)
        stmt = self._parse_statement()
        return CaseStmt(value=value, stmt=stmt)

    # ==================================================================
    # Hardware primitives
    # ==================================================================

    def _parse_hw_primitive(self) -> Stmt:
        """Dispatch: Delay / Enqueue / Replace / Insert / Remove / Send / Update."""
        tt = self._peek_type()

        if tt == TokenType.DELAY:
            return self._parse_delay()
        elif tt == TokenType.REPLACE:
            return self._parse_replace()
        elif tt == TokenType.INSERT:
            return self._parse_insert()
        elif tt == TokenType.REMOVE:
            return self._parse_remove()
        elif tt == TokenType.SEND:
            return self._parse_send()
        elif tt == TokenType.ENQUEUE:
            return self._parse_enqueue()
        elif tt == TokenType.UPDATE:
            return self._parse_table_write()
        else:
            raise ParseError(f"Unknown hardware primitive: {tt.name}", self._peek())

    def _parse_delay(self) -> DelayStmt:
        """Delay(expr);"""
        self._expect(TokenType.DELAY)
        self._expect(TokenType.LPAREN)
        cycles = self.parse_expression()
        self._expect(TokenType.RPAREN)
        self._expect(TokenType.SEMICOLON)
        return DelayStmt(cycles=cycles)

    def _parse_replace(self) -> ReplaceStmt:
        """Replace X[from] to X[to] using source;   or   Replace X[pos] using source;"""
        self._expect(TokenType.REPLACE)
        # parse full expression: target[from_byte] (or target for no-index)
        target_expr = self.parse_expression()
        from_byte: Expr = IntLiteral(value=0)
        base_target: Expr = target_expr
        if isinstance(target_expr, BitIndexExpr):
            from_byte = target_expr.index  # index is now Expr, use directly
            base_target = target_expr.base

        to_byte: Expr = IntLiteral(value=0)
        if self._match(TokenType.TO):
            to_expr = self.parse_expression()
            if isinstance(to_expr, BitIndexExpr):
                to_byte = to_expr.index
        else:
            to_byte = from_byte

        self._expect(TokenType.USING)
        source = self.parse_expression()
        self._expect(TokenType.SEMICOLON)
        return ReplaceStmt(
            target=base_target,
            from_byte=from_byte,
            to_byte=to_byte,
            source=source,
        )

    def _parse_insert(self) -> InsertStmt:
        """Insert value after X[pos];"""
        self._expect(TokenType.INSERT)
        value = self.parse_expression()
        self._expect(TokenType.AFTER)
        target_expr = self.parse_expression()
        position: Expr = IntLiteral(value=0)
        base_target: Expr = target_expr
        if isinstance(target_expr, BitIndexExpr):
            position = target_expr.index  # index is now Expr
            base_target = target_expr.base
        self._expect(TokenType.SEMICOLON)
        return InsertStmt(value=value, target=base_target, position=position)

    def _parse_remove(self) -> RemoveStmt:
        """remove X[from] ... X[to];"""
        self._expect(TokenType.REMOVE)
        target_expr = self.parse_expression()
        from_byte: Expr = IntLiteral(value=0)
        base_target: Expr = target_expr
        if isinstance(target_expr, BitIndexExpr):
            from_byte = target_expr.index
            base_target = target_expr.base
        self._expect(TokenType.ELLIPSIS)
        to_expr = self.parse_expression()
        to_byte: Expr = IntLiteral(value=0)
        if isinstance(to_expr, BitIndexExpr):
            to_byte = to_expr.index
        self._expect(TokenType.SEMICOLON)
        return RemoveStmt(target=base_target, from_byte=from_byte, to_byte=to_byte)

    def _parse_send(self) -> SendStmt:
        """send ... { expr, ... };  — consume natural language, extract values."""
        self._expect(TokenType.SEND)
        # skip natural-language words until '{' or ';'
        while not self._check(TokenType.LBRACE) and not self._check(TokenType.SEMICOLON) and not self._eof():
            self._advance()
        if self._check(TokenType.SEMICOLON):
            self._advance()
            return SendStmt(expr=IdentifierExpr(name="send"))
        # let parse_expression() handle the { ... } concat
        _fields = self.parse_expression()
        self._expect(TokenType.SEMICOLON)
        return SendStmt(expr=_fields)

    def _parse_enqueue(self) -> EnqueueStmt:
        """Enqueue ... ;  — consume natural language, extract target."""
        self._expect(TokenType.ENQUEUE)
        # skip natural-language words until ';'
        target_parts: List[str] = []
        while not self._check(TokenType.SEMICOLON) and not self._eof():
            t = self._advance()
            target_parts.append(t.value)
        self._expect(TokenType.SEMICOLON)
        target_name = " ".join(target_parts) if target_parts else "enqueue"
        return EnqueueStmt(expr=IdentifierExpr(name=target_name))

    # ==================================================================
    # Expression parsing (precedence climbing)
    # ==================================================================

    def parse_expression(self, min_prec: int = 0) -> Expr:
        """
        Pratt / precedence-climbing expression parser.

        Args:
            min_prec: Minimum precedence to continue (0 = parse all).
        """
        left = self._parse_primary()

        while not self._eof():
            # skip newlines between expression tokens (multi-line expressions)
            while self._check(TokenType.NEWLINE):
                self._advance()

            tt = self._peek_type()

            # -- check for postfix operators (. , [ , { , ( , ++ , -- ) --
            if tt in (TokenType.DOT, TokenType.LBRACKET, TokenType.LBRACE,
                       TokenType.LPAREN, TokenType.INC, TokenType.DEC):
                left = self._parse_postfix(left)
                continue

            # -- check for ternary ? : --
            if tt == TokenType.QUESTION:
                prec = _PRECEDENCE.get(tt, 0)
                if prec < min_prec:
                    break
                cond = left
                self._advance()  # consume '?'
                true_expr = self.parse_expression(0)
                self._expect(TokenType.COLON)
                false_expr = self.parse_expression(prec)
                left = BinaryOpExpr(
                    op="?:",
                    left=cond,
                    right=BinaryOpExpr(op=":", left=true_expr, right=false_expr),
                )
                continue

            # -- binary operator --
            prec = _PRECEDENCE.get(tt, -1)
            if prec < min_prec:
                break
            op_tok = self._advance()
            right = self.parse_expression(prec + 1)
            left = BinaryOpExpr(op=op_tok.value, left=left, right=right)

        return left

    # ==================================================================
    # Primary expression
    # ==================================================================

    def _parse_primary(self) -> Expr:
        """Parse a primary (leaf) expression."""
        tt = self._peek_type()

        # -- Max / Min built-in (must check BEFORE general identifier) --
        if tt == TokenType.IDENTIFIER and self._peek().value in ("Max", "Min"):
            func_name = self._advance().value
            self._expect(TokenType.LPAREN)
            args: List[Expr] = []
            while not self._check(TokenType.RPAREN):
                args.append(self.parse_expression())
                if not self._match(TokenType.COMMA):
                    break
            self._expect(TokenType.RPAREN)
            return MaxMinExpr(func=func_name.lower(), args=args)

        # -- identifier --
        if tt == TokenType.IDENTIFIER:
            tok = self._advance()
            return IdentifierExpr(name=tok.value)

        # -- integer literal --
        if tt == TokenType.INT_LITERAL:
            tok = self._advance()
            return IntLiteral(value=int(tok.value.replace("_", "")))

        # -- hex literal --
        if tt == TokenType.HEX_LITERAL:
            tok = self._advance()
            raw = tok.value.replace("_", "")
            if raw.startswith("0x") or raw.startswith("0X"):
                raw = raw[2:]
            val = int(raw, 16)
            width = len(raw) * 4  # each hex digit = 4 bits
            return HexLiteral(value=val, width=width)

        # -- binary literal (Verilog-style) --
        if tt == TokenType.BIN_LITERAL:
            tok = self._advance()
            v = tok.value
            # parse N'bXXXX or N'hXXXX
            val: int = 0
            width: int = 0
            if "'b" in v.lower():
                width_str, _, bits = v.lower().partition("'b")
                width = int(width_str) if width_str.isdigit() else len(bits)
                bits = bits.replace("_", "").replace("?", "0")
                val = int(bits, 2)
            elif "'h" in v.lower():
                width_str, _, hex_part = v.lower().partition("'h")
                width = int(width_str) if width_str.isdigit() else 0
                hex_part = hex_part.replace("_", "")
                val = int(hex_part, 16)
            return BinLiteral(value=val, width=width)

        # -- parenthesised expression --
        if tt == TokenType.LPAREN:
            self._advance()
            expr = self.parse_expression()
            self._expect(TokenType.RPAREN)
            return expr

        # -- concatenation: { expr, ... }  or  { expr, ..., expr } --
        if tt == TokenType.LBRACE:
            self._advance()
            parts: List[Expr] = []
            if not self._check(TokenType.RBRACE):
                while True:
                    # check for ... (range) BEFORE parsing next expression
                    if self._check(TokenType.ELLIPSIS):
                        self._advance()
                        start_expr = parts.pop() if parts else IntLiteral(value=0)
                        self._match(TokenType.COMMA)  # optional comma after ...
                        end_expr = self.parse_expression()
                        parts.append(RangeExpr(start=start_expr, end=end_expr))
                        break
                    parts.append(self.parse_expression())
                    if not self._match(TokenType.COMMA):
                        break
            self._expect(TokenType.RBRACE)
            return ConcatExpr(parts=parts)

        # -- unary prefix --
        if tt in _UNARY_PREFIX:
            op_tok = self._advance()
            operand = self.parse_expression(100)  # high precedence to capture postfix
            return UnaryOpExpr(op=op_tok.value, operand=operand)

        raise ParseError(f"Unexpected token in expression: {tt.name}", self._peek())

    # ==================================================================
    # Postfix expression
    # ==================================================================

    def _parse_postfix(self, base: Expr) -> Expr:
        """
        Handle postfix operators after a primary:
            .field        → FieldAccessExpr
            .{ a, b }     → CompositeFieldExpr
            [ expr ]      → BitIndexExpr
            [ expr : expr ] → BitSliceExpr
            { expr }      → FieldIndexExpr
            ( args )      → FunctionCallExpr
        """
        tt = self._peek_type()

        if tt == TokenType.DOT:
            self._advance()
            if self._check(TokenType.LBRACE):
                # .{ field1[hi:lo], field2[hi:lo] }
                self._advance()
                field_names: List[str] = []
                while not self._check(TokenType.RBRACE):
                    ft = self._expect(TokenType.IDENTIFIER)
                    fname = ft.value
                    # optional index: [hi:lo]  or  {idx}
                    if self._check(TokenType.LBRACKET):
                        self._advance()
                        self.parse_expression()
                        if self._match(TokenType.COLON):
                            self.parse_expression()
                        self._expect(TokenType.RBRACKET)
                    elif self._check(TokenType.LBRACE):
                        self._advance()
                        self.parse_expression()
                        self._expect(TokenType.RBRACE)
                    field_names.append(fname)
                    self._match(TokenType.COMMA)
                self._expect(TokenType.RBRACE)
                return CompositeFieldExpr(base=base, fields=field_names)
            else:
                field_tok = self._expect(TokenType.IDENTIFIER)
                return FieldAccessExpr(base=base, field=field_tok.value)

        if tt == TokenType.LBRACKET:
            self._advance()
            # distinguish BitIndexExpr vs BitSliceExpr
            saved = self.pos
            first = self.parse_expression()
            if self._check(TokenType.COLON):
                self._advance()
                second = self.parse_expression()
                self._expect(TokenType.RBRACKET)
                # BitSliceExpr: base[hi:lo]
                # Determine which is hi/lo: in the DSL, [hi:lo] or [index:width]
                # Convention: first=hi, second=lo
                hi_val = self._expr_to_int(first)
                lo_val = self._expr_to_int(second)
                if hi_val is not None and lo_val is not None:
                    return BitSliceExpr(base=base, hi_bit=hi_val, lo_bit=lo_val)
                # fallback: keep as generic
                return BitSliceExpr(base=base, hi_bit=0, lo_bit=0)
            else:
                self._expect(TokenType.RBRACKET)
                # BitIndexExpr: base[index] — index is now an expression
                return BitIndexExpr(base=base, index=first)

        if tt == TokenType.LBRACE:
            self._advance()
            idx = self.parse_expression()
            self._expect(TokenType.RBRACE)
            # FieldIndexExpr: base{idx}
            return FieldIndexExpr(base=base, index=idx)

        if tt == TokenType.LPAREN:
            self._advance()
            args: List[Expr] = []
            if not self._check(TokenType.RPAREN):
                while True:
                    args.append(self.parse_expression())
                    if not self._match(TokenType.COMMA):
                        break
            self._expect(TokenType.RPAREN)
            if isinstance(base, IdentifierExpr):
                return FunctionCallExpr(name=base.name, args=args)
            return FunctionCallExpr(name="<anon>", args=args)

        # postfix ++ / --
        if tt in (TokenType.INC, TokenType.DEC):
            op_tok = self._advance()
            return UnaryOpExpr(op="post" + op_tok.value, operand=base)

        return base

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _expr_to_int(e: Expr) -> Optional[int]:
        """Extract an integer value from a literal expression, or None."""
        if isinstance(e, IntLiteral):
            return e.value
        if isinstance(e, HexLiteral):
            return e.value
        return None
