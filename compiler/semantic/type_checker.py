"""
compiler/semantic/type_checker.py
Semantic type-checker for the 8m compiler.
Walks the AST, infers types for every expression node, and validates
assignment width compatibility.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from compiler.parser.ast_nodes import (
    # types
    BitVectorType, BoolType, StructType, Type,
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
    FunctionDef, ProcessDef, PseudoCModel, TranslationUnit,
)
from compiler.semantic.symbol_table import Symbol, SymbolTable


# ======================================================================
# Public entry point
# ======================================================================

def analyze(ast: TranslationUnit, symbol_table: SymbolTable) -> "TypeChecker":
    """
    Run semantic analysis on *ast* using *symbol_table*.

    Returns the TypeChecker instance so callers can inspect
    ``checker.errors`` and ``checker.warnings``.
    """
    checker = TypeChecker(symbol_table)
    checker.check(ast)
    return checker


# ======================================================================
# TypeChecker
# ======================================================================

class TypeChecker:
    """
    Walks the AST and performs type inference and compatibility checks.

    Usage:
        checker = TypeChecker(symtab)
        checker.check(translation_unit)
        if checker.errors:
            for e in checker.errors: print(e)
    """

    def __init__(self, symbol_table: SymbolTable) -> None:
        self.symtab: SymbolTable = symbol_table
        self.errors: List[str] = []
        self.warnings: List[str] = []
        # per-function / per-process local scope
        self._local_scope: Optional[SymbolTable] = None

    # ==================================================================
    # Top-level entry
    # ==================================================================

    def check(self, ast: TranslationUnit) -> None:
        """Walk every function and process body in the AST."""
        if ast.model is not None:
            for func in ast.model.functions:
                self._check_function(func)
            for proc in ast.model.processes:
                self._check_process(proc)

    # ------------------------------------------------------------------
    # Function / Process
    # ------------------------------------------------------------------

    def _check_function(self, func: FunctionDef) -> None:
        """Check a function: create local scope for params, check body."""
        saved = self._local_scope
        self._local_scope = SymbolTable(parent=self.symtab)
        # register parameters as local variables
        for p in func.params:
            self._local_scope.define(Symbol(
                name=p.name, kind="variable", type=p.param_type,
            ))
        if func.body is not None:
            self._check_compound(func.body)
        self._local_scope = saved

    def _check_process(self, proc: ProcessDef) -> None:
        """Check a process: create local scope, check body."""
        saved = self._local_scope
        self._local_scope = SymbolTable(parent=self.symtab)
        if proc.body is not None:
            self._check_compound(proc.body)
        self._local_scope = saved

    # ==================================================================
    # Statement dispatch
    # ==================================================================

    def _check_statement(self, stmt: Optional[Stmt]) -> None:
        """Dispatch a single statement to its handler."""
        if stmt is None:
            return
        if isinstance(stmt, CompoundStmt):
            self._check_compound(stmt)
        elif isinstance(stmt, AssignStmt):
            self._check_assign(stmt)
        elif isinstance(stmt, CompoundAssignStmt):
            self._check_compound_assign(stmt)
        elif isinstance(stmt, IncDecStmt):
            self._check_inc_dec(stmt)
        elif isinstance(stmt, IfStmt):
            self._check_if(stmt)
        elif isinstance(stmt, WhileStmt):
            self._check_while(stmt)
        elif isinstance(stmt, ForStmt):
            self._check_for(stmt)
        elif isinstance(stmt, SwitchStmt):
            self._check_switch(stmt)
        elif isinstance(stmt, VarDeclStmt):
            self._check_var_decl(stmt)
        elif isinstance(stmt, TableReadStmt):
            self._check_table_read(stmt)
        elif isinstance(stmt, TableWriteStmt):
            self._check_table_write(stmt)
        elif isinstance(stmt, DelayStmt):
            self.infer_type(stmt.cycles)
        elif isinstance(stmt, ExprStmt):
            self.infer_type(stmt.expr)
        elif isinstance(stmt, ReturnStmt):
            if stmt.expr is not None:
                self.infer_type(stmt.expr)
        elif isinstance(stmt, (BreakStmt,)):
            pass
        elif isinstance(stmt, (ReplaceStmt, InsertStmt, RemoveStmt,
                               SendStmt, EnqueueStmt)):
            # hardware primitives — infer types for sub-expressions only
            for attr in ("target", "from_byte", "to_byte", "source",
                          "value", "position", "expr"):
                sub = getattr(stmt, attr, None)
                if sub is not None and not isinstance(sub, str):
                    try:
                        self.infer_type(sub)
                    except Exception:
                        pass

    # ------------------------------------------------------------------
    # Compound
    # ------------------------------------------------------------------

    def _check_compound(self, stmt: CompoundStmt) -> None:
        for s in stmt.stmts:
            self._check_statement(s)

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def _check_assign(self, stmt: AssignStmt) -> None:
        """Check lhs = rhs for width compatibility."""
        lhs_t = self.infer_type(stmt.lhs)
        rhs_t = self.infer_type(stmt.rhs)
        lhs_w = self._type_width(lhs_t)
        rhs_w = self._type_width(rhs_t)
        if lhs_w is not None and rhs_w is not None:
            if rhs_w > lhs_w:
                self.warnings.append(
                    f"Assignment RHS width ({rhs_w}) exceeds LHS width ({lhs_w}); "
                    f"high bits will be truncated."
                )

    def _check_compound_assign(self, stmt: CompoundAssignStmt) -> None:
        """Check lhs op= rhs."""
        self.infer_type(stmt.lhs)
        self.infer_type(stmt.rhs)

    def _check_inc_dec(self, stmt: IncDecStmt) -> None:
        self.infer_type(stmt.operand)

    # ------------------------------------------------------------------
    # If / While / For
    # ------------------------------------------------------------------

    def _check_if(self, stmt: IfStmt) -> None:
        self.infer_type(stmt.cond)
        self._check_statement(stmt.then_stmt)
        if stmt.else_stmt is not None:
            self._check_statement(stmt.else_stmt)

    def _check_while(self, stmt: WhileStmt) -> None:
        self.infer_type(stmt.cond)
        self._check_statement(stmt.body)

    def _check_for(self, stmt: ForStmt) -> None:
        if stmt.init is not None:
            self._check_statement(stmt.init)
        if stmt.cond is not None:
            self.infer_type(stmt.cond)
        if stmt.incr is not None:
            self._check_statement(stmt.incr)
        if stmt.body is not None:
            self._check_statement(stmt.body)

    # ------------------------------------------------------------------
    # Switch / Case
    # ------------------------------------------------------------------

    def _check_switch(self, stmt: SwitchStmt) -> None:
        self.infer_type(stmt.expr)
        for cs in stmt.cases:
            if cs.value is not None:
                self.infer_type(cs.value)
            if cs.stmt is not None:
                self._check_statement(cs.stmt)

    # ------------------------------------------------------------------
    # 变量声明
    # ------------------------------------------------------------------

    def _check_var_decl(self, stmt: VarDeclStmt) -> None:
        """Register a local variable in the current process/function scope."""
        # Derive type from initializer if var_type is not set
        var_type = stmt.var_type
        if var_type is None and stmt.init is not None:
            var_type = self.infer_type(stmt.init)
        # Register in local scope
        if self._local_scope is not None:
            try:
                self._local_scope.define(Symbol(
                    name=stmt.name,
                    kind="variable",
                    type=var_type,
                    decl=stmt,
                ))
            except ValueError:
                self.errors.append(
                    f"Variable '{stmt.name}' already declared in this scope."
                )
        # Check initializer
        if stmt.init is not None:
            self.infer_type(stmt.init)

    # ------------------------------------------------------------------
    # Table read / write
    # ------------------------------------------------------------------

    def _check_table_read(self, stmt: TableReadStmt) -> None:
        """Verify the table exists and the index expression is valid."""
        sym = self._lookup(stmt.table_name)
        if sym is None or sym.kind != "table":
            self.errors.append(
                f"Table '{stmt.table_name}' not found for table read."
            )
        self.infer_type(stmt.index)

    def _check_table_write(self, stmt: TableWriteStmt) -> None:
        sym = self._lookup(stmt.table_name)
        if sym is None or sym.kind != "table":
            self.errors.append(
                f"Table '{stmt.table_name}' not found for table write."
            )
        self.infer_type(stmt.index)
        self.infer_type(stmt.value)

    # ==================================================================
    # Expression type inference
    # ==================================================================

    def infer_type(self, expr: Expr) -> Optional[Type]:
        """
        Derive the type of *expr* and return it.

        Returns None when the type cannot be determined (e.g. undefined
        identifier).  Errors are appended to ``self.errors``.
        """
        # ---- IdentifierExpr ----
        if isinstance(expr, IdentifierExpr):
            sym = self._lookup(expr.name)
            if sym is None:
                self.errors.append(f"Undefined identifier '{expr.name}'.")
                return None
            if sym.type is not None:
                return sym.type
            if sym.bit_width is not None:
                hi, lo = sym.bit_width
                return BitVectorType(width=hi - lo + 1)
            # For tables / registers / structs — no simple type
            return None

        # ---- IntLiteral ----
        if isinstance(expr, IntLiteral):
            w = self._min_bits_for_value(expr.value)
            return BitVectorType(width=w)

        # ---- HexLiteral ----
        if isinstance(expr, HexLiteral):
            w = expr.width or expr.value.bit_length() or 1
            return BitVectorType(width=w)

        # ---- BinLiteral ----
        if isinstance(expr, BinLiteral):
            return BitVectorType(width=expr.width)

        # ---- BinaryOpExpr ----
        if isinstance(expr, BinaryOpExpr):
            lt = self.infer_type(expr.left)
            rt = self.infer_type(expr.right)
            lw = self._type_width(lt)
            rw = self._type_width(rt)

            # logical ops → BoolType
            if expr.op in ("&&", "||", "!", "==", "!=", "<", ">", "<=", ">="):
                return BoolType()

            # bitwise / arithmetic → max width
            if lw is not None and rw is not None:
                if expr.op in ("<<",):
                    # shift-left: width is left + shift amount
                    shift_amt = self._expr_to_int(expr.right)
                    if shift_amt is not None:
                        return BitVectorType(width=lw + shift_amt)
                    return BitVectorType(width=lw)
                return BitVectorType(width=max(lw, rw))
            if lw is not None:
                return BitVectorType(width=lw)
            if rw is not None:
                return BitVectorType(width=rw)
            return None

        # ---- UnaryOpExpr ----
        if isinstance(expr, UnaryOpExpr):
            ot = self.infer_type(expr.operand)
            if expr.op in ("!",):
                return BoolType()
            # ~, -, + → same type as operand
            if ot is not None:
                return ot
            ow = self._type_width(ot)
            if ow is not None:
                return BitVectorType(width=ow)
            return None

        # ---- FieldAccessExpr ----
        if isinstance(expr, FieldAccessExpr):
            if isinstance(expr.base, IdentifierExpr):
                parent = expr.base.name
                fsym = self.symtab.lookup_field(parent, expr.field)
                if fsym is None and self._local_scope is not None:
                    fsym = self._local_scope.lookup_field(parent, expr.field)
                if fsym is not None:
                    if fsym.type is not None:
                        return fsym.type
                    if fsym.bit_width is not None:
                        hi, lo = fsym.bit_width
                        return BitVectorType(width=hi - lo + 1)
                self.errors.append(
                    f"Field '{expr.field}' not found in '{parent}'."
                )
            return None

        # ---- BitSliceExpr ----
        if isinstance(expr, BitSliceExpr):
            w = expr.hi_bit - expr.lo_bit + 1
            if w > 0:
                return BitVectorType(width=w)
            return BitVectorType(width=1)

        # ---- BitIndexExpr ----
        if isinstance(expr, BitIndexExpr):
            return BitVectorType(width=1)

        # ---- FieldIndexExpr ----
        if isinstance(expr, FieldIndexExpr):
            # field index (e.g. aging{idx}) — width depends on parent field
            if isinstance(expr.base, FieldAccessExpr):
                inner = self.infer_type(expr.base)
                return inner
            return BitVectorType(width=1)

        # ---- CompositeFieldExpr ----
        if isinstance(expr, CompositeFieldExpr):
            total_w = 0
            for fname in expr.fields:
                # try to look up each field
                parent = ""
                if isinstance(expr.base, IdentifierExpr):
                    parent = expr.base.name
                fsym = self.symtab.lookup_field(parent, fname)
                if fsym is not None and fsym.bit_width is not None:
                    hi, lo = fsym.bit_width
                    total_w += hi - lo + 1
            if total_w > 0:
                return BitVectorType(width=total_w)
            return None

        # ---- ConcatExpr ----
        if isinstance(expr, ConcatExpr):
            total_w = 0
            for p in expr.parts:
                pt = self.infer_type(p)
                pw = self._type_width(pt)
                if pw is not None:
                    total_w += pw
                elif isinstance(p, IntLiteral):
                    total_w += self._min_bits_for_value(p.value)
            if total_w > 0:
                return BitVectorType(width=total_w)
            return None

        # ---- FunctionCallExpr ----
        if isinstance(expr, FunctionCallExpr):
            # infer arg types
            for a in expr.args:
                self.infer_type(a)
            sym = self._lookup(expr.name)
            if sym is not None and sym.kind == "function":
                return sym.type  #  return type
            # built-in / unknown → use arg widths
            max_w = 0
            for a in expr.args:
                w = self.get_bit_width(a)
                if w is not None:
                    max_w = max(max_w, w)
            if max_w > 0:
                return BitVectorType(width=max_w)
            return None

        # ---- MaxMinExpr ----
        if isinstance(expr, MaxMinExpr):
            max_w = 0
            for a in expr.args:
                w = self.get_bit_width(a)
                if w is not None:
                    max_w = max(max_w, w)
            if max_w > 0:
                return BitVectorType(width=max_w)
            return None

        # ---- RangeExpr ----
        if isinstance(expr, RangeExpr):
            sw = self.get_bit_width(expr.start)
            ew = self.get_bit_width(expr.end)
            w = max(sw or 1, ew or 1)
            return BitVectorType(width=w)

        # ---- CompoundExpr ----
        if isinstance(expr, CompoundExpr):
            for e in expr.exprs:
                self.infer_type(e)
            return None

        return None

    # ==================================================================
    # Bit-width helpers
    # ==================================================================

    def get_bit_width(self, expr_or_type: Union[Expr, Type, None]) -> Optional[int]:
        """Return the bit-width of an expression or type."""
        if expr_or_type is None:
            return None
        if isinstance(expr_or_type, (BitVectorType, BoolType, StructType)):
            return self._type_width(expr_or_type)
        # treat as expression
        t = self.infer_type(expr_or_type)
        return self._type_width(t)

    @staticmethod
    def _type_width(t: Optional[Type]) -> Optional[int]:
        """Extract bit-width from a Type object."""
        if isinstance(t, BitVectorType):
            return t.width
        if isinstance(t, BoolType):
            return 1
        return None

    @staticmethod
    def _min_bits_for_value(value: int) -> int:
        """Minimum bits needed to represent *value* (1 for 0)."""
        if value == 0:
            return 1
        return value.bit_length()

    @staticmethod
    def _expr_to_int(e: Expr) -> Optional[int]:
        """Extract a constant integer from a literal expression."""
        if isinstance(e, IntLiteral):
            return e.value
        if isinstance(e, HexLiteral):
            return e.value
        if isinstance(e, BinLiteral):
            return e.value
        return None

    # ==================================================================
    # Symbol lookup (local → global)
    # ==================================================================

    def _lookup(self, name: str) -> Optional[Symbol]:
        """Look up *name* in local scope first, then global."""
        if self._local_scope is not None:
            sym = self._local_scope.lookup(name, recurse=False)
            if sym is not None:
                return sym
        return self.symtab.lookup(name, recurse=True)
