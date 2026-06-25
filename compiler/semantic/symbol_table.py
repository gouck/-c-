"""
compiler/semantic/symbol_table.py
Symbol-table management for the 8m compiler.
Supports nested scopes, recursive lookup, and field registration
for memory tables, registers, and structs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from compiler.parser.ast_nodes import (
    FieldDecl,
    FunctionDef,
    GlobalVarDecl,
    MemTableDecl,
    ProcessDef,
    PseudoCModel,
    RegisterDecl,
    RegMapDef,
    StructDef,
    TranslationUnit,
    Type,
)


# ======================================================================
# Symbol
# ======================================================================

@dataclass
class Symbol:
    """A single entry in the symbol table."""

    name: str
    """Symbol name (identifier)."""

    kind: str
    """
    Kind of symbol:
      "table"    – memory-mapped table (e.g. DsMac, DsPort)
      "register" – hardware register (e.g. L2AgingCtl, StormCfgCtl)
      "variable" – global / local variable (e.g. piSrcPort, giStormIdx)
      "struct"   – user-defined struct type (e.g. ParserResult)
      "process"  – process / thread (e.g. forward)
      "function" – function (e.g. parser, switchX)
      "field"    – field of a table / register / struct
    """

    type: Optional[Type] = None
    """Type annotation (BitVectorType, StructType, BoolType, etc.)."""

    decl: Any = None
    """Reference to the AST declaration node that introduced this symbol."""

    parent_table: Optional[str] = None
    """For "field" kinds: the name of the parent table / register / struct."""

    bit_width: Optional[tuple] = None
    """For variables / fields: (hi, lo) bit-range when declared with [hi:lo]."""


# ======================================================================
# SymbolTable
# ======================================================================

class SymbolTable:
    """
    A single scope in the symbol table with optional parent (enclosing scope).

    Usage:
        global_scope = SymbolTable()
        global_scope.define(Symbol(name="DsMac", kind="table", ...))

        func_scope = SymbolTable(parent=global_scope)
        func_scope.define(Symbol(name="i", kind="variable", ...))
        func_scope.lookup("DsMac")   # → found in global_scope (recurse=True)
    """

    def __init__(self, parent: Optional[SymbolTable] = None) -> None:
        """
        Args:
            parent: The enclosing (outer) scope, or None for the global scope.
        """
        self.symbols: Dict[str, Symbol] = {}
        self.parent: Optional[SymbolTable] = parent

    # ------------------------------------------------------------------
    # define
    # ------------------------------------------------------------------

    def define(self, symbol: Symbol) -> None:
        """
        Insert a symbol into the current scope.

        Raises:
            ValueError: If a symbol with the same name already exists
                        in this scope.
        """
        name = symbol.name
        if name in self.symbols:
            existing = self.symbols[name]
            raise ValueError(
                f"Symbol '{name}' ({symbol.kind}) already defined in this scope "
                f"as '{existing.kind}'. Redeclaration is not allowed."
            )
        self.symbols[name] = symbol

    # ------------------------------------------------------------------
    # lookup
    # ------------------------------------------------------------------

    def lookup(self, name: str, recurse: bool = True) -> Optional[Symbol]:
        """
        Find a symbol by name.

        Args:
            name: The symbol name to look up.
            recurse: If True, search parent scopes when not found locally.

        Returns:
            The Symbol if found, or None.
        """
        if name in self.symbols:
            return self.symbols[name]
        if recurse and self.parent is not None:
            return self.parent.lookup(name, recurse=True)
        return None

    def lookup_local(self, name: str) -> Optional[Symbol]:
        """
        Look up a symbol in the current scope only (no parent search).

        Returns:
            The Symbol if found in this scope, or None.
        """
        return self.symbols.get(name)

    # ------------------------------------------------------------------
    # Field helpers
    # ------------------------------------------------------------------

    def define_field(self, parent_name: str, field: FieldDecl) -> None:
        """
        Register a field as belonging to a parent table / register / struct.

        The field is stored as a "field"-kind symbol whose key is
        ``parent_name.field_name`` (composite key) to avoid collisions
        between fields of the same name in different parents.

        Args:
            parent_name: Name of the owning table, register, or struct.
            field:       The FieldDecl AST node to register.
        """
        key = f"{parent_name}.{field.name}"
        sym = Symbol(
            name=field.name,
            kind="field",
            type=field.field_type,
            decl=field,
            parent_table=parent_name,
            bit_width=(field.hi_bit, field.lo_bit),
        )
        self.symbols[key] = sym  # bypass define() to skip duplicate check

    def lookup_field(self, parent_name: str, field_name: str) -> Optional[Symbol]:
        """
        Look up a field by its owning parent name and field name.

        Fields are stored with composite keys ``parent.field``.

        Args:
            parent_name: Name of the parent table / register / struct.
            field_name:  Name of the field.

        Returns:
            The field Symbol if found, or None.
        """
        key = f"{parent_name}.{field_name}"
        return self.symbols.get(key)

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    def dump(self, indent: int = 0) -> None:
        """Print the symbol table contents for debugging."""
        prefix = "  " * indent
        for name, sym in self.symbols.items():
            extra = ""
            if sym.parent_table:
                extra = f"  (parent={sym.parent_table})"
            print(f"{prefix}{sym.kind:10s} {name:30s}{extra}")


# ======================================================================
# SymbolTableBuilder
# ======================================================================

class SymbolTableBuilder:
    """
    Walks the TranslationUnit AST and populates a SymbolTable.

    Build order (matching declaration-before-use semantics):
      1. memory tables & registers (from RegMapDef)
      2. struct definitions
      3. global variables
      4. functions & processes
    """

    def __init__(self) -> None:
        self.global_scope: SymbolTable = SymbolTable()

    # ------------------------------------------------------------------
    # build
    # ------------------------------------------------------------------

    def build(self, ast: TranslationUnit) -> SymbolTable:
        """
        Populate ``self.global_scope`` from *ast* and return it.

        Args:
            ast: The root TranslationUnit AST node.

        Returns:
            The populated global SymbolTable.
        """
        # 1. RegMapDef → tables & registers + their fields
        if ast.reg_map is not None:
            self._collect_regmap(ast.reg_map)

        # 2. struct definitions + fields
        for sdef in ast.structs:
            self._collect_struct(sdef)

        # 3. global variables
        for gvar in ast.globals:
            self._collect_global_var(gvar)

        # 4. functions & processes (from PseudoCModel)
        if ast.model is not None:
            for func in ast.model.functions:
                self._collect_function(func)
            for proc in ast.model.processes:
                self._collect_process(proc)

        return self.global_scope

    # ==================================================================
    # Internal collectors
    # ==================================================================

    def _collect_regmap(self, reg_map: RegMapDef) -> None:
        """Register memory tables, registers, and their fields."""
        # memory tables
        for mt in reg_map.mem_tables:
            sym = Symbol(
                name=mt.name,
                kind="table",
                decl=mt,
                type=None,  # tables don't have a simple type
            )
            self.global_scope.define(sym)
            # fields
            for f in mt.fields:
                self.global_scope.define_field(mt.name, f)

        # registers
        for reg in reg_map.registers:
            sym = Symbol(
                name=reg.name,
                kind="register",
                decl=reg,
                type=None,
            )
            self.global_scope.define(sym)
            # fields
            for f in reg.fields:
                self.global_scope.define_field(reg.name, f)

    def _collect_struct(self, sdef: StructDef) -> None:
        """Register a struct type and its fields."""
        sym = Symbol(
            name=sdef.name,
            kind="struct",
            decl=sdef,
            type=None,  # struct itself doesn't have a "type" — it IS a type
        )
        self.global_scope.define(sym)
        for f in sdef.fields:
            self.global_scope.define_field(sdef.name, f)

    def _collect_global_var(self, gvar: GlobalVarDecl) -> None:
        """Register a global variable."""
        sym = Symbol(
            name=gvar.name,
            kind="variable",
            type=gvar.var_type,
            decl=gvar,
        )
        self.global_scope.define(sym)

    def _collect_function(self, func: FunctionDef) -> None:
        """Register a function definition."""
        sym = Symbol(
            name=func.name,
            kind="function",
            type=func.return_type,
            decl=func,
        )
        self.global_scope.define(sym)

    def _collect_process(self, proc: ProcessDef) -> None:
        """Register a process definition."""
        sym = Symbol(
            name=proc.name,
            kind="process",
            decl=proc,
        )
        self.global_scope.define(sym)
