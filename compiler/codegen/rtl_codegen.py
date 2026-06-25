"""
compiler/codegen/rtl_codegen.py
RTL (Verilog) 代码生成器 — 从8m AST生成可综合的Verilog RTL。
与 c_codegen.py 平级，共享同一套 AST 和符号表。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from compiler.parser.ast_nodes import (
    # Types
    BitVectorType, BoolType, StructType, ArrayType, Type,
    # Expressions
    IdentifierExpr, IntLiteral, BinLiteral, HexLiteral,
    BinaryOpExpr, UnaryOpExpr, FieldAccessExpr, BitSliceExpr,
    BitIndexExpr, FieldIndexExpr, CompositeFieldExpr, ConcatExpr,
    FunctionCallExpr, MaxMinExpr, RangeExpr, Expr,
    # Statements
    AssignStmt, CompoundAssignStmt, IncDecStmt,
    CompoundStmt, IfStmt, WhileStmt, ForStmt,
    SwitchStmt, CaseStmt, BreakStmt, ReturnStmt,
    VarDeclStmt, TableReadStmt, TableWriteStmt,
    DelayStmt, EnqueueStmt, ReplaceStmt, InsertStmt, RemoveStmt,
    SendStmt, ExprStmt, Stmt,
    # Top-level
    ProcessDef, FunctionDef, FieldDecl, MemTableDecl,
    RegisterDecl, RegMapDef, TranslationUnit, PseudoCModel,
)
from compiler.semantic.symbol_table import SymbolTable, Symbol


# ======================================================================
# RTLCodeGenerator
# ======================================================================

class RTLCodeGenerator:
    """从8m AST生成可综合的Verilog RTL代码。"""

    def __init__(self, ast: TranslationUnit, symbol_table: SymbolTable) -> None:
        self.ast = ast
        self.symtab = symbol_table
        self._indent_level: int = 0
        self._pipe_vars: Dict[str, str] = {}  # 流水线信号名 → 声明

    # ==================================================================
    # 入口
    # ==================================================================

    @staticmethod
    def _sanitize_module_name(name: str) -> str:
        """确保模块名不以数字开头。"""
        if name and name[0].isdigit():
            return "m" + name
        return name

    def generate(self) -> Dict[str, str]:
        """返回 {子路径: Verilog内容} 的字典。"""
        files: Dict[str, str] = {}
        model = self.ast.model
        reg_map = self.ast.reg_map

        if model is None:
            return files

        # ── 行为模块 → v_output/behavior/ ──
        if model.functions:
            for func in model.functions:
                safe = self._sanitize_module_name(f"m_{func.name}")
                files[f"v_output/behavior/{safe}.v"] = self._gen_function_module(func)

        if model.processes:
            for proc in model.processes:
                if proc.name == "forward":
                    files[f"v_output/behavior/m_forward.v"] = self._gen_pipeline_module(proc)
                else:
                    safe = self._sanitize_module_name(f"m_{proc.name}")
                    files[f"v_output/behavior/{safe}.v"] = self._gen_process_module(proc)

        # ── RAM 模块 → v_output/hardware/ ──
        if reg_map and reg_map.mem_tables:
            for tbl in reg_map.mem_tables:
                files[f"v_output/hardware/m_ram_wrap_{tbl.name}.v"] = self._gen_ram_wrapper(tbl)

        # ── 基础设施 → v_output/hardware/ ──
        if reg_map and reg_map.registers:
            files["v_output/hardware/m_reg_bank.v"] = self._gen_reg_bank(reg_map.registers)
        if reg_map:
            files["v_output/hardware/m_reg_decode.v"] = self._gen_addr_decode(reg_map)

        # ── 顶层模块 → v_output/ 根目录 ──
        files["v_output/m_switch_top.v"] = self._gen_top_module(model, reg_map)

        return files

    # ==================================================================
    # 顶层模块
    # ==================================================================

    def _gen_top_module(self, model: PseudoCModel, reg_map: Optional[RegMapDef]) -> str:
        """生成顶层模块 m_switch_top。"""
        lines: List[str] = []
        lines.append("module m_switch_top (")
        lines.append("    input  wire        clk,")
        lines.append("    input  wire        rst_n,")
        lines.append("")
        lines.append("    // 寄存器总线接口")
        lines.append("    input  wire [17:2]  reg_addr,")
        lines.append("    input  wire [31:0]  reg_wr_data,")
        lines.append("    input  wire         reg_wr_en,")
        lines.append("    output wire [31:0]  reg_rd_data")
        lines.append(");")
        lines.append("")

        # 函数子模块例化
        for func in model.functions:
            mod_name = f"m_{func.name}"
            lines.append(f"    // {func.name} 模块例化")
            lines.append(f"    {mod_name} u_{func.name} (")
            lines.append(f"        .clk   (clk),")
            lines.append(f"        .rst_n (rst_n)")
            lines.append("    );")
            lines.append("")

        # 过程子模块例化
        for proc in model.processes:
            mod_name = f"m_{proc.name}"
            lines.append(f"    // {proc.name} 模块例化")
            lines.append(f"    {mod_name} u_{proc.name} (")
            lines.append(f"        .clk   (clk),")
            lines.append(f"        .rst_n (rst_n)")
            lines.append("    );")
            lines.append("")

        # RAM wrapper 例化
        if reg_map:
            for tbl in reg_map.mem_tables:
                name = tbl.name
                bits = tbl.words * 32
                addr_w = self._addr_width(tbl.num_entries)
                lines.append(f"    // {name} RAM 例化")
                lines.append(f"    wire [{addr_w-1}:0]  {name}_rd_addr;")
                lines.append(f"    wire [{bits-1}:0]   {name}_rd_data;")
                lines.append(f"    wire                {name}_wr_en;")
                lines.append(f"    wire [{addr_w-1}:0]  {name}_wr_addr;")
                lines.append(f"    wire [{bits-1}:0]   {name}_wr_data;")
                lines.append(f"    {name}_ram u_{name}_ram (")
                lines.append(f"        .clk     (clk),")
                lines.append(f"        .rd_addr ({name}_rd_addr),")
                lines.append(f"        .rd_data ({name}_rd_data),")
                lines.append(f"        .wr_en   ({name}_wr_en),")
                lines.append(f"        .wr_addr ({name}_wr_addr),")
                lines.append(f"        .wr_data ({name}_wr_data)")
                lines.append("    );")
                lines.append("")

        # 寄存器 bank 例化
        if reg_map and reg_map.registers:
            lines.append("    // 寄存器 bank 例化")
            lines.append("    reg_bank u_reg_bank (")
            lines.append("        .clk        (clk),")
            lines.append("        .rst_n      (rst_n),")
            lines.append("        .reg_addr   (reg_addr),")
            lines.append("        .reg_wr_data(reg_wr_data),")
            lines.append("        .reg_wr_en  (reg_wr_en),")
            lines.append("        .reg_rd_data(reg_rd_data)")
            lines.append("    );")
            lines.append("")

        lines.append("endmodule")
        return "\n".join(lines)

    # ==================================================================
    # 函数 → 独立模块
    # ==================================================================

    def _collect_external_refs(self, stmt: "Optional[Stmt]", local: "set[str]") -> "set[str]":
        refs = set()
        if stmt is None:
            return refs
        if isinstance(stmt, VarDeclStmt):
            local.add(stmt.name)
            return refs
        if isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                if isinstance(s, VarDeclStmt):
                    local.add(s.name)
            for s in stmt.stmts:
                refs |= self._collect_external_refs(s, local)
            return refs
        if isinstance(stmt, IfStmt):
            refs |= self._expr_has_ref(stmt.cond, local)
            refs |= self._collect_external_refs(stmt.then_stmt, local)
            refs |= self._collect_external_refs(stmt.else_stmt, local)
            return refs
        if isinstance(stmt, WhileStmt):
            refs |= self._expr_has_ref(stmt.cond, local)
            refs |= self._collect_external_refs(stmt.body, local)
            return refs
        if isinstance(stmt, ForStmt):
            c = stmt.cond if hasattr(stmt, 'cond') else None
            refs |= self._expr_has_ref(c, local)
            refs |= self._collect_external_refs(stmt.body, local)
            return refs
        if isinstance(stmt, SwitchStmt):
            refs |= self._expr_has_ref(stmt.expr, local)
            for cs in stmt.cases:
                refs |= self._collect_external_refs(cs.stmt, local)
            return refs
        if isinstance(stmt, AssignStmt):
            refs |= self._expr_has_ref(stmt.lhs, local)
            refs |= self._expr_has_ref(stmt.rhs, local)
            return refs
        if isinstance(stmt, ExprStmt):
            refs |= self._expr_has_ref(stmt.expr, local)
            return refs
        return refs

    def _expr_has_ref(self, expr: "Optional[Expr]", local: "set[str]") -> "set[str]":
        refs = set()
        if expr is None:
            return refs
        if isinstance(expr, IdentifierExpr):
            name = expr.name
            if name not in local and not name.startswith('_') and (not name or not name[0].isdigit()):
                refs.add(name)
            return refs
        if isinstance(expr, BinaryOpExpr):
            return self._expr_has_ref(expr.left, local) | self._expr_has_ref(expr.right, local)
        if isinstance(expr, UnaryOpExpr):
            return self._expr_has_ref(expr.operand, local)
        if isinstance(expr, FieldAccessExpr):
            return self._expr_has_ref(expr.base, local)
        if isinstance(expr, BitSliceExpr):
            return self._expr_has_ref(expr.base, local)
        if isinstance(expr, BitIndexExpr):
            return self._expr_has_ref(expr.base, local) | self._expr_has_ref(expr.index, local)
        if isinstance(expr, FieldIndexExpr):
            r = self._expr_has_ref(expr.base, local)
            if hasattr(expr, 'index') and expr.index:
                r |= self._expr_has_ref(expr.index, local)
            return r
        if isinstance(expr, ConcatExpr):
            r = set()
            for p in expr.parts:
                r |= self._expr_has_ref(p, local)
            return r
        if isinstance(expr, FunctionCallExpr):
            r = set()
            for a in expr.args:
                r |= self._expr_has_ref(a, local)
            return r
        if isinstance(expr, MaxMinExpr):
            r = set()
            for a in expr.args:
                r |= self._expr_has_ref(a, local)
            return r
        return refs

    def _collect_rtl_regs(self, stmt):
        decls = []
        if stmt is None: return decls
        if isinstance(stmt, VarDeclStmt):
            w = 32
            if stmt.var_type and isinstance(stmt.var_type, BitVectorType): w = stmt.var_type.width
            decls.append('reg [{w-1}:0] {stmt.name};')
        elif isinstance(stmt, CompoundStmt):
            for s in stmt.stmts: decls.extend(self._collect_rtl_regs(s))
        elif isinstance(stmt, IfStmt):
            decls.extend(self._collect_rtl_regs(stmt.then_stmt))
            decls.extend(self._collect_rtl_regs(stmt.else_stmt))
        elif isinstance(stmt, (WhileStmt, ForStmt)):
            decls.extend(self._collect_rtl_regs(stmt.body))
        elif isinstance(stmt, SwitchStmt):
            for cs in stmt.cases: decls.extend(self._collect_rtl_regs(cs.stmt))
        return decls


    def _gen_function_module(self, func: FunctionDef) -> str:
        """将函数转换为独立Verilog模块。"""
        lines: "List[str]" = []
        safe_name = self._sanitize_module_name(f"m_{func.name}")
        # 收集外部引用 → 作为 input 端口
        if func.body:
            undeclared = self._collect_external_refs(func.body, set())
        else:
            undeclared = set()
        ports = [("input", "wire", "clk"), ("input", "wire", "rst_n")]
        for name in sorted(undeclared - {'clk', 'rst_n'}):
            ports.append(("input", "wire [31:0]", name))
        lines.append(self._gen_module_header(safe_name, ports))
        self._indent_level = 1
        if func.body:
            regs = self._collect_rtl_regs(func.body)
            for r in sorted(set(regs)):
                lines.append(self._indent(r))
            if regs:
                lines.append("")
            lines.append("always @(*) begin")
            self._indent_level += 1
            # 直接翻译每条语句，不包裹额外的 begin/end
            if isinstance(func.body, CompoundStmt):
                for s in func.body.stmts:
                    lines.append(self._gen_rtl_statement(s))
            else:
                lines.append(self._gen_rtl_statement(func.body))
            self._indent_level -= 1
            lines.append("end")
        self._indent_level = 0
        lines.append("endmodule")
        return "\n".join(lines)

    # ==================================================================
    # 过程 → always 块模块
    # ==================================================================

    def _gen_process_module(self, proc: ProcessDef) -> str:
        """将过程转换为 always 块模块（FSM 或 简单时序逻辑）。"""
        lines: List[str] = []
        mod_name = f"m_{proc.name}"
        ports = [("input", "wire", "clk"), ("input", "wire", "rst_n")]
        lines.append(self._gen_module_header(mod_name, ports))
        self._indent_level = 1

        # 分析是否包含 Delay → FSM
        has_delay = self._has_delay(proc.body)
        if has_delay:
            lines.append(self._gen_fsm_block(proc))
            # TODO: 完整 FSM 生成
        else:
            # 无 Delay: 简单 always @(posedge clk)
            lines.append("always @(posedge clk or negedge rst_n) begin")
            self._indent_level += 1
            lines.append(self._indent("if (!rst_n) begin"))
            self._indent_level += 1
            # 复位逻辑（占位）
            lines.append(self._indent("// TODO: reset logic"))
            self._indent_level -= 1
            lines.append(self._indent("end else begin"))
            self._indent_level += 1
            if proc.body:
                lines.append(self._gen_rtl_statement(proc.body))
            self._indent_level -= 1
            lines.append(self._indent("end"))
            self._indent_level -= 1
            lines.append("end")

        self._indent_level = 0
        lines.append("endmodule")
        return "\n".join(lines)

    def _gen_fsm_block(self, proc: ProcessDef) -> str:
        """为包含 Delay 的过程生成 FSM。"""
        lines: List[str] = []
        # 推断状态
        states = self._infer_fsm_states(proc.body)
        state_param = self._indent(f"localparam [2:0] " +
                                   ", ".join(f"{s} = {i}" for i, s in enumerate(states)) + ";")
        lines.append(state_param)
        lines.append(self._indent(f"reg [2:0] state, next_state;"))
        lines.append(self._indent(f"reg [31:0] delay_cnt;"))
        lines.append("")
        lines.append(self._indent("always @(posedge clk or negedge rst_n) begin"))
        self._indent_level += 1
        lines.append(self._indent("if (!rst_n) begin"))
        self._indent_level += 1
        lines.append(self._indent(f"state <= {states[0]};"))
        lines.append(self._indent("delay_cnt <= 0;"))
        self._indent_level -= 1
        lines.append(self._indent("end else begin"))
        self._indent_level += 1
        lines.append(self._indent("state <= next_state;"))
        lines.append(self._indent("case (state)"))
        self._indent_level += 1
        for i, s in enumerate(states):
            lines.append(self._indent(f"{s}: begin"))
            self._indent_level += 1
            if i < len(states) - 1:
                lines.append(self._indent(f"next_state = {states[i+1]};"))
            else:
                lines.append(self._indent(f"next_state = {states[0]};"))
            lines.append(self._indent("// TODO: FSM state body"))
            self._indent_level -= 1
            lines.append(self._indent("end"))
        self._indent_level -= 1
        lines.append(self._indent("endcase"))
        self._indent_level -= 1
        lines.append(self._indent("end"))
        self._indent_level -= 1
        lines.append("end")
        return "\n".join(lines)

    # ==================================================================
    # 流水线模块（forward 特殊处理）
    # ==================================================================

    def _gen_pipeline_module(self, proc: ProcessDef) -> str:
        """为 forward() 生成流水线模块。"""
        lines: List[str] = []
        mod_name = "m_forward_pipeline"
        ports = [
            ("input", "wire", "clk"),
            ("input", "wire", "rst_n"),
            ("input", "wire [7:0]", "PacketByte [0:63]"),
            ("output", "wire [7:0]", "out_packet [0:63]"),
            ("output", "wire [2:0]", "out_port"),
        ]
        lines.append(self._gen_module_header(mod_name, ports))
        self._indent_level = 1

        # 推断流水线级数
        stages = self._infer_pipeline_stages(proc.body)
        lines.append(f"// 推断为 {len(stages)} 级流水线: " + " → ".join(stages))
        lines.append("")

        # 流水线寄存器
        for i, stage in enumerate(stages):
            if i > 0:
                lines.append(f"// Stage {i} → Stage {i+1} 流水线寄存器")
                lines.append("// TODO: automatic pipeline register insertion")
                lines.append("")

        lines.append("// TODO: manual pipeline adjustment required")
        self._indent_level = 0
        lines.append("endmodule")
        return "\n".join(lines)

    # ==================================================================
    # RAM Wrapper
    # ==================================================================

    def _gen_ram_wrapper(self, tbl: MemTableDecl) -> str:
        """为内存表生成可综合单口RAM wrapper模块。"""
        name = tbl.name
        depth = tbl.num_entries
        bits = tbl.words * 32
        addr_w = self._addr_width(depth)
        lines: List[str] = []
        lines.append(f"// {name} RAM ({depth} entries × {tbl.words} words)")
        lines.append(f"module {name}_ram (")
        lines.append(f"    input  wire        clk,")
        lines.append(f"    input  wire [{addr_w-1}:0] rd_addr,")
        lines.append(f"    output reg  [{bits-1}:0]  rd_data,")
        lines.append(f"    input  wire         wr_en,")
        lines.append(f"    input  wire [{addr_w-1}:0] wr_addr,")
        lines.append(f"    input  wire [{bits-1}:0]  wr_data")
        lines.append(");")
        lines.append("")
        lines.append(f"    reg [{bits-1}:0] mem [0:{depth-1}];")
        lines.append("")
        lines.append("    always @(posedge clk) begin")
        lines.append("        if (wr_en)")
        lines.append("            mem[wr_addr] <= wr_data;")
        lines.append("        rd_data <= mem[rd_addr];")
        lines.append("    end")
        lines.append("")
        lines.append("endmodule")
        return "\n".join(lines)

    # ==================================================================
    # 寄存器 Bank
    # ==================================================================

    def _gen_reg_bank(self, registers: List[RegisterDecl]) -> str:
        """为所有寄存器生成寄存器bank模块。"""
        lines: List[str] = []
        lines.append("// 寄存器 Bank")
        lines.append("module reg_bank (")
        lines.append("    input  wire        clk,")
        lines.append("    input  wire        rst_n,")
        lines.append("    input  wire [17:2]  reg_addr,")
        lines.append("    input  wire [31:0]  reg_wr_data,")
        lines.append("    input  wire         reg_wr_en,")
        lines.append("    output reg  [31:0]  reg_rd_data")
        lines.append(");")
        lines.append("")

        # 为每个寄存器声明 reg
        for reg in registers:
            name = reg.name
            words = reg.words
            lines.append(f"    // {name} ({words} words)")
            for i in range(words):
                def_val = ""
                for f in reg.fields:
                    if f.default_value:
                        def_val = f.default_value
                lines.append(f"    reg [31:0] {name}_word{i};")
            lines.append("")

        # always 块实现读写
        lines.append("    always @(posedge clk or negedge rst_n) begin")
        lines.append("        if (!rst_n) begin")
        for reg in registers:
            for i in range(reg.words):
                # 提取默认值
                def_val = "32'b0"
                for f in reg.fields:
                    if f.default_value:
                        def_val = f"32'h{f.default_value}"
                        break
                lines.append(f"            {reg.name}_word{i} <= {def_val};")
        lines.append("        end else if (reg_wr_en) begin")
        lines.append("            case (reg_addr)")
        # 为每个寄存器生成地址 case
        for reg in registers:
            addr = reg.decode_pattern
            if addr:
                lines.append(f"                {addr}: begin")
                for i in range(reg.words):
                    offset = hex(int(addr, 0) + i) if addr.startswith("0x") else addr
                    lines.append(f"                    if (reg_addr == {offset})")
                    lines.append(f"                        {reg.name}_word{i} <= reg_wr_data;")
                lines.append("                end")
        lines.append("            endcase")
        lines.append("        end")
        lines.append("    end")
        lines.append("")
        lines.append("    // 读数据")
        lines.append("    always @(*) begin")
        lines.append("        case (reg_addr)")
        for reg in registers:
            addr = reg.decode_pattern
            if addr:
                for i in range(reg.words):
                    offset = hex(int(addr, 0) + i) if addr.startswith("0x") else addr
                    lines.append(f"            {offset}: reg_rd_data = {reg.name}_word{i};")
        lines.append("            default: reg_rd_data = 32'b0;")
        lines.append("        endcase")
        lines.append("    end")
        lines.append("")
        lines.append("endmodule")
        return "\n".join(lines)

    # ==================================================================
    # 地址译码
    # ==================================================================

    def _gen_addr_decode(self, reg_map: RegMapDef) -> str:
        """生成地址译码模块。"""
        lines: List[str] = []
        lines.append("// 地址译码模块")
        lines.append("module addr_decode (")
        lines.append("    input  wire [31:0] addr,")
        lines.append("    output wire        sel_reg_bank,")
        lines.append("    output wire [9:0]   sel_ram_id,")
        lines.append("    output wire [11:0]  ram_offset")
        lines.append(");")
        lines.append("")
        lines.append("    // TODO: 实现地址译码逻辑")
        lines.append("    assign sel_reg_bank = (addr[31:24] == 8'h00);")
        lines.append("    assign sel_ram_id = addr[31:22];")
        lines.append("    assign ram_offset = addr[11:0];")
        lines.append("")
        lines.append("endmodule")
        return "\n".join(lines)

    # ==================================================================
    # 语句翻译
    # ==================================================================

    def _gen_rtl_statement(self, stmt: Optional[Stmt]) -> str:
        """将AST语句翻译为Verilog。"""
        if stmt is None:
            return ""
        if isinstance(stmt, CompoundStmt):
            return self._gen_compound_statement(stmt)
        if isinstance(stmt, IfStmt):
            return self._gen_if(stmt)
        if isinstance(stmt, ForStmt):
            return self._gen_for(stmt)
        if isinstance(stmt, WhileStmt):
            return f"// TODO: while loop → always block\n{self._gen_rtl_statement(stmt.body)}"
        if isinstance(stmt, SwitchStmt):
            return self._gen_switch(stmt)
        if isinstance(stmt, AssignStmt):
            return self._gen_assign(stmt)
        if isinstance(stmt, CompoundAssignStmt):
            return self._gen_compound_assign(stmt)
        if isinstance(stmt, IncDecStmt):
            return self._gen_inc_dec_rtl(stmt)
        if isinstance(stmt, VarDeclStmt):
            return self._gen_var_decl_rtl(stmt)
        if isinstance(stmt, TableReadStmt):
            return self._gen_table_read_rtl(stmt)
        if isinstance(stmt, TableWriteStmt):
            return self._gen_table_write_rtl(stmt)
        if isinstance(stmt, ExprStmt):
            return f"{self._gen_rtl_expr(stmt.expr)};"
        if isinstance(stmt, DelayStmt):
            return f"// TODO: Delay → FSM DELAY state"
        if isinstance(stmt, BreakStmt):
            return "// break"
        if isinstance(stmt, ReturnStmt):
            return "// return"
        if isinstance(stmt, (EnqueueStmt, SendStmt)):
            return f"// TODO: hardware enqueue/send"
        if isinstance(stmt, (ReplaceStmt, InsertStmt, RemoveStmt)):
            return f"// TODO: packet manipulation"
        return f"// TODO: {type(stmt).__name__}"

    def _gen_compound_statement(self, stmt: CompoundStmt) -> str:
        parts: List[str] = []
        parts.append(self._indent("begin"))
        self._indent_level += 1
        for s in stmt.stmts:
            rtl = self._gen_rtl_statement(s)
            if rtl:
                parts.append(rtl)
        self._indent_level -= 1
        parts.append(self._indent("end"))
        return "\n".join(parts)

    def _gen_if(self, stmt: IfStmt) -> str:
        cond = self._gen_rtl_expr(stmt.cond)
        parts: List[str] = []
        parts.append(f"if ({cond}) begin")
        self._indent_level += 1
        if stmt.then_stmt:
            parts.append(self._gen_rtl_statement(stmt.then_stmt))
        self._indent_level -= 1
        if stmt.else_stmt:
            parts.append(f"end else begin")
            self._indent_level += 1
            parts.append(self._gen_rtl_statement(stmt.else_stmt))
            self._indent_level -= 1
        parts.append("end")
        return "\n".join(self._indent(p) if i == 0 else p for i, p in enumerate(parts))

    def _gen_for(self, stmt: ForStmt) -> str:
        init = self._gen_rtl_statement(stmt.init) if stmt.init else ""
        cond = self._gen_rtl_expr(stmt.cond) if stmt.cond else ""
        incr = self._gen_rtl_statement(stmt.incr) if stmt.incr else ""
        body = self._gen_rtl_statement(stmt.body) if stmt.body else ""
        return (
            f"for ({init.strip().rstrip(';')}; {cond}; {incr.strip().rstrip(';')}) begin\n"
            f"{body}\n"
            f"end"
        )

    def _gen_switch(self, stmt: SwitchStmt) -> str:
        expr = self._gen_rtl_expr(stmt.expr)
        parts: List[str] = [f"case ({expr})"]
        self._indent_level += 1
        for cs in stmt.cases:
            if cs.value is None:
                label = "default:"
            elif isinstance(cs.value, RangeExpr):
                s = self._gen_rtl_expr(cs.value.start)
                e = self._gen_rtl_expr(cs.value.end)
                label = f"{s}, {e}:"  # 简化：不展开范围
            else:
                label = f"{self._gen_rtl_expr(cs.value)}:"
            body = self._gen_rtl_statement(cs.stmt) if cs.stmt else ""
            parts.append(f"{label} begin {body} end")
        self._indent_level -= 1
        parts.append("endcase")
        return "\n".join(parts)

    def _gen_assign(self, stmt: AssignStmt) -> str:
        lhs = self._gen_rtl_expr(stmt.lhs)
        rhs = self._gen_rtl_expr(stmt.rhs)
        return f"{lhs} <= {rhs};"

    def _gen_compound_assign(self, stmt: CompoundAssignStmt) -> str:
        lhs = self._gen_rtl_expr(stmt.lhs)
        rhs = self._gen_rtl_expr(stmt.rhs)
        return f"{lhs} <= {lhs} {stmt.op[0]} {rhs};"

    def _gen_inc_dec_rtl(self, stmt: IncDecStmt) -> str:
        op = stmt.op
        operand = self._gen_rtl_expr(stmt.operand)
        if stmt.prefix:
            return f"{operand} <= {operand} {'+' if op == '++' else '-'} 1;"
        return f"{operand} <= {operand} {'+' if op == '++' else '-'} 1;"

    def _gen_var_decl_rtl(self, stmt: VarDeclStmt) -> str:
        """reg 声明已在模块顶部，这里只生成初始化赋值。"""
        if stmt.init:
            rhs = self._gen_rtl_expr(stmt.init)
            return f"{stmt.name} = {rhs};"
        return f"// {stmt.name} declared at module top"

    def _gen_table_read_rtl(self, stmt: TableReadStmt) -> str:
        idx = self._gen_rtl_expr(stmt.index)
        return f"{stmt.target_var} = {stmt.table_name}_rd_data; // addr={idx}"

    def _gen_table_write_rtl(self, stmt: TableWriteStmt) -> str:
        idx = self._gen_rtl_expr(stmt.index)
        val = self._gen_rtl_expr(stmt.value)
        return (
            f"{stmt.table_name}_wr_en = 1;\n"
            f"{self._indent(f'{stmt.table_name}_wr_addr = {idx};')}\n"
            f"{self._indent(f'{stmt.table_name}_wr_data = {val};')}"
        )

    # ==================================================================
    # 表达式翻译
    # ==================================================================

    def _gen_rtl_expr(self, expr: Optional[Expr]) -> str:
        """将AST表达式翻译为Verilog表达式。"""
        if expr is None:
            return ""
        if isinstance(expr, IdentifierExpr):
            return expr.name
        if isinstance(expr, IntLiteral):
            w = expr.value.bit_length()
            if w <= 1:
                return str(expr.value)
            return f"{w}'d{expr.value}"
        if isinstance(expr, HexLiteral):
            if expr.width:
                return f"{expr.width}'h{expr.value:x}"
            w = expr.value.bit_length()
            if w == 0:
                w = 1
            return f"{w}'h{expr.value:x}"
        if isinstance(expr, BinLiteral):
            return f"{expr.width}'b{expr.value:b}"
        if isinstance(expr, BinaryOpExpr):
            left = self._gen_rtl_expr(expr.left)
            right = self._gen_rtl_expr(expr.right)
            op = expr.op
            # 映射C操作符到Verilog
            verilog_ops = {
                "&&": "&&", "||": "||", "!=": "!=", "==": "==",
                "<": "<", ">": ">", "<=": "<=", ">=": ">=",
                "+": "+", "-": "-", "*": "*", "/": "/",
                "<<": "<<", ">>": ">>",
                "&": "&", "|": "|", "^": "^",
            }
            vop = verilog_ops.get(op, op)
            if op == "?:":  # ternary
                inner = expr.right
                if isinstance(inner, BinaryOpExpr) and inner.op == ":":
                    return f"({left} ? {self._gen_rtl_expr(inner.left)} : {self._gen_rtl_expr(inner.right)})"
            return f"({left} {vop} {right})"
        if isinstance(expr, UnaryOpExpr):
            operand = self._gen_rtl_expr(expr.operand)
            op = expr.op
            if op == "!":
                return f"!{operand}"
            if op == "~":
                return f"~{operand}"
            if op.startswith("post"):
                return f"{operand}"  # 前缀/后缀无区别，assign时处理
            return f"{op}{operand}"
        if isinstance(expr, FieldAccessExpr):
            base = self._gen_rtl_expr(expr.base)
            field = expr.field
            return f"{base}_{field}"
        if isinstance(expr, BitSliceExpr):
            base = self._gen_rtl_expr(expr.base)
            return f"{base}[{expr.hi_bit}:{expr.lo_bit}]"
        if isinstance(expr, ConcatExpr):
            parts = ", ".join(self._gen_rtl_expr(p) for p in expr.parts)
            return f"{{{parts}}}"
        if isinstance(expr, FunctionCallExpr):
            args = ", ".join(self._gen_rtl_expr(a) for a in expr.args)
            return f"{expr.name}({args})"
        if isinstance(expr, MaxMinExpr):
            op = ">" if expr.func == "max" else "<"
            args = [self._gen_rtl_expr(a) for a in expr.args]
            if len(args) == 2:
                return f"({args[0]} {op} {args[1]} ? {args[0]} : {args[1]})"
            if len(args) == 3:
                a, b, c = args
                return f"(({a} {op} {b}) ? (({a} {op} {c}) ? {a} : {c}) : (({b} {op} {c}) ? {b} : {c}))"
        if isinstance(expr, BitIndexExpr):
            base = self._gen_rtl_expr(expr.base)
            idx = self._gen_rtl_expr(expr.index)
            return f"{base}[{idx}]"
        if isinstance(expr, FieldIndexExpr):
            if isinstance(expr.base, FieldAccessExpr):
                parent = self._gen_rtl_expr(expr.base.base)
                field = expr.base.field
                idx = self._gen_rtl_expr(expr.index)
                return f"{parent}_{field}[{idx}]"
            return f"{self._gen_rtl_expr(expr.base)}[{self._gen_rtl_expr(expr.index)}]"
        # 默认
        return f"/*expr:{type(expr).__name__}*/"

    # ==================================================================
    # 辅助方法
    # ==================================================================

    def _type_to_rtl(self, t: Optional[Type], io: str = "wire") -> str:
        """将8m类型转换为Verilog类型字符串。"""
        if t is None:
            return io
        if isinstance(t, BitVectorType):
            if t.width == 1:
                return io
            return f"{io} [{t.width-1}:0]"
        if isinstance(t, BoolType):
            return io
        if isinstance(t, StructType):
            return f"{io} [{self._struct_width(t)-1}:0]"
        if isinstance(t, ArrayType):
            base = self._type_to_rtl(t.base_type, io)
            return f"{base} [0:{t.size-1}]"
        return io

    def _type_width(self, t: Optional[Type]) -> int:
        """返回类型的位宽。"""
        if t is None:
            return 1
        if isinstance(t, BitVectorType):
            return t.width
        if isinstance(t, BoolType):
            return 1
        if isinstance(t, ArrayType):
            return self._type_width(t.base_type) * t.size
        return 1

    @staticmethod
    def _struct_width(st: StructType) -> int:
        total = 0
        for f in st.fields:
            if f.width:
                total += f.width
            else:
                total += 1
        return total

    @staticmethod
    def _addr_width(depth: int) -> int:
        if depth <= 1:
            return 1
        return (depth - 1).bit_length()

    @staticmethod
    def _gen_module_header(name: str, ports: List[Tuple[str, str, str]]) -> str:
        """生成模块头: module name(clk, rst_n, ...);"""
        lines = [f"module {name} ("]
        for i, (direction, wire_type, port_def) in enumerate(ports):
            comma = "," if i < len(ports) - 1 else ""
            lines.append(f"    {direction} {wire_type} {port_def}{comma}")
        lines.append(");")
        return "\n".join(lines)

    @staticmethod
    def _gen_always_block(sensitive: str, body: str) -> str:
        """生成 always 块。"""
        return f"always @({sensitive}) begin\n{body}\nend"

    def _indent(self, text: str, extra: int = 0) -> str:
        return "    " * (self._indent_level + extra) + text

    @staticmethod
    def _has_delay(stmt: Optional[Stmt]) -> bool:
        """检查语句树中是否包含 DelayStmt。"""
        if stmt is None:
            return False
        if isinstance(stmt, DelayStmt):
            return True
        if isinstance(stmt, CompoundStmt):
            return any(RTLCodeGenerator._has_delay(s) for s in stmt.stmts)
        if isinstance(stmt, IfStmt):
            return (RTLCodeGenerator._has_delay(stmt.then_stmt) or
                    RTLCodeGenerator._has_delay(stmt.else_stmt))
        if isinstance(stmt, WhileStmt):
            return RTLCodeGenerator._has_delay(stmt.body)
        if isinstance(stmt, ForStmt):
            return RTLCodeGenerator._has_delay(stmt.body)
        return False

    def _infer_fsm_states(self, stmt: Optional[Stmt]) -> List[str]:
        """推断FSM状态（简化版：基于Delay出现次数）。"""
        states = ["IDLE"]
        if stmt is None:
            return states
        # 简单推断: 每个嵌套块一个新状态
        self._count_states(stmt, states)
        return states

    def _count_states(self, stmt: Stmt, states: List[str]) -> None:
        if isinstance(stmt, DelayStmt):
            states.append(f"DELAY_{len(states)}")
        elif isinstance(stmt, CompoundStmt):
            for s in stmt.stmts:
                self._count_states(s, states)
        elif isinstance(stmt, IfStmt):
            if stmt.then_stmt:
                self._count_states(stmt.then_stmt, states)
            if stmt.else_stmt:
                self._count_states(stmt.else_stmt, states)
        elif isinstance(stmt, WhileStmt):
            if stmt.body:
                self._count_states(stmt.body, states)
        elif isinstance(stmt, ForStmt):
            if stmt.body:
                self._count_states(stmt.body, states)

    def _infer_pipeline_stages(self, stmt: Optional[Stmt]) -> List[str]:
        """推断流水线级数（通过分析函数调用链）。"""
        stages: List[str] = []
        if stmt is None:
            return stages

        def collect_calls(s: Stmt) -> None:
            if isinstance(s, ExprStmt) and isinstance(s.expr, FunctionCallExpr):
                stages.append(s.expr.name)
            elif isinstance(s, CompoundStmt):
                for sub in s.stmts:
                    collect_calls(sub)
            elif isinstance(s, (IfStmt, WhileStmt)):
                if s.body:
                    collect_calls(s.body)
        collect_calls(stmt)
        return stages if stages else ["parser", "switchX", "egress"]
