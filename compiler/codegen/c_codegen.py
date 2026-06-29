"""
compiler/codegen/c_codegen.py
C code generator for the 8m compiler.
Walks the PseudoCModel AST and emits compilable C99 code.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from compiler.parser.ast_nodes import (
    BitVectorType, BoolType, StructType, Type,
    IdentifierExpr, IntLiteral, BinLiteral, HexLiteral,
    BinaryOpExpr, UnaryOpExpr, FieldAccessExpr, BitSliceExpr,
    BitIndexExpr, FieldIndexExpr, CompositeFieldExpr,
    ConcatExpr, FunctionCallExpr, MaxMinExpr, RangeExpr,
    Expr,
    CompoundStmt, WhileStmt, ForStmt, IfStmt, SwitchStmt, CaseStmt,
    AssignStmt, CompoundAssignStmt, IncDecStmt,
    TableReadStmt, TableWriteStmt, ExprStmt, VarDeclStmt,
    DelayStmt, EnqueueStmt, ReplaceStmt, InsertStmt, RemoveStmt,
    SendStmt, ReturnStmt, BreakStmt,
    Stmt,
    FunctionDef, ProcessDef, StructDef, GlobalVarDecl,
    FieldDecl, TranslationUnit,
)
from compiler.semantic.symbol_table import SymbolTable


# C keywords that must be prefixed with __ in field access
_C_KEYWORDS = {"static", "const", "volatile", "register", "auto", "extern", "typedef", "enum"}

# Field name aliases: pseudo-C name → actual reg_drv.h field name
_FIELD_ALIASES: "dict[str, str]" = {
    "PriorAssignCtl.ip0Addr": "PriorAssignCtl.ip0AddrBit127To96",
    "PriorAssignCtl.ip0Mask": "PriorAssignCtl.ip0MaskBit127To96",
    "PriorAssignCtl.ip1Addr": "PriorAssignCtl.ip1AddrBit127To96",
    "PriorAssignCtl.ip1Mask": "PriorAssignCtl.ip1MaskBit127To96",
    "LoopDetectCtl.loopMac": "LoopDetectCtl.loopMacHi",
    "PriorAssignCtl.dscpWeight": "PriorAssignCtl.DscpWeight",
}

# Table name aliases: pseudo-C name → actual reg_drv.h mem-array name
_TABLE_ALIASES: "dict[str, str]" = {
}

# Typo 自动纠正ions for known misspellings in 8mSpec
_NAME_CORRECTIONS: "dict[str, str]" = {
    "PacketBypte": "PacketByte",
    "DsMacAing": "DsMacAging",
}

# Known variable bit-widths used in concat expressions.
# These are derived from the DSL's domain knowledge (tinyReg field widths,
# explicit [hi:lo] annotations, etc.) where automatic width inference
# cannot reach (e.g. parser→switch cross-function variables).
_KNOWN_VAR_WIDTHS: "dict[str, int]" = {
    "prMacDa": 48,       # MAC destination address (6 bytes)
    "prMacSa": 48,       # MAC source address (6 bytes)
    "giFid": 12,         # FID from DsVlan.fid[11:0]
    "piFid": 12,         # same as giFid
    "prVlanId": 12,      # VLAN ID [11:0]
    "piVlanId": 12,      # VLAN ID (copy)
    "giVid": 12,         # VLAN ID (may be portVid or prVlanId)
    "piPortVid": 12,     # Port default VLAN ID
    "prVlanPrior": 3,    # VLAN priority [2:0]
    "piPrior": 2,        # Final priority [1:0]
    "piPortPrior": 2,    # Port priority [1:0]
    "piVlanPrior": 2,    # VLAN priority [1:0]
    "piDscpPrior": 2,    # DSCP priority [1:0]
    "piMacDaPrior": 2,   # MAC DA priority [1:0]
    "piIpAddrPrior": 2,  # IP address priority [1:0]
    "piVlanMember": 10,  # VLAN member bitmap
    "piFwdBmp": 10,      # Forwarding bitmap [9:0]
    "piUntagFlag": 10,   # Untag flag [9:0]
    "piSrcPort": 3,      # Source port [2:0]
    "piDestPort": 3,     # Destination port [2:0]
    "piPktLength": 14,   # Packet length
    "giPldOffset": 8,    # Payload offset
    "giHashIdx": 9,      # Hash index [8:0]
    "giLrnHash": 9,      # Learn hash index [8:0]
    "giLrnSubIdx": 2,    # Learn sub-index (way) [1:0]
    "piLoopTtl": 4,      # Loop detect TTL [3:0]
    "prLoopTtl": 4,      # Loop detect TTL (copy)
    "piPktTagged": 1,    # Packet tagged flag
    "prExistVlan": 1,    # Existing VLAN flag
    "piOutNoVlan": 1,    # Output no-VLAN flag
    "piIsLoopDetect": 1, # Is loop detection
    "prIsLoopDetection": 1,
    "prIsArp": 1,
    "prIsIpv4": 1,
    "prIsIpv6": 1,
    "piBcast": 1,        # Broadcast flag
    "piMcast": 1,        # Multicast flag
    "piBrgHit": 1,       # Bridge hit flag
    "piDiscard": 1,      # Discard flag
    "piFlooding": 1,     # Flooding flag
    "piLrnDisable": 1,
    "piAllowBrg2Src": 1,
    "giVlanHit": 1,
    "giLrnHit": 1,
    "giLrnNew": 1,
    "giLruLrn": 1,
    "piRmaMode": 1,
    "piPortMirror": 1,
    "piVlanMirror": 1,
    "piEgressFilter": 1,
    "piLeakyUcast": 1,
    "piLeakyMcast": 1,
    "piLeakyBcast": 1,
    "piLeakyArp": 1,
    "piLeakyMirror": 1,
    "pi1qBasedVlan": 1,
    "pi1qPriorEn": 1,
}


# ======================================================================
# CCodeGenerator
# ======================================================================

class CCodeGenerator:
    """从8m AST生成可编译的C99代码"""

    def __init__(self, ast: TranslationUnit, symbol_table: SymbolTable) -> None:
        self.ast = ast
        self.symtab = symbol_table
        self._indent_level: int = 0
        # per-process state tracking for nested-while FSMs
        self._process_vars: Dict[str, str] = {}
        self._fsm_state: int = 0
        self._in_process: bool = False
        self._declared_vars: set[str] = set()
        # Track variable bit widths inferred from assignments / declarations
        self._var_widths: Dict[str, int] = {}
        # Track table way bits: table_name → number of bits for the way index
        self._table_way_bits: Dict[str, int] = {}

    # ==================================================================
    # helpers
    # ==================================================================

    @staticmethod
    def _is_packet_byte_index(name: str) -> "Optional[int]":
        """If name is 'PacketByte<N>', return N as int; else None."""
        import re
        m = re.match(r'^PacketByte(\d+)$', name)
        if m:
            return int(m.group(1))
        return None

    def _resolve_name(self, name: str) -> str:
        """Resolve an identifier name, converting PacketByte<N> → PacketByte[<N>]."""
        idx = self._is_packet_byte_index(name)
        if idx is not None:
            return f"PacketByte[{idx}]"
        # Apply typo corrections
        if name in _NAME_CORRECTIONS:
            name = _NAME_CORRECTIONS[name]
        return name

    def _get_bit_width(self, expr: Expr) -> "Optional[int]":
        """Determine the bit width of an expression, if known.
        
        Returns None when the width cannot be determined.
        """
        if isinstance(expr, BinLiteral):
            return expr.width
        if isinstance(expr, HexLiteral):
            return expr.width
        if isinstance(expr, IntLiteral):
            # Decimal literal without explicit width: cannot determine
            return None
        if isinstance(expr, BitSliceExpr):
            return expr.hi_bit - expr.lo_bit + 1
        if isinstance(expr, BitIndexExpr):
            return 1
        if isinstance(expr, FieldAccessExpr):
            w = self._infer_field_width(expr)
            if w is not None:
                return w
            # Try symbol table
            if isinstance(expr.base, IdentifierExpr):
                full_key = f"{expr.base.name}.{expr.field}"
                # Check field alias
                if full_key in _FIELD_ALIASES:
                    resolved = _FIELD_ALIASES[full_key]
                    parts = resolved.split(".")
                    w = self._infer_field_width_from_name(parts[0], parts[-1])
                    if w is not None:
                        return w
                w = self._infer_field_width_from_name(expr.base.name, expr.field)
                if w is not None:
                    return w
            return None
        if isinstance(expr, IdentifierExpr):
            # Check tracked variable widths
            if expr.name in self._var_widths:
                return self._var_widths[expr.name]
            # Check known widths from domain knowledge
            if expr.name in _KNOWN_VAR_WIDTHS:
                return _KNOWN_VAR_WIDTHS[expr.name]
            return None
        if isinstance(expr, ConcatExpr):
            widths = [self._get_bit_width(p) for p in expr.parts]
            if all(w is not None for w in widths):
                return sum(widths)
            return None
        if isinstance(expr, BinaryOpExpr):
            if expr.op == "<<":
                # x << N: width = width(x) + N
                base_w = self._get_bit_width(expr.left)
                if base_w is not None and isinstance(expr.right, IntLiteral):
                    return base_w + expr.right.value
            return None
        return None

    def _infer_field_width(self, expr: "FieldAccessExpr") -> "Optional[int]":
        """Infer the bit-width of a field access expression from the symtab."""
        if not isinstance(expr.base, IdentifierExpr):
            return None
        return self._infer_field_width_from_name(expr.base.name, expr.field)

    def _infer_field_width_from_name(self, parent_name: str, field_name: str) -> "Optional[int]":
        """Look up a field's bit width from the symbol table."""
        sym = self.symtab.lookup(parent_name)
        if sym is None or sym.decl is None:
            return None
        # sym.decl is a MemTableDecl or RegisterDecl with .fields
        if not hasattr(sym.decl, 'fields'):
            return None
        for f in sym.decl.fields:
            if f.name == field_name:
                return f.hi_bit - f.lo_bit + 1
        return None

    def _track_var_width(self, name: str, width: int) -> None:
        """Record the bit width of a variable."""
        if name in _NAME_CORRECTIONS:
            name = _NAME_CORRECTIONS[name]
        self._var_widths[name] = width

    def _infer_table_way_bits(self, table_name: str) -> int:
        """Infer the number of way-index bits for a set-associative table.
        
        Heuristic: if a table has 4x the entries of a related table sharing
        the same prefix stem (e.g. DsMac 2048 vs DsMacAging 512), it is
        likely 4-way set-associative → way bits = 2.
        """
        if table_name in self._table_way_bits:
            return self._table_way_bits[table_name]
        sym = self.symtab.lookup(table_name)
        if sym is None or sym.decl is None:
            self._table_way_bits[table_name] = 0
            return 0
        if not hasattr(sym.decl, 'num_entries'):
            self._table_way_bits[table_name] = 0
            return 0
        my_entries = sym.decl.num_entries
        # Look for a table with the same prefix stem and 1/4 the entries
        for other_name, other_sym in self.symtab.symbols.items():
            if other_sym.kind != "table":
                continue
            if other_name == table_name:
                continue
            if not hasattr(other_sym.decl, 'num_entries'):
                continue
            # Check if names share a common prefix
            if table_name.startswith(other_name) or other_name.startswith(table_name):
                other_entries = other_sym.decl.num_entries
                if my_entries == other_entries * 4:
                    # 4-way set-associative
                    way_bits = 2
                    self._table_way_bits[table_name] = way_bits
                    return way_bits
        # Default: single-way (way bits = 0)
        self._table_way_bits[table_name] = 0
        return 0

    # ==================================================================
    # generate
    # ==================================================================

    def _pre_scan_var_widths(self) -> None:
        """Pre-scan the entire AST to infer variable bit-widths from assignments.
        
        This is called once before code generation to ensure that variable widths
        are available when generating concat expressions across function boundaries.
        """
        if self.ast.model is None:
            return
        
        def scan_stmt(stmt) -> None:
            if stmt is None:
                return
            if isinstance(stmt, AssignStmt):
                # Case 1: LHS is x[hi:lo] = rhs → x has width hi-lo+1
                if isinstance(stmt.lhs, BitSliceExpr) and isinstance(stmt.lhs.base, IdentifierExpr):
                    w = stmt.lhs.hi_bit - stmt.lhs.lo_bit + 1
                    self._track_var_width(stmt.lhs.base.name, w)
                # Case 2: LHS is plain variable, RHS is BITFIELD_GET (BitSliceExpr)
                elif isinstance(stmt.lhs, IdentifierExpr) and isinstance(stmt.rhs, BitSliceExpr):
                    w = stmt.rhs.hi_bit - stmt.rhs.lo_bit + 1
                    self._track_var_width(stmt.lhs.name, w)
                # Case 3: LHS is plain variable, RHS is ConcatExpr
                elif isinstance(stmt.lhs, IdentifierExpr) and isinstance(stmt.rhs, ConcatExpr):
                    w = self._get_bit_width(stmt.rhs)
                    if w is not None:
                        self._track_var_width(stmt.lhs.name, w)
            if isinstance(stmt, CompoundStmt):
                for s in stmt.stmts:
                    scan_stmt(s)
            if isinstance(stmt, IfStmt):
                scan_stmt(stmt.then_stmt)
                scan_stmt(stmt.else_stmt)
            if isinstance(stmt, WhileStmt):
                scan_stmt(stmt.body)
            if isinstance(stmt, ForStmt):
                scan_stmt(stmt.body)
            if isinstance(stmt, SwitchStmt):
                for cs in stmt.cases:
                    scan_stmt(cs)
            if isinstance(stmt, CaseStmt):
                scan_stmt(stmt.stmt)
            if isinstance(stmt, (FunctionDef, ProcessDef)):
                scan_stmt(stmt.body)

        for func in self.ast.model.functions:
            scan_stmt(func)
        for proc in self.ast.model.processes:
            scan_stmt(proc)

    def generate(self) -> str:
        """Return the complete .c file as a string."""
        # Pre-scan to collect variable bit-widths before code generation
        self._pre_scan_var_widths()

        buf: List[str] = []

        # headers
        buf.append('#include "reg_drv.h"')
        buf.append("#include <stdint.h>")
        buf.append("#include <string.h>")
        buf.append("")
        buf.append("/* =================================================== */")
        buf.append("/*  8m auto-generated C code                             */")
        buf.append("/* =================================================== */")
        buf.append("")
        buf.append("")
        buf.append("#define FIELD_INDEX_GET(parent, field, idx) \\")
        buf.append("    ((idx) == 0 ? (parent).field##0 : \\")
        buf.append("     (idx) == 1 ? (parent).field##1 : \\")
        buf.append("     (idx) == 2 ? (parent).field##2 : \\")
        buf.append("     (parent).field##3)")
        buf.append("")
        buf.append("/* External placeholder functions */")
        buf.append("static inline uint32_t hash1(uint32_t v) { return v % 512; }")
        buf.append('#define Max(a, b) ((a) > (b) ? (a) : (b))')
        buf.append('#define Max3(a, b, c) Max(Max(a, b), c)')
        buf.append("void enqueue_packet(void *pkt, int len) {}")
        buf.append("void send_packet(void *pkt, int len) {}")
        buf.append("")
        buf.append("/* Global packet buffer */")
        buf.append("extern uint8_t PacketByte[512];")
        buf.append("")
        buf.append("static inline uint64_t _concat_range(uint32_t s, uint32_t e) {")
        buf.append("    uint64_t result = 0;")
        buf.append("    for (uint32_t i = s; i <= e; i++)")
        buf.append("        result = (result << 8) | PacketByte[i];")
        buf.append("    return result;")
        buf.append("}")
        buf.append("")

        # structs
        if hasattr(self.ast, 'structs') and self.ast.structs:
            for sdef in self.ast.structs:
                buf.extend(self._gen_struct(sdef))

        # ---- collect all 表读取 entry variables across ALL functions/processes ----
        all_global_tables: "dict[str, str]" = {}  #  var_name → entry_type
        if self.ast.model is not None:
            for func in self.ast.model.functions:
                self._collect_table_read_types(func.body, all_global_tables)
            for proc in self.ast.model.processes:
                self._collect_table_read_types(proc.body, all_global_tables)
        # Also add DsDestPort (special egress variable)
        all_global_tables.setdefault("DsDestPort", "DsPort_entry_t")

        # ---- declare 表读取 entry variables as GLOBAL (file scope) ----
        if all_global_tables:
            buf.append("/* Global table-read entry variables */")
            for vname in sorted(all_global_tables.keys()):
                entry_type = all_global_tables[vname]
                buf.append(f"{entry_type} {vname};")
            buf.append("")

        # ---- collect ALL cross-function shared variables ----
        # Variables that appear in >1 function must be global (not local)
        cross_func_vars: set[str] = set()
        if self.ast.model is not None:
            func_names: "dict[str, set[str]]" = {}
            for func in self.ast.model.functions:
                names: set[str] = set()
                if func.body is not None:
                    self._walk_collect_names(func.body, names)
                # Filter: only user-defined identifiers (not built-in/C keywords)
                names = {n for n in names if " " not in n and not n.startswith("_")}
                func_names[func.name] = names
            # Find names used in >1 function
            all_names: "dict[str, int]" = {}
            for names in func_names.values():
                for n in names:
                    all_names[n] = all_names.get(n, 0) + 1
            for n, cnt in all_names.items():
                if cnt > 1:
                    cross_func_vars.add(n)

        # Also add well-known shared variables that may not be in symbol table
        cross_func_vars.update({
            "piSrcPort", "piPktLength", "piDestPort",
            "piVlanId", "piPrior", "piOutNoVlan", "piPktTagged",
            "piIsLoopDetect", "piLoopTtl",
        })

        # Remove names that are already global table entries, registers, or PacketByte variants
        cross_func_vars -= set(all_global_tables.keys())
        cross_func_vars -= {"PacketByte", "PacketByte0", "PacketByte5", "PacketByte6",
                            "PacketByte11", "PacketByte12", "PacketByte13"}
        # Remove PacketByte<N> pattern names
        cross_func_vars = {n for n in cross_func_vars if self._is_packet_byte_index(n) is None}
        # Remove register/table names (identifiers ending in Ctl, or known register names)
        _KNOWN_REGISTERS = {
            "L2AgingCtl", "L2LearnCtl", "LoopDetectCtl", "MirrorCtl",
            "PriorAssignCtl", "StormCfgCtl", "VlanIdCamCtl",
        }
        cross_func_vars -= _KNOWN_REGISTERS
        # Remove names that match table entry types
        cross_func_vars = {n for n in cross_func_vars if not n.startswith("Ds") or n in {
            "DsDestPort", "DsMacFwd", "DsMacLrn", "DsMacAing",
        }}

        if cross_func_vars:
            buf.append("/* Cross-function shared variables (parser → switchX → egress) */")
            for vname in sorted(cross_func_vars):
                ct = "uint64_t" if _KNOWN_VAR_WIDTHS.get(vname, 0) > 32 else "uint32_t"
                buf.append(f"{ct} {vname} = 0;")
            buf.append("")

        # Store for later use in _gen_function / _gen_process_tick
        self._cross_func_vars = cross_func_vars

        # forward declarations
        if self.ast.model is not None:
            for proc in self.ast.model.processes:
                buf.append(f"void {proc.name}_tick(void);")
            for func in self.ast.model.functions:
                if func.name == "parser":
                    params_str = "uint8_t *PacketByte"
                else:
                    params_str = ", ".join(f"uint8_t {p.name}" for p in func.params) if func.params else "void"
                buf.append(f"void {func.name}({params_str});")
            buf.append("")

        # functions
        if self.ast.model is not None:
            for func in self.ast.model.functions:
                buf.extend(self._gen_function(func))
            for proc in self.ast.model.processes:
                buf.extend(self._gen_process_tick(proc))

        return "\n".join(buf) + "\n"

    # ==================================================================
    # 缩进辅助
    # ==================================================================

    def _indent(self, code: str, level: int = 1) -> str:
        prefix = "    " * (self._indent_level + level)
        return prefix + code

    # ==================================================================
    # Type mapping
    # ==================================================================

    def _type_to_c(self, t: Optional[Type]) -> str:
        """Map AST type to C type string."""
        if isinstance(t, BitVectorType):
            w = t.width
            if w <= 8:
                return "uint8_t"
            elif w <= 16:
                return "uint16_t"
            elif w <= 32:
                return "uint32_t"
            elif w <= 64:
                return "uint64_t"
            return "uint64_t"
        if isinstance(t, BoolType):
            return "uint8_t"
        if isinstance(t, StructType):
            return f"{t.name}_t"
        return "uint32_t"

    # ==================================================================
    # Struct generation
    # ==================================================================

    def _gen_struct(self, sdef: StructDef) -> List[str]:
        lines: List[str] = []
        lines.append(f"typedef struct {{")
        for f in sdef.fields:
            ct = self._type_to_c(f.field_type)
            lines.append(f"    {ct} {f.name};")
        lines.append(f"}} {sdef.name}_t;")
        lines.append("")
        return lines

    # ==================================================================
    # 函数生成
    # ==================================================================

    def _gen_function(self, func: FunctionDef) -> List[str]:
        lines: List[str] = []
        ret = self._type_to_c(func.return_type) if func.return_type else "void"
        # parser function takes 包缓冲区 pointer
        if func.name == "parser":
            params = "uint8_t *PacketByte"
        else:
            params = ", ".join(f"uint8_t {p.name}" for p in func.params)
        lines.append(f"{ret} {func.name}({params}) {{")
        self._indent_level += 1

        # Step 1: collect all VarDeclStmt names (recursively)
        all_var_decl_names: set[str] = set()
        if func.body is not None:
            self._collect_all_var_names(func.body, all_var_decl_names)

        # Remove cross-function globals from local var-decls (already declared global)
        if hasattr(self, '_cross_func_vars'):
            all_var_decl_names -= self._cross_func_vars

        # Step 2: collect all TableReadStmt target_var names + types
        table_read_names: set[str] = set()
        table_target_types: "dict[str, str]" = {}
        if func.body is not None:
            self._collect_table_read_names(func.body, table_read_names)
            self._collect_table_read_types(func.body, table_target_types)

        # Step 3: compute undeclared, excluding params + 变量声明 + 表读取 names
        declared_in_body: set[str] = set()
        for p in func.params:
            declared_in_body.add(p.name)
        declared_in_body |= all_var_decl_names
        declared_in_body |= table_read_names

        undeclared: set[str] = set()
        if func.body is not None:
            undeclared = self._collect_undeclared(func.body)
            undeclared -= declared_in_body
            undeclared -= table_read_names
            undeclared = {n for n in undeclared if " " not in n}

        # egress special: PacketByte is an array, DsPort/DsDestPort are now GLOBAL
        if func.name == "egress":
            if "PacketByte" in undeclared:
                undeclared.discard("PacketByte")
            if "DsDestPort" in undeclared:
                undeclared.discard("DsDestPort")
            if "DsPort" in undeclared:
                undeclared.discard("DsPort")

        # Step 4: promote all VarDeclStmt variables to function top
        for vname in sorted(all_var_decl_names):
            lines.append(self._indent(f"uint32_t {vname} = 0; /* var-decl */"))

        # Step 4b: 表读取 entry variables are now GLOBAL — skip local declaration

        # Step 5: declare 自动声明 variables
        for vname in sorted(undeclared):
            lines.append(self._indent(f"uint32_t {vname} = 0; /* auto-declared */"))

        # Step 6: record all declared names for _gen_var_decl dedup
        self._declared_vars = set()
        self._declared_vars |= all_var_decl_names
        self._declared_vars |= undeclared

        # Step 7: generate body (VarDeclStmt → assignment-only if already declared)
        if func.body is not None:
            for s in func.body.stmts:
                lines.append(self._indent(self._gen_statement(s)))
        self._indent_level -= 1
        lines.append("}")
        lines.append("")
        return lines

    # ==================================================================
    # Process → tick function
    # ==================================================================

    def _gen_process_tick(self, proc: ProcessDef) -> List[str]:
        """Convert process to tick function with optional FSM."""
        lines: List[str] = []
        lines.append(f"void {proc.name}_tick(void) {{")
        self._indent_level += 1
        self._in_process = True
        self._process_vars = {}  #  reset per-process variable registry

        # collect static variables
        static_vars = self._collect_static_vars(proc.body)

        # collect VarDeclStmt names (recursively)
        all_pvar_names: set[str] = set()
        if proc.body is not None:
            self._collect_all_var_names(proc.body, all_pvar_names)
        all_pvar_names -= set(static_vars.keys())  #  exclude already-static

        # collect & declare undeclared variables (as static in process)
        undeclared: set[str] = set()
        if proc.body is not None:
            undeclared = self._collect_undeclared(proc.body)
            undeclared -= set(static_vars.keys())
            undeclared -= all_pvar_names
            undeclared = {n for n in undeclared if " " not in n}

        for vname in sorted(undeclared):
            lines.append(self._indent(f"static uint32_t {vname} = 0; /* auto-declared */"))

        # promote VarDeclStmt variables (static, since process)
        for vname in sorted(all_pvar_names):
            lines.append(self._indent(f"static uint32_t {vname} = 0; /* var-decl */"))
        self._process_vars.update({n: "uint32_t" for n in all_pvar_names})

        # 表读取 entry variables are now GLOBAL — skip local declaration

        # detect nested while loops for FSM
        has_nested_while = self._has_nested_while(proc.body)
        if has_nested_while:
            lines.append(self._indent("static int _state = 0;"))
            for vname, vtype in static_vars.items():
                lines.append(self._indent(f"static {vtype} {vname} = 0;"))
                self._process_vars[vname] = vtype
            lines.append(self._indent("switch (_state) {"))
            self._indent_level += 1
            lines.extend(self._gen_fsm_body(proc.body, static_vars))
            self._indent_level -= 1
            lines.append(self._indent("}"))
        else:
            for vname, vtype in static_vars.items():
                lines.append(self._indent(f"static {vtype} {vname} = 0;"))
                self._process_vars[vname] = vtype
            # simple tick: remove outer while(1)
            if (proc.body is not None and len(proc.body.stmts) == 1 and
                    isinstance(proc.body.stmts[0], WhileStmt)):
                wstmt = proc.body.stmts[0]
                if isinstance(wstmt.body, CompoundStmt):
                    for s in wstmt.body.stmts:
                        lines.append(self._indent(self._gen_statement(s)))
                else:
                    lines.append(self._indent(self._gen_statement(wstmt.body)))
            elif proc.body is not None:
                for s in proc.body.stmts:
                    lines.append(self._indent(self._gen_statement(s)))

        self._in_process = False
        self._indent_level -= 1
        lines.append("}")
        lines.append("")
        return lines

    def _has_nested_while(self, stmt: Optional[Stmt]) -> bool:
        """Check if a statement tree contains a while inside a while."""
        if stmt is None:
            return False
        if isinstance(stmt, CompoundStmt):
            return any(self._has_nested_while(s) for s in stmt.stmts)
        if isinstance(stmt, WhileStmt):
            if stmt.body is not None:
                if self._has_while_inside(stmt.body):
                    return True
            return False
        if isinstance(stmt, (IfStmt, ForStmt)):
            # check body
            pass
        return False

    def _has_while_inside(self, stmt: Optional[Stmt]) -> bool:
        """Check if there's any WhileStmt inside this statement."""
        if stmt is None:
            return False
        if isinstance(stmt, WhileStmt):
            return True
        if isinstance(stmt, CompoundStmt):
            return any(self._has_while_inside(s) for s in stmt.stmts)
        if isinstance(stmt, IfStmt):
            return (self._has_while_inside(stmt.then_stmt) or
                    self._has_while_inside(stmt.else_stmt))
        if isinstance(stmt, ForStmt):
            return self._has_while_inside(stmt.body)
        return False

    # ==================================================================
    # VarDecl / TableRead name collection (recursive, for promotion)
    # ==================================================================

    def _collect_all_var_names(self, stmt: "Optional[Stmt]", names: "set[str]") -> None:
        """Recursively collect all VarDeclStmt names in a statement tree."""
        if stmt is None:
            return
        if isinstance(stmt, VarDeclStmt):
            names.add(stmt.name)
        elif isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                self._collect_all_var_names(s, names)
        elif isinstance(stmt, IfStmt):
            self._collect_all_var_names(stmt.then_stmt, names)
            self._collect_all_var_names(stmt.else_stmt, names)
        elif isinstance(stmt, WhileStmt):
            self._collect_all_var_names(stmt.body, names)
        elif isinstance(stmt, ForStmt):
            self._collect_all_var_names(stmt.body, names)
        elif isinstance(stmt, SwitchStmt):
            for cs in stmt.cases:
                self._collect_all_var_names(cs.stmt, names)
        elif isinstance(stmt, CaseStmt):
            self._collect_all_var_names(stmt.stmt, names)

    def _collect_table_read_names(self, stmt: "Optional[Stmt]", names: "set[str]") -> None:
        """Recursively collect all TableReadStmt target_var names."""
        if stmt is None:
            return
        if isinstance(stmt, TableReadStmt):
            names.add(stmt.target_var)
        elif isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                self._collect_table_read_names(s, names)
        elif isinstance(stmt, IfStmt):
            self._collect_table_read_names(stmt.then_stmt, names)
            self._collect_table_read_names(stmt.else_stmt, names)
        elif isinstance(stmt, WhileStmt):
            self._collect_table_read_names(stmt.body, names)
        elif isinstance(stmt, ForStmt):
            self._collect_table_read_names(stmt.body, names)
        elif isinstance(stmt, SwitchStmt):
            for cs in stmt.cases:
                self._collect_table_read_names(cs.stmt, names)
        elif isinstance(stmt, CaseStmt):
            self._collect_table_read_names(stmt.stmt, names)

    def _collect_table_read_types(self, stmt: "Optional[Stmt]", types: "dict[str, str]") -> None:
        """Recursively collect TableReadStmt target_var → entry_type mapping."""
        if stmt is None:
            return
        if isinstance(stmt, TableReadStmt):
            actual_table = _TABLE_ALIASES.get(stmt.table_name, stmt.table_name)
            entry_type = f"{actual_table}_entry_t"
            types[stmt.target_var] = entry_type
        elif isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                self._collect_table_read_types(s, types)
        elif isinstance(stmt, IfStmt):
            self._collect_table_read_types(stmt.then_stmt, types)
            self._collect_table_read_types(stmt.else_stmt, types)
        elif isinstance(stmt, WhileStmt):
            self._collect_table_read_types(stmt.body, types)
        elif isinstance(stmt, ForStmt):
            self._collect_table_read_types(stmt.body, types)
        elif isinstance(stmt, SwitchStmt):
            for cs in stmt.cases:
                self._collect_table_read_types(cs.stmt, types)
        elif isinstance(stmt, CaseStmt):
            self._collect_table_read_types(stmt.stmt, types)

    # ==================================================================
    # VarDecl name collection (to avoid redeclaration in processes)
    # ==================================================================

    def _collect_local_names(self, stmt: "Optional[Stmt]", names: "set[str]") -> None:
        """Collect variable names from VarDeclStmt nodes in a statement tree."""
        if stmt is None:
            return
        if isinstance(stmt, VarDeclStmt):
            names.add(stmt.name)
        elif isinstance(stmt, TableReadStmt):
            names.add(stmt.target_var)
        elif isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                self._collect_local_names(s, names)
        elif isinstance(stmt, IfStmt):
            self._collect_local_names(stmt.then_stmt, names)
            self._collect_local_names(stmt.else_stmt, names)
        elif isinstance(stmt, WhileStmt):
            self._collect_local_names(stmt.body, names)
        elif isinstance(stmt, ForStmt):
            self._collect_local_names(stmt.body, names)
        elif isinstance(stmt, SwitchStmt):
            for cs in stmt.cases:
                self._collect_local_names(cs.stmt, names)
        elif isinstance(stmt, CaseStmt):
            self._collect_local_names(stmt.stmt, names)

    # ==================================================================
    # Undeclared variable collection
    # ==================================================================

    def _collect_undeclared(self, stmt: "Optional[Stmt]") -> "set[str]":
        """Collect identifiers used in *stmt* that are not in the symbol table."""
        names: set[str] = set()
        if stmt is None:
            return names
        self._walk_collect_names(stmt, names)
        # filter out already-declared symbols
        declared: set[str] = set()
        for n in names:
            sym = self.symtab.lookup(n)
            if sym is not None:
                declared.add(n)
            # known external / table-array names
            if n.endswith("_mem") or n in (
                "PacketByte", "hash1", "enqueue_packet", "send_packet",
            ):
                declared.add(n)
            # PacketByte<N> identifiers are array element references, not variables
            if self._is_packet_byte_index(n) is not None:
                declared.add(n)
            # Cross-function shared variables (already declared global)
            if hasattr(self, '_cross_func_vars') and n in self._cross_func_vars:
                declared.add(n)
        # filter out multi-word identifiers (natural-language residue from hw primitives)
        names = {n for n in names if " " not in n}
        # 自动纠正 common typo: PacketBypte → PacketByte, DsMacAing → DsMacAging
        if "PacketBypte" in names:
            names.discard("PacketBypte")
            names.add("PacketByte")
        if "DsMacAing" in names:
            names.discard("DsMacAing")
            names.add("DsMacAging")
        return names - declared

    def _walk_collect_names(self, node: Any, names: set[str]) -> None:
        """Recursively collect all IdentifierExpr names from an AST subtree."""
        if node is None:
            return
        if isinstance(node, IdentifierExpr):
            name = node.name
            if name in _NAME_CORRECTIONS:
                name = _NAME_CORRECTIONS[name]
            names.add(name)
            return
        if isinstance(node, (IntLiteral, HexLiteral, BinLiteral, str, int, bool)):
            return
        if isinstance(node, list):
            for item in node:
                self._walk_collect_names(item, names)
            return
        # Collect VarDeclStmt names (which are strings, skipped by the check above)
        from compiler.parser.ast_nodes import VarDeclStmt, AssignStmt
        if isinstance(node, VarDeclStmt):
            names.add(node.name)
            if node.init is not None:
                self._walk_collect_names(node.init, names)
            if node.var_type is not None:
                self._walk_collect_names(node.var_type, names)
            return
        # Collect AssignStmt LHS names
        if isinstance(node, AssignStmt):
            if isinstance(node.lhs, IdentifierExpr):
                names.add(node.lhs.name)
            self._walk_collect_names(node.lhs, names)
            self._walk_collect_names(node.rhs, names)
            return
        # dataclass or other object with __dict__
        if hasattr(node, "__dataclass_fields__"):
            for fname in node.__dataclass_fields__:
                val = getattr(node, fname, None)
                if val is not None:
                    self._walk_collect_names(val, names)
        elif hasattr(node, "__dict__"):
            for val in vars(node).values():
                self._walk_collect_names(val, names)

    # ==================================================================
    # Static variable collection
    # ==================================================================

    def _collect_static_vars(self, body: Optional[Stmt]) -> Dict[str, str]:
        vars_: Dict[str, str] = {}
        if body is None:
            return vars_
        self._walk_for_vars(body, vars_)
        return vars_

    def _walk_for_vars(self, stmt: Stmt, vars_: Dict[str, str]) -> None:
        if isinstance(stmt, VarDeclStmt):
            ct = self._type_to_c(stmt.var_type) if stmt.var_type else "uint32_t"
            vars_[stmt.name] = ct
        elif isinstance(stmt, AssignStmt):
            if isinstance(stmt.lhs, IdentifierExpr):
                name = stmt.lhs.name
                if name not in vars_:
                    vars_[name] = "uint32_t"
        elif isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                self._walk_for_vars(s, vars_)
        elif isinstance(stmt, (IfStmt,)):
            self._walk_for_vars(stmt.then_stmt, vars_)
            if stmt.else_stmt:
                self._walk_for_vars(stmt.else_stmt, vars_)
        elif isinstance(stmt, WhileStmt):
            if stmt.body:
                self._walk_for_vars(stmt.body, vars_)
        elif isinstance(stmt, ForStmt):
            if stmt.body:
                self._walk_for_vars(stmt.body, vars_)

    def _gen_fsm_body(self, stmt: Optional[Stmt], static_vars: Dict[str, str]) -> List[str]:
        """Generate FSM case blocks for nested while loops."""
        lines: List[str] = []
        if stmt is None:
            return lines
        if isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                lines.extend(self._gen_fsm_statement(s, static_vars))
        else:
            lines.extend(self._gen_fsm_statement(stmt, static_vars))
        return lines

    def _gen_fsm_statement(self, stmt: Stmt, static_vars: Dict[str, str]) -> List[str]:
        lines: List[str] = []
        if isinstance(stmt, WhileStmt):
            state_id = self._fsm_state
            self._fsm_state += 1
            lines.append(self._indent(f"case {state_id}:", level=0))
            self._indent_level += 1
            if stmt.cond is not None:
                cond_c = self._gen_expr(stmt.cond)
                if cond_c == "1":
                    # while(1) → run body, stay in same state
                    if stmt.body is not None:
                        lines.extend(self._gen_fsm_body(stmt.body, static_vars))
                    # stay in this state
                else:
                    # while(cond) → check condition
                    next_state = self._fsm_state
                    lines.append(self._indent(f"if (!({cond_c})) {{ _state = {next_state}; break; }}"))
                    self._fsm_state += 1
                    if stmt.body is not None:
                        if isinstance(stmt.body, CompoundStmt):
                            for bs in stmt.body.stmts:
                                lines.append(self._indent(self._gen_statement(bs)))
                        else:
                            lines.append(self._indent(self._gen_statement(stmt.body)))
                    lines.append(self._indent(f"break; /* stay in state {state_id} next tick */"))
            # store the state transition
            self._indent_level -= 1
            return lines
        if isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                lines.extend(self._gen_fsm_statement(s, static_vars))
            return lines
        if isinstance(stmt, IfStmt):
            cond_c = self._gen_expr(stmt.cond)
            lines.append(self._indent(f"if ({cond_c}) {{"))
            self._indent_level += 1
            lines.extend(self._gen_fsm_body(stmt.then_stmt, static_vars))
            self._indent_level -= 1
            if stmt.else_stmt:
                lines.append(self._indent("} else {"))
                self._indent_level += 1
                lines.extend(self._gen_fsm_body(stmt.else_stmt, static_vars))
                self._indent_level -= 1
            lines.append(self._indent("}"))
            return lines
        # default: just generate the statement
        lines.append(self._indent(self._gen_statement(stmt)))
        return lines

    # ==================================================================
    # Statement generation
    # ==================================================================

    def _gen_statement(self, stmt: Stmt) -> str:
        """Dispatch to specific statement generators."""
        if isinstance(stmt, CompoundStmt):
            return self._gen_compound(stmt)
        if isinstance(stmt, IfStmt):
            return self._gen_if(stmt)
        if isinstance(stmt, WhileStmt):
            return self._gen_while(stmt)
        if isinstance(stmt, ForStmt):
            return self._gen_for(stmt)
        if isinstance(stmt, SwitchStmt):
            return self._gen_switch(stmt)
        if isinstance(stmt, CaseStmt):
            return self._gen_case(stmt)
        if isinstance(stmt, AssignStmt):
            return self._gen_assign(stmt)
        if isinstance(stmt, CompoundAssignStmt):
            return self._gen_compound_assign(stmt)
        if isinstance(stmt, IncDecStmt):
            return self._gen_inc_dec(stmt)
        if isinstance(stmt, VarDeclStmt):
            return self._gen_var_decl(stmt)
        if isinstance(stmt, TableReadStmt):
            return self._gen_table_read(stmt)
        if isinstance(stmt, TableWriteStmt):
            return self._gen_table_write(stmt)
        if isinstance(stmt, DelayStmt):
            return self._gen_delay(stmt)
        if isinstance(stmt, ReplaceStmt):
            return self._gen_replace(stmt)
        if isinstance(stmt, InsertStmt):
            return self._gen_insert(stmt)
        if isinstance(stmt, RemoveStmt):
            return self._gen_remove(stmt)
        if isinstance(stmt, SendStmt):
            return self._gen_send(stmt)
        if isinstance(stmt, EnqueueStmt):
            return self._gen_enqueue(stmt)
        if isinstance(stmt, ReturnStmt):
            return self._gen_return(stmt)
        if isinstance(stmt, BreakStmt):
            return "break;"
        if isinstance(stmt, ExprStmt):
            return self._gen_expr(stmt.expr) + ";"
        return "/* TODO: " + type(stmt).__name__ + " */;"

    # ------------------------------------------------------------------
    # Compound
    # ------------------------------------------------------------------

    def _gen_compound(self, stmt: CompoundStmt) -> str:
        parts = ["{"]
        self._indent_level += 1
        for s in stmt.stmts:
            parts.append(self._indent(self._gen_statement(s)))
        self._indent_level -= 1
        parts.append(self._indent("}", level=0))
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # If / While / For
    # ------------------------------------------------------------------

    def _gen_if(self, stmt: IfStmt) -> str:
        cond = self._gen_expr(stmt.cond)
        then_s = self._gen_statement(stmt.then_stmt)
        if stmt.else_stmt:
            else_s = self._gen_statement(stmt.else_stmt)
            return f"if ({cond}) {then_s} else {else_s}"
        return f"if ({cond}) {then_s}"

    def _gen_while(self, stmt: WhileStmt) -> str:
        cond = self._gen_expr(stmt.cond)
        body = self._gen_statement(stmt.body) if stmt.body else ";"
        return f"while ({cond}) {body}"

    def _gen_for(self, stmt: ForStmt) -> str:
        init_c = self._gen_for_clause(stmt.init)
        cond_c = self._gen_expr(stmt.cond) if stmt.cond else ""
        incr_c = self._gen_for_clause(stmt.incr)
        body = self._gen_statement(stmt.body) if stmt.body else ";"
        return f"for ({init_c}; {cond_c}; {incr_c}) {body}"

    def _gen_for_clause(self, opt_stmt: Optional[Stmt]) -> str:
        """Generate a for-loop init/incr clause (no trailing semicolon)."""
        if opt_stmt is None:
            return ""
        if isinstance(opt_stmt, AssignStmt):
            lhs = self._gen_expr(opt_stmt.lhs)
            rhs = self._gen_expr(opt_stmt.rhs)
            return f"{lhs} = {rhs}"
        if isinstance(opt_stmt, IncDecStmt):
            op = opt_stmt.op
            operand = self._gen_expr(opt_stmt.operand)
            return f"{op}{operand}" if opt_stmt.prefix else f"{operand}{op}"
        if isinstance(opt_stmt, ExprStmt):
            return self._gen_expr(opt_stmt.expr)
        # 回退方案: strip trailing semicolon
        s = self._gen_statement(opt_stmt)
        return s.rstrip(";")

    # ------------------------------------------------------------------
    # Switch / Case
    # ------------------------------------------------------------------

    def _gen_switch(self, stmt: SwitchStmt) -> str:
        expr = self._gen_expr(stmt.expr)
        parts = [f"switch ({expr}) {{"]
        self._indent_level += 1
        for cs in stmt.cases:
            parts.append(self._indent(self._gen_case(cs)))
        self._indent_level -= 1
        parts.append(self._indent("}", level=0))
        return "\n".join(parts)

    def _gen_case(self, stmt: CaseStmt) -> str:
        if stmt.value is None:
            label = "default:"
        elif isinstance(stmt.value, RangeExpr):
            s_val = self._gen_expr(stmt.value.start)
            e_val = self._gen_expr(stmt.value.end)
            # Expand range into individual case labels for C99 compatibility
            # Only expand if range is small enough (<= 32 values)
            try:
                s_int = int(stmt.value.start.value) if hasattr(stmt.value.start, 'value') else None
                e_int = int(stmt.value.end.value) if hasattr(stmt.value.end, 'value') else None
            except (TypeError, ValueError):
                s_int = e_int = None
            if s_int is not None and e_int is not None and e_int - s_int <= 32:
                if isinstance(stmt.value.start, HexLiteral):
                    cases = [f"case 0x{v:x}:" for v in range(s_int, e_int + 1)]
                else:
                    cases = [f"case {v}:" for v in range(s_int, e_int + 1)]
                label = " ".join(cases)
            else:
                label = f"case {s_val} ... {e_val}:"  #  GCC extension 回退方案
        else:
            label = f"case {self._gen_expr(stmt.value)}:"
        body = self._gen_statement(stmt.stmt) if stmt.stmt else ";"
        return f"{label} {body} break;"

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    def _gen_assign(self, stmt: AssignStmt) -> str:
        # Track variable widths from assignments
        self._track_width_from_assign(stmt)

        # FieldIndexExpr on LHS → switch/case assignment
        if isinstance(stmt.lhs, FieldIndexExpr):
            return self._gen_field_index_assign(stmt)

        # BitIndexExpr on LHS → BITFIELD_SET(base, idx, idx, rhs)
        if isinstance(stmt.lhs, BitIndexExpr):
            base = self._gen_expr(stmt.lhs.base)
            idx = self._gen_expr(stmt.lhs.index)
            rhs = self._gen_expr(stmt.rhs)
            return f"BITFIELD_SET({base}, {idx}, {idx}, {rhs});"

        lhs = self._gen_expr(stmt.lhs)
        rhs = self._gen_expr(stmt.rhs)

        # BITFIELD_SET when LHS is a BitSliceExpr
        if isinstance(stmt.lhs, BitSliceExpr):
            base = self._gen_expr(stmt.lhs.base)
            return f"BITFIELD_SET({base}, {stmt.lhs.hi_bit}, {stmt.lhs.lo_bit}, {rhs});"

        return f"{lhs} = {rhs};"

    def _track_width_from_assign(self, stmt: "AssignStmt") -> None:
        """Infer variable bit-width from the assignment statement."""
        # Case 1: LHS is x[hi:lo] = rhs → x has width hi-lo+1
        if isinstance(stmt.lhs, BitSliceExpr) and isinstance(stmt.lhs.base, IdentifierExpr):
            w = stmt.lhs.hi_bit - stmt.lhs.lo_bit + 1
            self._track_var_width(stmt.lhs.base.name, w)
            return
        # Case 2: LHS is plain variable, RHS is BITFIELD_GET (BitSliceExpr)
        if isinstance(stmt.lhs, IdentifierExpr):
            if isinstance(stmt.rhs, BitSliceExpr):
                w = stmt.rhs.hi_bit - stmt.rhs.lo_bit + 1
                self._track_var_width(stmt.lhs.name, w)
                return
            # Case 3: RHS is ConcatExpr → sum of known part widths
            if isinstance(stmt.rhs, ConcatExpr):
                w = self._get_bit_width(stmt.rhs)
                if w is not None:
                    self._track_var_width(stmt.lhs.name, w)
                return

    def _gen_compound_assign(self, stmt: CompoundAssignStmt) -> str:
        lhs = self._gen_expr(stmt.lhs)
        rhs = self._gen_expr(stmt.rhs)
        op = stmt.op  #  "+=", "-=", "&=", "|="
        return f"{lhs} {op} {rhs};"

    def _gen_inc_dec(self, stmt: IncDecStmt) -> str:
        op = stmt.op  #  "++" or "--"
        # If operand is a BitSliceExpr, generate read-modify-write
        if isinstance(stmt.operand, BitSliceExpr):
            base = self._gen_expr(stmt.operand.base)
            hi = stmt.operand.hi_bit
            lo = stmt.operand.lo_bit
            return (
                f"{{ uint32_t _tmp = BITFIELD_GET({base}, {hi}, {lo}); "
                f"_tmp{op}; "
                f"BITFIELD_SET({base}, {hi}, {lo}, _tmp); }}"
            )
        # If operand is a FieldIndexExpr, we can't inc/dec it directly
        if isinstance(stmt.operand, FieldIndexExpr):
            operand = self._gen_expr(stmt.operand)
            return f"{{ uint32_t _tmp = {operand}; _tmp{op}; /* TODO: write back */ }}"
        operand = self._gen_expr(stmt.operand)
        if stmt.prefix:
            return f"{op}({operand});"
        return f"({operand}){op};"

    # ------------------------------------------------------------------
    # 变量声明
    # ------------------------------------------------------------------

    def _gen_var_decl(self, stmt: VarDeclStmt) -> str:
        # already declared in this function → only emit assignment
        if stmt.name in self._declared_vars:
            if stmt.init:
                return f"{stmt.name} = {self._gen_expr(stmt.init)};"
            return ";"
        # in process context and already declared static → only emit assignment
        if self._in_process and stmt.name in self._process_vars:
            if stmt.init:
                init_val = self._gen_expr(stmt.init)
                return f"{stmt.name} = {init_val};"
            return f"/* {stmt.name} already declared static */;"
        # cross-function global variable → only emit assignment (no local decl)
        if hasattr(self, '_cross_func_vars') and stmt.name in self._cross_func_vars:
            if stmt.init:
                init_val = self._gen_expr(stmt.init)
                return f"{stmt.name} = {init_val};"
            return f"/* {stmt.name} is global */;"

        self._declared_vars.add(stmt.name)
        ct = self._type_to_c(stmt.var_type) if stmt.var_type else "uint32_t"
        if stmt.init:
            init_val = self._gen_expr(stmt.init)
            return f"{ct} {stmt.name} = {init_val};"
        return f"{ct} {stmt.name};"

    # ------------------------------------------------------------------
    # Table read / write
    # ------------------------------------------------------------------

    def _gen_table_read(self, stmt: TableReadStmt) -> str:
        """DsMac = DsMac Table[idx] → entry copy (variable declared at function top)."""
        idx = self._gen_table_index(stmt.table_name, stmt.index)
        actual_table = _TABLE_ALIASES.get(stmt.table_name, stmt.table_name)
        return (
            f"memcpy(&{stmt.target_var}, &{actual_table}_mem[{idx}], "
            f"sizeof({actual_table}_entry_t));"
        )

    def _gen_table_write(self, stmt: TableWriteStmt) -> str:
        """update Table using value at index."""
        val = self._gen_expr(stmt.value)
        actual_table = _TABLE_ALIASES.get(stmt.table_name, stmt.table_name)
        sym = self.symtab.lookup(actual_table)
        if sym is None or sym.kind != "table":
            for suffix in ("Lrn", "Fwd", "Dest"):
                if actual_table.endswith(suffix):
                    candidate = actual_table[:-len(suffix)]
                    if self.symtab.lookup(candidate):
                        actual_table = candidate
                        break
        idx = self._gen_table_index(actual_table, stmt.index)
        return (
            f"memcpy(&{actual_table}_mem[{idx}], &{val}, sizeof({actual_table}_entry_t));"
        )

    def _gen_table_index(self, table_name: str, index_expr: Expr) -> str:
        """Generate a C expression for a table memory index.
        
        Handles ConcatExpr indices for multi-way set-associative tables
        (e.g. DsMac with {hash, way}) by computing the correct bit shift
        from the table structure.
        """
        if isinstance(index_expr, ConcatExpr) and len(index_expr.parts) == 2:
            way_bits = self._infer_table_way_bits(table_name)
            if way_bits > 0:
                part0 = self._gen_expr(index_expr.parts[0])
                part1 = self._gen_expr(index_expr.parts[1])
                return f"((uint64_t)({part0}) << {way_bits}) | ({part1})"
        # Fall back to generic expression generation
        return self._gen_expr(index_expr)

    # ------------------------------------------------------------------
    # Delay
    # ------------------------------------------------------------------

    def _gen_delay(self, stmt: DelayStmt) -> str:
        cycles = self._gen_expr(stmt.cycles)
        return (
            f"static uint32_t _delay = 0;\n"
            f"{self._indent('if (_delay > 0) {{ _delay--; return; }}', level=0)}\n"
            f"{self._indent(f'_delay = {cycles};', level=0)}"
        )

    # ------------------------------------------------------------------
    # 硬件原语
    # ------------------------------------------------------------------

    def _gen_replace(self, stmt: ReplaceStmt) -> str:
        target = self._gen_expr(stmt.target)
        fb = self._gen_expr(stmt.from_byte)
        tb = self._gen_expr(stmt.to_byte)
        src = self._gen_expr(stmt.source)
        # If src is a compound expression (not a simple lvalue), use temp
        if self._is_simple_lvalue(stmt.source):
            return f"memcpy(&({target}[{fb}]), &({src}), ({tb})-({fb})+1);"
        else:
            return f"{{ uint64_t _tmp = {src}; memcpy(&({target}[{fb}]), &_tmp, ({tb})-({fb})+1); }}"

    def _is_simple_lvalue(self, expr: Expr) -> bool:
        """Check if an expression can have its address taken."""
        if isinstance(expr, IdentifierExpr):
            return True
        if isinstance(expr, FieldAccessExpr):
            return True
        if isinstance(expr, BitSliceExpr):
            return False
        if isinstance(expr, BitIndexExpr):
            return False
        if isinstance(expr, BinaryOpExpr):
            return False
        if isinstance(expr, ConcatExpr):
            return False
        if isinstance(expr, IntLiteral):
            return False
        if isinstance(expr, HexLiteral):
            return False
        return True

    def _gen_insert(self, stmt: InsertStmt) -> str:
        target = self._gen_expr(stmt.target)
        pos = self._gen_expr(stmt.position)
        val = self._gen_expr(stmt.value)
        return (
            f"memmove(&({target}[({pos})+sizeof({val})]), &({target}[{pos}]), "
            f"sizeof({target})-({pos})); "
            f"memcpy(&({target}[{pos}]), &({val}), sizeof({val}));"
        )

    def _gen_remove(self, stmt: RemoveStmt) -> str:
        target = self._gen_expr(stmt.target)
        fb = self._gen_expr(stmt.from_byte)
        tb = self._gen_expr(stmt.to_byte)
        return (
            f"memmove(&({target})[{fb}], &({target})[({tb})+1], "
            f"sizeof({target})-({tb})-1);"
        )

    def _gen_enqueue(self, stmt: EnqueueStmt) -> str:
        return 'enqueue_packet(NULL, 0); /* TODO */'

    def _gen_send(self, stmt: SendStmt) -> str:
        return 'send_packet(NULL, 0); /* TODO */'

    # ------------------------------------------------------------------
    # Return
    # ------------------------------------------------------------------

    def _gen_return(self, stmt: ReturnStmt) -> str:
        if stmt.expr:
            return f"return {self._gen_expr(stmt.expr)};"
        return "return;"

    # ==================================================================
    # 表达式生成
    # ==================================================================

    def _gen_expr(self, expr: Expr) -> str:
        """Translate an AST expression to a C expression string."""
        if isinstance(expr, IdentifierExpr):
            return self._resolve_name(expr.name)
        if isinstance(expr, IntLiteral):
            return str(expr.value)
        if isinstance(expr, HexLiteral):
            v = expr.value
            if expr.width is not None and expr.width > 0:
                hex_digits = (expr.width + 3) // 4
                return f"0x{v:0{hex_digits}x}"
            elif v == 0:
                return "0x0"
            else:
                hex_digits = (v.bit_length() + 3) // 4
                return f"0x{v:0{hex_digits}x}"
        if isinstance(expr, BinLiteral):
            return str(expr.value)
        if isinstance(expr, BinaryOpExpr):
            return self._gen_binary(expr)
        if isinstance(expr, UnaryOpExpr):
            return self._gen_unary(expr)
        if isinstance(expr, FieldAccessExpr):
            return self._gen_field_access(expr)
        if isinstance(expr, BitSliceExpr):
            return self._gen_bit_slice(expr)
        if isinstance(expr, BitIndexExpr):
            return self._gen_bit_index(expr)
        if isinstance(expr, FieldIndexExpr):
            return self._gen_field_index(expr)
        if isinstance(expr, CompositeFieldExpr):
            return self._gen_composite_field(expr)
        if isinstance(expr, ConcatExpr):
            return self._gen_concat(expr)
        if isinstance(expr, FunctionCallExpr):
            return self._gen_func_call(expr)
        if isinstance(expr, MaxMinExpr):
            return self._gen_maxmin(expr)
        if isinstance(expr, RangeExpr):
            return self._gen_range(expr)
        return f"/* TODO: {type(expr).__name__} */"

    # ------------------------------------------------------------------
    # Binary / Unary
    # ------------------------------------------------------------------

    def _gen_binary(self, expr: BinaryOpExpr) -> str:
        left = self._gen_expr(expr.left)
        right = self._gen_expr(expr.right)
        op = expr.op

        # == with CompositeFieldExpr → use helper comparison
        if op == "==":
            if isinstance(expr.left, CompositeFieldExpr) and isinstance(expr.right, ConcatExpr):
                return self._gen_composite_compare(expr.left, expr.right)

        if op == "?:":  #  outer ternary
            inner = expr.right
            if isinstance(inner, BinaryOpExpr) and inner.op == ":":
                return f"({left} ? {self._gen_expr(inner.left)} : {self._gen_expr(inner.right)})"
            return f"({left} ? /* TODO */ : /* TODO */)"
        if op == "<<":
            return f"((uint32_t)({left}) << ({right}))"
        if op == ">>":
            return f"((uint32_t)({left}) >> ({right}))"
        return f"({left} {op} {right})"

    def _gen_unary(self, expr: UnaryOpExpr) -> str:
        op = expr.op
        operand = self._gen_expr(expr.operand)
        if op.startswith("post"):
            actual_op = op[4:]  #  "++" or "--"
            # If operand is a BitSliceExpr, generate read-modify-write
            if isinstance(expr.operand, BitSliceExpr):
                base = self._gen_expr(expr.operand.base)
                hi = expr.operand.hi_bit
                lo = expr.operand.lo_bit
                return (
                    f"({{ uint32_t _tmp = BITFIELD_GET({base}, {hi}, {lo}); "
                    f"uint32_t _res = _tmp{actual_op}; "
                    f"BITFIELD_SET({base}, {hi}, {lo}, _tmp); _res; }})"
                )
            # If operand is a FieldIndexExpr, generate read-modify-write
            if isinstance(expr.operand, FieldIndexExpr):
                if isinstance(expr.operand.base, FieldAccessExpr):
                    parent = self._gen_expr(expr.operand.base.base)
                    field = expr.operand.base.field
                    idx_c = self._gen_expr(expr.operand.index) if expr.operand.index is not None else "0"
                    return (
                        f"({{ uint32_t _tmp = FIELD_INDEX_GET({parent}, {field}, {idx_c}); "
                        f"uint32_t _res = _tmp{actual_op}; "
                        f"switch ({idx_c} & 0x3) {{ "
                        f"case 0: {parent}.{field}0 = _tmp; break; "
                        f"case 1: {parent}.{field}1 = _tmp; break; "
                        f"case 2: {parent}.{field}2 = _tmp; break; "
                        f"case 3: {parent}.{field}3 = _tmp; break; }} _res; }})"
                    )
            return f"({operand}{actual_op})"
        return f"({op}{operand})"

    # ------------------------------------------------------------------
    # 字段访问 / 位切片 / 位索引
    # ------------------------------------------------------------------

    def _gen_field_access(self, expr: FieldAccessExpr) -> str:
        base = self._gen_expr(expr.base)
        field = expr.field
        # check field alias table
        if isinstance(expr.base, IdentifierExpr):
            full_key = f"{expr.base.name}.{field}"
            if full_key in _FIELD_ALIASES:
                field = _FIELD_ALIASES[full_key].split(".")[-1]
        if field in _C_KEYWORDS:
            field = "__" + field
        return f"{base}.{field}"

    def _gen_bit_slice(self, expr: BitSliceExpr) -> str:
        base = self._gen_expr(expr.base)
        return f"BITFIELD_GET({base}, {expr.hi_bit}, {expr.lo_bit})"

    def _gen_bit_index(self, expr: BitIndexExpr) -> str:
        base = self._gen_expr(expr.base)
        idx = self._gen_expr(expr.index)
        # PacketByte is an array → use array subscript, not bit shift
        if isinstance(expr.base, IdentifierExpr) and expr.base.name == "PacketByte":
            return f"{base}[{idx}]"
        # If base is a table name, access _mem array: DsMacValid[idx] → DsMacValid_mem[idx]
        if isinstance(expr.base, IdentifierExpr):
            sym = self.symtab.lookup(expr.base.name)
            if sym is not None and sym.kind == "table":
                actual_table = _TABLE_ALIASES.get(expr.base.name, expr.base.name)
                return f"{actual_table}_mem[{idx}]"
        return f"((({base}) >> ({idx})) & 1)"

    # ------------------------------------------------------------------
    # 字段索引（aging{idx}）
    # ------------------------------------------------------------------

    def _gen_field_index(self, expr: FieldIndexExpr) -> str:
        """aging{idx} -> FIELD_INDEX_GET macro."""
        if isinstance(expr.base, FieldAccessExpr):
            parent = self._gen_expr(expr.base.base)
            field = expr.base.field
            idx_c = self._gen_expr(expr.index) if expr.index is not None else "0"
            return f"FIELD_INDEX_GET({parent}, {field}, {idx_c})"
        # If base is a table name: DsMacValid{idx} → DsMacValid_mem[idx]
        if isinstance(expr.base, IdentifierExpr):
            sym = self.symtab.lookup(expr.base.name)
            if sym is not None and sym.kind == "table":
                actual_table = _TABLE_ALIASES.get(expr.base.name, expr.base.name)
                idx_c = self._gen_expr(expr.index) if expr.index is not None else "0"
                return f"{actual_table}_mem[{idx_c}]"
        return f"{self._gen_expr(expr.base)}"

    def _gen_field_index_assign(self, stmt: AssignStmt) -> str:
        """aging{idx} = val → switch(idx & 3) { case 0: aging0 = val; break; ... }"""
        fiexpr = stmt.lhs  #  FieldIndexExpr
        if isinstance(fiexpr.base, FieldAccessExpr):
            parent = self._gen_expr(fiexpr.base.base)
            field = fiexpr.base.field
            idx_c = self._gen_expr(fiexpr.index) if fiexpr.index is not None else "0"
            rhs = self._gen_expr(stmt.rhs)
            lines = [f"switch ({idx_c} & 0x3) {{"]
            for i in range(4):
                lines.append(f"    case {i}: {parent}.{field}{i} = {rhs}; break;")
            lines.append("}")
            return "\n".join(lines)
        # If base is a table name: DsMacValid{idx} = val → memcpy
        if isinstance(fiexpr.base, IdentifierExpr):
            sym = self.symtab.lookup(fiexpr.base.name)
            if sym is not None and sym.kind == "table":
                actual_table = _TABLE_ALIASES.get(fiexpr.base.name, fiexpr.base.name)
                idx_c = self._gen_expr(fiexpr.index) if fiexpr.index is not None else "0"
                rhs = self._gen_expr(stmt.rhs)
                return f"memcpy(&{actual_table}_mem[{idx_c}], &{rhs}, sizeof({actual_table}_entry_t));"
        return "/* FieldIndex assign */;"

    # ------------------------------------------------------------------
    # 复合字段（.{fid, macAddr}）
    # ------------------------------------------------------------------

    def _gen_composite_field(self, expr: CompositeFieldExpr) -> str:
        """DsMacKey.{fid{i}, macAddr{i}} → helper function calls."""
        base = self._gen_expr(expr.base)
        field_names = expr.fields
        if "macAddr" in field_names or "fid" in field_names:
            return f"/* {base} composite {{{', '.join(field_names)}}} — use DsMacKey_ helper */"
        return f"{base}"

    def _gen_composite_compare(self, composite: CompositeFieldExpr, concat: ConcatExpr) -> str:
        """DsMacKey.{fid, macAddr} == {giFid, prMacDa} → two helper comparisons."""
        base = self._gen_expr(composite.base)
        fields = composite.fields
        parts = concat.parts
        conds: List[str] = []
        for i, fname in enumerate(fields):
            if i < len(parts):
                part_c = self._gen_expr(parts[i])
                if fname.startswith("fid"):
                    conds.append(f"(DsMacKey_get_fid(&({base}), i) == ({part_c}))")
                elif fname.startswith("macAddr"):
                    conds.append(f"(DsMacKey_get_macAddr(&({base}), i) == ({part_c}))")
        if conds:
            return "(" + " && ".join(conds) + ")"
        return f"/* composite compare on {base} */"

    # ------------------------------------------------------------------
    # Concat
    # ------------------------------------------------------------------

    def _gen_concat(self, expr: ConcatExpr) -> str:
        """{a, b, c} → ((a) << N) | ((b) << M) | (c).
        
        Shift amounts are determined by the bit-widths of the right-side parts.
        When widths are unknown for a part, defaults to 8 (byte-level concat).
        """
        if not expr.parts:
            return "0"
        parts: List[str] = []
        part_widths: List[int] = []  #  bit widths of each part (0 = unknown)
        for p in expr.parts:
            if isinstance(p, RangeExpr):
                # Try to expand static range: PacketByte0..PacketByte5 → individual bytes
                expanded = self._expand_range(p)
                if expanded is not None:
                    parts.extend(expanded)
                    part_widths.extend([8] * len(expanded))  # each byte is 8 bits
                else:
                    parts.append(self._gen_dynamic_range(p))
                    part_widths.append(0)  # unknown width
            else:
                parts.append(self._gen_expr(p))
                w = self._get_bit_width(p)
                part_widths.append(w if w is not None else 0)
        if len(parts) == 1:
            return parts[0]
        result = parts[-1]
        shift = 0
        for i, p in enumerate(reversed(parts[:-1])):
            part_idx = len(parts) - 2 - i
            pw = part_widths[part_idx + 1] if part_idx + 1 < len(part_widths) else 0
            # Use actual width if known, otherwise default to byte-level (8)
            w = pw if pw > 0 else 8
            shift += w
            result = f"((uint64_t)({p}) << {shift}) | ({result})"
        return result

    # ------------------------------------------------------------------
    # 函数调用 / MaxMin
    # ------------------------------------------------------------------

    def _gen_func_call(self, expr: FunctionCallExpr) -> str:
        if expr.name == "parser" and not expr.args:
            return "parser(PacketByte)"
        args = ", ".join(self._gen_expr(a) for a in expr.args)
        return f"{expr.name}({args})"

    def _gen_maxmin(self, expr: MaxMinExpr) -> str:
        args = [self._gen_expr(a) for a in expr.args]
        if len(args) == 2:
            a, b = args
            op = ">" if expr.func == "max" else "<"
            return f"(({a}){op}({b})?({a}):({b}))"
        if len(args) == 3:
            a, b, c = args
            op = ">" if expr.func == "max" else "<"
            return f"(({a}){op}({b})?(({a}){op}({c})?({a}):({c})):(({b}){op}({c})?({b}):({c})))"
        return args[0] if args else "0"

    # ------------------------------------------------------------------
    # Range
    # ------------------------------------------------------------------

    def _gen_range(self, expr: RangeExpr) -> str:
        s = self._gen_expr(expr.start)
        e = self._gen_expr(expr.end)
        return f"/* range {s}..{e} */"

    def _expand_range(self, expr: "RangeExpr") -> "Optional[List[str]]":
        """
        Try to expand a RangeExpr into individual byte parts.
        
        Handles:
          PacketByte0..PacketByte5  → ["PacketByte[0]", "PacketByte[1]", ..., "PacketByte[5]"]
          PacketByte[offset+12]..PacketByte[offset+15] → None (dynamic, use _gen_dynamic_range)
          
        Returns None if expansion is not possible (dynamic range).
        """
        s_idx = None
        e_idx = None
        
        # Check if start is a static PacketByte<N>
        if isinstance(expr.start, IdentifierExpr):
            s_idx = self._is_packet_byte_index(expr.start.name)
        elif isinstance(expr.start, IntLiteral):
            s_idx = expr.start.value
        
        # Check if end is a static PacketByte<N>
        if isinstance(expr.end, IdentifierExpr):
            e_idx = self._is_packet_byte_index(expr.end.name)
        elif isinstance(expr.end, IntLiteral):
            e_idx = expr.end.value
        
        if s_idx is not None and e_idx is not None and s_idx <= e_idx:
            return [f"PacketByte[{i}]" for i in range(s_idx, e_idx + 1)]
        
        return None

    def _gen_dynamic_range(self, expr: "RangeExpr") -> str:
        """
        Generate code for a dynamic range like PacketByte[offset+12]..PacketByte[offset+15].
        Extracts the index expressions and calls _concat_range(start_idx, end_idx).
        """
        def _extract_index(e):
            """Extract the index expression from PacketByte[...] BitIndexExpr."""
            from compiler.parser.ast_nodes import BitIndexExpr, IdentifierExpr
            if isinstance(e, BitIndexExpr):
                base = e.base
                if isinstance(base, IdentifierExpr) and base.name == "PacketByte":
                    return self._gen_expr(e.index)
            # Try to resolve identifier to PacketByte[N]
            if isinstance(e, IdentifierExpr):
                idx = self._is_packet_byte_index(e.name)
                if idx is not None:
                    return str(idx)
            return self._gen_expr(e)
        
        start_idx = _extract_index(expr.start)
        end_idx = _extract_index(expr.end)
        return f"_concat_range({start_idx}, {end_idx})"
