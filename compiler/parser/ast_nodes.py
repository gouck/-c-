"""
compiler/parser/ast_nodes.py
AST node definitions for the 8m compiler.
All nodes are implemented as Python dataclasses with full type annotations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union


# ---------------------------------------------------------------------------
# Type system
# ---------------------------------------------------------------------------

@dataclass
class BitVectorType:
    """Unsigned bit-vector type of a given width (e.g. bit<8>)."""
    width: int


@dataclass
class BoolType:
    """Boolean type."""
    pass


@dataclass
class StructType:
    """User-defined struct type."""
    name: str
    fields: List["FieldDecl"] = field(default_factory=list)


@dataclass
class ArrayType:
    """Fixed-size array type."""
    base_type: Union[BitVectorType, BoolType, StructType, "ArrayType"]
    size: int


# Convenience union
Type = Union[BitVectorType, BoolType, StructType, ArrayType]


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

@dataclass
class IdentifierExpr:
    """Variable or parameter reference."""
    name: str


@dataclass
class IntLiteral:
    """Decimal integer literal."""
    value: int


@dataclass
class BinLiteral:
    """Binary literal (e.g. 0b1010)."""
    value: int
    width: int


@dataclass
class HexLiteral:
    """Hexadecimal literal (e.g. 0xFF)."""
    value: int
    width: Optional[int] = None


@dataclass
class BinaryOpExpr:
    """Binary operation expression (e.g. a + b)."""
    op: str
    left: "Expr"
    right: "Expr"


@dataclass
class UnaryOpExpr:
    """Unary operation expression (e.g. ~a, !a)."""
    op: str
    operand: "Expr"


@dataclass
class FieldAccessExpr:
    """Struct field access (e.g. hdr.field)."""
    base: "Expr"
    field: str


@dataclass
class BitSliceExpr:
    """Bit-slice of an expression (e.g. data[7:0])."""
    base: "Expr"
    hi_bit: int
    lo_bit: int


@dataclass
class BitIndexExpr:
    """Single-bit index (e.g. data[3])."""
    base: "Expr"
    index: "Expr"


@dataclass
class FieldIndexExpr:
    """Field index (e.g. aging{idx}, vlanId{i})."""
    base: "Expr"
    index: "Expr"


@dataclass
class CompositeFieldExpr:
    """Composite field reference."""
    base: "Expr"
    fields: List[str] = field(default_factory=list)


@dataclass
class ConcatExpr:
    """Bit concatenation expression."""
    parts: List["Expr"] = field(default_factory=list)


@dataclass
class FunctionCallExpr:
    """Function call expression."""
    name: str
    args: List["Expr"] = field(default_factory=list)


@dataclass
class MaxMinExpr:
    """max() / min() built-in expression."""
    func: str  # "max" or "min"
    args: List["Expr"] = field(default_factory=list)


@dataclass
class RangeExpr:
    """Range expression (e.g. 0..7)."""
    start: "Expr"
    end: "Expr"


@dataclass
class CompoundExpr:
    """Compound expression grouping."""
    exprs: List["Expr"] = field(default_factory=list)


Expr = Union[
    IdentifierExpr, IntLiteral, BinLiteral, HexLiteral,
    BinaryOpExpr, UnaryOpExpr, FieldAccessExpr, BitSliceExpr,
    BitIndexExpr, FieldIndexExpr, CompositeFieldExpr,
    ConcatExpr, FunctionCallExpr, MaxMinExpr, RangeExpr, CompoundExpr,
]


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

@dataclass
class CompoundStmt:
    """Block statement: { stmt1; stmt2; ... }."""
    stmts: List["Stmt"] = field(default_factory=list)


@dataclass
class WhileStmt:
    """while (cond) body."""
    cond: Expr
    body: "Stmt"


@dataclass
class ForStmt:
    """for (init; cond; incr) body."""
    init: Optional["Stmt"] = None
    cond: Optional[Expr] = None
    incr: Optional["Stmt"] = None
    body: Optional["Stmt"] = None


@dataclass
class IfStmt:
    """if (cond) then_stmt [else else_stmt]."""
    cond: Expr
    then_stmt: "Stmt"
    else_stmt: Optional["Stmt"] = None


@dataclass
class SwitchStmt:
    """switch (expr) { cases... }."""
    expr: Expr
    cases: List["CaseStmt"] = field(default_factory=list)


@dataclass
class CaseStmt:
    """case value: stmt  /  default: stmt."""
    value: Optional[Expr] = None  # None means default
    stmt: Optional["Stmt"] = None


@dataclass
class AssignStmt:
    """Simple assignment: lhs = rhs."""
    lhs: Expr
    rhs: Expr


@dataclass
class CompoundAssignStmt:
    """Compound assignment: lhs op= rhs (e.g. +=, &=, |=)."""
    op: str
    lhs: Expr
    rhs: Expr


@dataclass
class IncDecStmt:
    """Increment / decrement: ++var, --var, var++, var--."""
    op: str      # "++" or "--"
    operand: Expr
    prefix: bool = True


@dataclass
class TableReadStmt:
    """Table read statement (e.g. DsMac = DsMac Table[idx])."""
    table_name: str       # 表名 (如 "DsMac")
    index: Expr           # 索引表达式 (如 giHashIdx)
    target_var: str       # 赋值目标变量名，伪C语法左侧的变量名


@dataclass
class TableWriteStmt:
    """Table write statement."""
    table_name: str
    index: Expr
    value: Expr


@dataclass
class ExprStmt:
    """Expression used as a statement."""
    expr: Expr


@dataclass
class VarDeclStmt:
    """Variable declaration statement."""
    name: str
    var_type: Optional[Type] = None
    init: Optional[Expr] = None


@dataclass
class DelayStmt:
    """Delay statement (simulation)."""
    cycles: Expr


@dataclass
class EnqueueStmt:
    """Enqueue packet statement."""
    expr: Expr


@dataclass
class ReplaceStmt:
    """Replace packet bytes: Replace X[from_byte] to X[to_byte] using source."""
    target: Expr           # 目标数组 (如 IdentifierExpr("PacketByte"))
    from_byte: Expr        # 起始字节位置
    to_byte: Expr          # 结束字节位置
    source: Expr           # 替换用的值


@dataclass
class InsertStmt:
    """Insert bytes into packet: Insert value after X[pos]."""
    value: Expr            # 要插入的值
    target: Expr           # 目标数组
    position: Expr         # 在哪个字节后插入


@dataclass
class RemoveStmt:
    """Remove packet bytes: remove X[from_byte] ... X[to_byte]."""
    target: Expr           # 目标数组
    from_byte: Expr        # 起始字节
    to_byte: Expr          # 结束字节


@dataclass
class SendStmt:
    """Send packet statement."""
    expr: Expr


@dataclass
class ReturnStmt:
    """Return statement."""
    expr: Optional[Expr] = None


@dataclass
class BreakStmt:
    """Break statement."""
    pass


Stmt = Union[
    CompoundStmt, WhileStmt, ForStmt, IfStmt, SwitchStmt, CaseStmt,
    AssignStmt, CompoundAssignStmt, IncDecStmt,
    TableReadStmt, TableWriteStmt, ExprStmt, VarDeclStmt,
    DelayStmt, EnqueueStmt, ReplaceStmt, InsertStmt, RemoveStmt,
    SendStmt, ReturnStmt, BreakStmt,
]


# ---------------------------------------------------------------------------
# Top-level declarations
# ---------------------------------------------------------------------------

@dataclass
class FieldDecl:
    """A field declaration within a struct, memory table, or register."""
    name: str
    field_type: Optional[Type] = None
    width: Optional[int] = None
    offset: int = 0                       # Word 内偏移 (tinyReg.txt Offset 列)
    hi_bit: int = 0                       # 高位
    lo_bit: int = 0                       # 低位
    description: str = ""                 # 字段描述
    read_trigger: bool = False            # (MemReg) 读触发
    write_trigger: bool = False           # (MemReg) 写触发
    read_only: bool = False               # (Register) 只读
    read_indicate: bool = False           # (Register) 读指示
    write_indicate: bool = False          # (Register) 写指示
    write_one_indicate: bool = False      # (Register) 写1指示
    default_value: Optional[str] = None   # (Register) 默认值，如 "4'b0"


@dataclass
class GlobalVarDecl:
    """Global variable declaration."""
    name: str
    var_type: Optional[Type] = None
    init: Optional[Expr] = None


@dataclass
class StructDef:
    """Struct type definition."""
    name: str
    fields: List[FieldDecl] = field(default_factory=list)


@dataclass
class ParamDecl:
    """Function / process parameter declaration."""
    name: str
    param_type: Optional[Type] = None
    direction: str = "in"  # "in", "out", "inout"


@dataclass
class ProcessDef:
    """Process (thread-like entity) definition."""
    name: str
    params: List[ParamDecl] = field(default_factory=list)
    body: Optional[CompoundStmt] = None


@dataclass
class FunctionDef:
    """Function definition."""
    name: str
    params: List[ParamDecl] = field(default_factory=list)
    return_type: Optional[Type] = None
    body: Optional[CompoundStmt] = None


@dataclass
class PseudoCModel:
    """Top-level pseudo-C model declaration."""
    name: str
    processes: List[ProcessDef] = field(default_factory=list)
    functions: List[FunctionDef] = field(default_factory=list)


@dataclass
class MemTableDecl:
    """Memory table declaration (from tinyReg.txt)."""
    name: str
    full_name: str
    num_entries: int
    words: int
    addr_bits: int
    decode_pattern: str
    description: str
    fields: List[FieldDecl] = field(default_factory=list)


@dataclass
class RegisterDecl:
    """Register declaration (from tinyReg.txt)."""
    name: str
    full_name: str
    words: int
    decode_pattern: str
    description: str
    fields: List[FieldDecl] = field(default_factory=list)


@dataclass
class RegMapDef:
    """Top-level register map definition, containing all tables and registers."""
    mem_tables: List[MemTableDecl] = field(default_factory=list)
    registers: List[RegisterDecl] = field(default_factory=list)


@dataclass
class TranslationUnit:
    """The root of the entire compilation – the complete program."""
    model: Optional[PseudoCModel] = None
    reg_map: Optional[RegMapDef] = None
    globals: List[GlobalVarDecl] = field(default_factory=list)
    structs: List[StructDef] = field(default_factory=list)
