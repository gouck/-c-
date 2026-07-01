"""
compiler/pipeline.py
Compilation pipeline orchestrator for the 8m compiler.

Coordinates the six compilation phases:
    Phase 1 – Lexing (tab_lexer + pseudoc_lexer)
    Phase 2 – Parsing (regmap_parser + pseudo-C parser)
    Phase 3 – Semantic analysis (symbol table + type checking)
    Phase 4 – IR generation (占位)
    Phase 5 – Optimization (占位)
    Phase 6 – Code generation (C)
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from compiler.lexer.tab_lexer import TabLexer
from compiler.lexer.pseudoc_lexer import PseudoCLexer, TokenType
from compiler.parser.regmap_parser import RegMapParser
from compiler.parser.pseudoc_parser import PseudoCParser
from compiler.parser.ast_nodes import TranslationUnit, PseudoCModel, RegMapDef
from compiler.semantic.symbol_table import SymbolTable, SymbolTableBuilder
from compiler.semantic.type_checker import analyze
from compiler.codegen.cpp_reg_driver_gen import CRegDriverGenerator
from compiler.codegen.c_codegen import CCodeGenerator


class CompilerPipeline:
    """
    Orchestrates the end-to-end compilation flow.

    Reads the pseudo-C spec and the register table DSL, then drives the
    compilation through lexing, parsing, semantic analysis, and
    final code generation.
    """

    def __init__(
        self,
        spec_path: str,
        reg_paths: list,
        output_dir: str,
        target: str,
        verbose: bool,
        h_files: list = None,
        c_files: list = None,
        project_mode: bool = False,
        merge_only: bool = False,
    ) -> None:
        self.spec_path: str = spec_path
        self.reg_paths: list = reg_paths
        self.target: str = target
        self.verbose: bool = verbose
        self.h_files: list = h_files or []
        self.c_files: list = c_files or [spec_path]
        self.project_mode: bool = project_mode
        self.merge_only: bool = merge_only

        # 自动编号：output/ → output/001/, output/002/, ...
        os.makedirs(output_dir, exist_ok=True)
        existing = [d for d in os.listdir(output_dir)
                     if os.path.isdir(os.path.join(output_dir, d)) and d.isdigit()]
        next_num = max([int(d) for d in existing] + [0]) + 1
        self.output_dir: str = os.path.join(output_dir, f"{next_num:03d}")
        self._run_number: int = next_num

        # intermediate results
        self.reg_data: Optional[Dict] = None
        self.reg_map: Optional[RegMapDef] = None
        self.spec_tokens: list = []
        self.spec_ast: Optional[PseudoCModel] = None
        self.translation_unit: Optional[TranslationUnit] = None
        self.symtab: Optional[SymbolTable] = None

    def run(self) -> None:
        """Execute all compilation phases in order."""
        phases = [
            ("Phase 1: Lexing", self._phase1_lex),
            # ╔══════════════════════════════════════════════════════════╗
            # ║  扩展加载阶段 — 扫描 source/ 下所有 .ext 文件              ║
            # ║  加载后注入 lexer 关键字表, 注册到 pipeline               ║
            # ╚══════════════════════════════════════════════════════════╝
            ("Phase 1.5: Extensions", self._phase1_5_extensions),
            ("Phase 2: Parsing", self._phase2_parse),
            ("Phase 2.5: Symbol source analysis", self._phase2_5_symbol_sources),
            ("Phase 3: Semantic analysis", self._phase3_semantic),
            ("Phase 4: IR generation", self._phase4_ir),
            ("Phase 5: Optimization", self._phase5_optimize),
            ("Phase 6: Code generation", self._phase6_codegen),
        ]

        for name, phase_fn in phases:
            if self.verbose:
                print(f"  [{name}] ...")
            phase_fn()

        print("Compilation pipeline complete.")

    # ------------------------------------------------------------------
    # Phase 1 – Lexing
    # ------------------------------------------------------------------

    def _phase1_lex(self) -> None:
        """Lex both input files into structured data / token lists."""
        # ── tinyReg.txt(s) → merged structured dict + individual dicts ──
        merged_data: Dict = {"config": {}, "mem_tables": [], "registers": []}
        self._individual_reg_data: list = []
        first_config = True
        for rp in self.reg_paths:
            with open(rp, "r", encoding="utf-8") as f:
                reg_text = f.read()
            lexer = TabLexer(reg_text)
            try:
                data = lexer.tokenize()
            except Exception as e:
                print(f"    Skipping {os.path.basename(rp)}: {e}")
                continue
            self._individual_reg_data.append(data)
            if first_config:
                merged_data["config"] = data.get("config", {})
                first_config = False
            merged_data["mem_tables"].extend(data.get("mem_tables", []))
            merged_data["registers"].extend(data.get("registers", []))
            if self.verbose:
                print(f"    Reg file {os.path.basename(rp)}: "
                      f"{len(data.get('mem_tables',[]))} tables, "
                      f"{len(data.get('registers',[]))} registers")
        self.reg_data = merged_data
        total_tables = len(self.reg_data.get("mem_tables", []))
        total_regs = len(self.reg_data.get("registers", []))
        if self.verbose and len(self.reg_paths) > 1:
            print(f"    Total merged: {total_tables} tables, {total_regs} registers")

        # ── Spec files (pseudo-C) ──
        # 多文件模式: 每个.h/.c单独lex，保留文件来源信息
        self._all_spec_text: str = ""           # 合并后的全部文本（仅.c，解析用）
        self._spec_file_contents: Dict[str, str] = {}  # 文件名 → 文本
        self._spec_token_map: Dict[str, list] = {}     # 文件名 → token列表

        # 合并所有 .c 文件用于统一解析（.h 文件由符号分析阶段处理）
        all_texts: list = []
        for hf in self.h_files:
            with open(hf, "r", encoding="utf-8") as f:
                text = f.read()
            self._spec_file_contents[os.path.basename(hf)] = text
            # .h 不加入合并解析文本，仅存储供符号分析和输出生成使用
        for cf in self.c_files:
            with open(cf, "r", encoding="utf-8") as f:
                text = f.read()
            self._spec_file_contents[os.path.basename(cf)] = text
            all_texts.append(f"/* @8m-file: {os.path.basename(cf)} */\n{text}")

        self._all_spec_text = "\n".join(all_texts)

        # Lex merged text (for unified parsing)
        spec_lexer = PseudoCLexer(self._all_spec_text)
        tokens = spec_lexer.tokenize()
        self.spec_tokens = [t for t in tokens if t.type != TokenType.NEWLINE]
        if self.verbose:
            n_files = len(self.h_files) + len(self.c_files)
            print(f"    Spec files: {n_files} files ({len(self.h_files)} .h + {len(self.c_files)} .c)")
            print(f"    Merged tokens: {len(tokens)} ({len(self.spec_tokens)} non-NEWLINE)")
        self.unknown_keywords = getattr(spec_lexer, '_unknown_keywords', set())

        # Also lex each file individually for per-file codegen
        for fname, text in self._spec_file_contents.items():
            fl = PseudoCLexer(text)
            ft = fl.tokenize()
            self._spec_token_map[fname] = [t for t in ft if t.type != TokenType.NEWLINE]

    # ------------------------------------------------------------------
    # Phase 1.5 – 扩展加载
    # ------------------------------------------------------------------

    def _phase1_5_extensions(self) -> None:
        """加载 source/ 目录下的所有 .ext 语法扩展文件"""
        from compiler.extension_loader import (
            load_extensions,
            get_keywords_from_extensions,
            get_hw_primitives_from_extensions,
        )
        import os as _os

        source_dir = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(self.spec_path))),
            'source'
        )
        if not _os.path.isdir(source_dir):
            source_dir = _os.path.join(_os.path.dirname(_os.path.abspath(self.spec_path)), 'source')

        self.loaded_extensions = load_extensions(source_dir)
        self.extra_keywords = get_keywords_from_extensions(self.loaded_extensions)
        self.extra_hw_primitives = get_hw_primitives_from_extensions(self.loaded_extensions)

        if self.verbose and self.loaded_extensions:
            print(f"    Loaded {len(self.loaded_extensions)} extensions:")
            for ext in self.loaded_extensions:
                print(f"      · {ext.name:20s} ({ext.ext_type:20s}) {ext.keyword or ext.operator}  {ext.description}")
        elif self.verbose:
            print("    (no .ext files found)")

    # ------------------------------------------------------------------
    # Phase 2 – Parsing
    # ------------------------------------------------------------------

    def _phase2_parse(self) -> None:
        """Parse both representations into ASTs."""
        # Parse each individual reg file → separate RegMapDef (for per-file output)
        self._individual_reg_maps: list = []
        for i, data in enumerate(self._individual_reg_data):
            parser = RegMapParser(data)
            reg_map = parser.parse()
            self._individual_reg_maps.append(reg_map)
            if self.verbose:
                label = os.path.basename(self.reg_paths[i]) if i < len(self.reg_paths) else f"reg_{i}"
                print(f"    Reg map [{label}]: {len(reg_map.mem_tables)} tables, "
                      f"{len(reg_map.registers)} registers")

        # Merged register map (for symbol table & backward compat)
        parser = RegMapParser(self.reg_data)
        self.reg_map = parser.parse()
        if self.verbose and len(self._individual_reg_data) > 1:
            print(f"    Register map (merged): {len(self.reg_map.mem_tables)} tables, "
                  f"{len(self.reg_map.registers)} registers")

        # Pseudo-C → PseudoCModel
        spec_parser = PseudoCParser(self.spec_tokens)
        self.spec_ast = spec_parser.parse()
        if self.verbose:
            print(f"    Pseudo-C model: {len(self.spec_ast.processes)} processes, "
                  f"{len(self.spec_ast.functions)} functions")

        # Build TranslationUnit
        self.translation_unit = TranslationUnit(
            model=self.spec_ast,
            reg_map=self.reg_map,
        )

    # ------------------------------------------------------------------
    # Phase 2.5 – Symbol source analysis (多文件模式)
    # ------------------------------------------------------------------

    def _phase2_5_symbol_sources(self) -> None:
        """Analyze which symbols are defined in which file.

        Builds:
          self._file_defines: dict[filename, set[symbol_name]]
          self._symbol_file:  dict[symbol_name, filename]
          self._file_uses:    dict[filename, set[symbol_name]]
        Used by Phase 6 to generate correct #include directives.
        """
        # Always run this phase (even single-file mode) for consistency
        import re
        self._file_defines: Dict[str, set] = {}
        self._symbol_file: Dict[str, str] = {}
        self._file_uses: Dict[str, set] = {}

        # Populate from .h files: everything declared is "defined" by that .h
        for fname, text in self._spec_file_contents.items():
            self._file_defines[fname] = set()
            self._file_uses[fname] = set()

        # Scan each file for symbol definitions (variable assignments, struct defs,
        # function definitions, process definitions)
        for fname, text in self._spec_file_contents.items():
            defines = self._file_defines[fname]
            uses = self._file_uses[fname]

            # Struct definitions: struct Xxx { ... }
            for m in re.finditer(r'struct\s+(\w+)', text):
                defines.add(m.group(1))

            # Variable declarations with type: uintN name[...] = ...
            for m in re.finditer(r'(?:uint\d+|bool)\s+(\w+)', text):
                var = m.group(1)
                defines.add(var)

            # Function definitions: void xxx( ... ) {
            for m in re.finditer(r'void\s+(\w+)\s*\(', text):
                defines.add(m.group(1))

            # Process definitions: process xxx() {
            for m in re.finditer(r'process\s+(\w+)\s*\(', text):
                defines.add(m.group(1))

            # Variable definitions (LHS of assignment → this file defines these)
            for m in re.finditer(r'(\w+)\s*\[.*?\]\s*=', text):
                defines.add(m.group(1))
            # Also catch bare assignments: var = expr; (no bit-range)
            for m in re.finditer(r'^\s*(\w+)\s*=\s*', text, re.MULTILINE):
                var = m.group(1)
                if var not in ('PacketByte', 'i'):  # skip loop counters, known globals
                    defines.add(var)
            # Variable usage (RHS of assignment / references)
            for m in re.finditer(r'=\s*(\w+)', text):
                uses.add(m.group(1))
            # Also track table reads and register field accesses
            for m in re.finditer(r'(\w+)\s*Table', text):
                uses.add(m.group(1))
            # Function call arguments: parser(PacketByte)
            for m in re.finditer(r'(\w+)\s*\(', text):
                func = m.group(1)
                if func not in ('while', 'for', 'if', 'switch', 'Delay', 'Enqueue',
                                'Replace', 'Insert', 'remove', 'send', 'update', 'Max', 'Max3', 'hash1'):
                    uses.add(func)

        # Build reverse mapping: symbol → defining file
        for fname, syms in self._file_defines.items():
            for sym in syms:
                if sym not in self._symbol_file:
                    self._symbol_file[sym] = fname

        # For each .c file, compute which .h files it needs
        self._file_includes: Dict[str, List[str]] = {}
        for cf in self.c_files:
            cf_name = os.path.basename(cf)
            needed: List[str] = []
            used_syms = self._file_uses.get(cf_name, set())

            # Rule 2: type dependencies — if .c uses struct fields
            for hf in self.h_files:
                hf_name = os.path.basename(hf)
                hf_defines = self._file_defines.get(hf_name, set())
                # If any symbol used by .c is defined in this .h
                if used_syms & hf_defines:
                    needed.append(hf_name)

            # Rule 4: extern dependencies — if .c uses symbols defined in other files
            for sym in used_syms:
                src = self._symbol_file.get(sym)
                if src and src != cf_name:
                    base = os.path.splitext(src)[0]
                    h_name = f"{base}.h"
                    if h_name in [os.path.basename(h) for h in self.h_files] and h_name not in needed:
                        needed.append(h_name)

            # Special: main.c always needs globals.h (PacketByte buffer)
            if cf_name == "main.c" and "globals.h" not in needed:
                needed.insert(0, "globals.h")
            # Every .c implicitly uses types from types.h if it references struct fields
            if "types.h" not in needed:
                # Check if the .c text contains struct member references
                if re.search(r'\b(macDa|macSa|vlanPrior|vlanId|isIpv4|isIpv6|ipDscp|isLoopDetection|isArp|isUnknownPkt)\b',
                             self._spec_file_contents.get(cf_name, '')):
                    needed.insert(0, "types.h")

            self._file_includes[cf_name] = needed

        if self.verbose:
            for fname, syms in self._file_defines.items():
                print(f"    {fname}: defines {len(syms)} symbols")
            for cf_name, incs in self._file_includes.items():
                if incs:
                    print(f"    {cf_name} → needs: {', '.join(incs)}")

    # ------------------------------------------------------------------
    # Phase 3 – Semantic analysis
    # ------------------------------------------------------------------

    def _phase3_semantic(self) -> None:
        """Build symbol table and run type checker."""
        builder = SymbolTableBuilder()
        self.symtab = builder.build(self.translation_unit)
        if self.verbose:
            print(f"    Symbol table: {len(self.symtab.symbols)} symbols")

        checker = analyze(self.translation_unit, self.symtab)
        if self.verbose:
            print(f"    Type check: {len(checker.errors)} errors, "
                  f"{len(checker.warnings)} warnings")

    # ------------------------------------------------------------------
    # Phase 4 – IR generation (占位)
    # ------------------------------------------------------------------

    def _phase4_ir(self) -> None:
        """Generate intermediate representation (future work)."""
        if self.verbose:
            print("    (placeholder)")

    # ------------------------------------------------------------------
    # Phase 5 – Optimization (占位)
    # ------------------------------------------------------------------

    def _phase5_optimize(self) -> None:
        """Optimize the IR (future work)."""
        if self.verbose:
            print("    (placeholder)")

    # ------------------------------------------------------------------
    # Phase 6 – Code generation
    # ------------------------------------------------------------------

    def _report_unknown_syntax(self, keywords: set) -> None:
        """报告伪C中发现的未注册语法关键字"""
        print()
        print("=" * 55)
        print("  WARNING: 发现未注册的语法元素")
        print("=" * 55)
        for kw in sorted(keywords):
            print(f"  · {kw}")
        print()
        print("  请为每个新语法创建 .ext 扩展文件，放入 source/ 目录。")
        print("  文件格式参考: source/README.ext")
        print("=" * 55)
        print()

    def _phase6_codegen(self) -> None:
        """Generate C header, source, and main logic files."""
        # ╔══════════════════════════════════════════════════════════╗
        # ║  扩展兼容性检查 — 报告源文件中未注册的语法关键字            ║
        # ╚══════════════════════════════════════════════════════════╝
        loaded_kw_set = set()
        if hasattr(self, 'loaded_extensions') and self.loaded_extensions:
            loaded_kw_set = {e.keyword for e in self.loaded_extensions if e.keyword}
        if hasattr(self, 'unknown_keywords') and self.unknown_keywords:
            truly_unknown = self.unknown_keywords - loaded_kw_set
            reg_names = set()
            if self.reg_data:
                for t in self.reg_data.get('mem_tables', []):
                    reg_names.add(t.get('name', ''))
                for r in self.reg_data.get('registers', []):
                    reg_names.add(r.get('name', ''))
            known_ids = reg_names | {
                'Max', 'Max3', 'PacketByte', 'PacketByte0', 'PacketByte5',
                'PacketByte6', 'PacketByte11', 'PacketByte12', 'PacketByte13',
                'ParserResult', 'DsMacFwd', 'DsMacLrn', 'DsMacAing',
                'DsDestPort', 'Detect', 'Loop',
            }
            truly_unknown -= known_ids
            if truly_unknown:
                self._report_unknown_syntax(truly_unknown)

        os.makedirs(self.output_dir, exist_ok=True)

        # -- 为每个 reg 文件独立生成 reg_drv_N.h / reg_drv_N.c --
        #  工程模式下只在 c_project 内生成，此处仅收集文件名供 output.c 使用
        reg_drv_headers: List[str] = []
        if hasattr(self, '_individual_reg_maps') and len(self._individual_reg_maps) > 1:
            common_macros = CRegDriverGenerator._gen_bitfield_macros()
            common_h = "#ifndef _REG_DRV_COMMON_H_\n#define _REG_DRV_COMMON_H_\n\n"
            common_h += "#include <stdint.h>\n\n"
            common_h += "\n".join(common_macros) + "\n\n"
            common_h += "#endif /* _REG_DRV_COMMON_H_ */\n"

            reg_drv_headers.append("reg_drv_common.h")

            for i, reg_map in enumerate(self._individual_reg_maps):
                fname = os.path.splitext(os.path.basename(self.reg_paths[i]))[0] if i < len(self.reg_paths) else f"reg_{i}"
                h_name = f"reg_drv_{fname}.h"
                c_name = f"reg_drv_{fname}.c"
                reg_drv_headers.append(h_name)

                # 非工程模式(或merge-only) → 在 output/ 下也生成一份
                if not self.project_mode or self.merge_only:
                    drv_gen = CRegDriverGenerator(reg_map)
                    header = drv_gen.generate_header(guard_suffix=fname)
                    source = drv_gen.generate_source(header_name=fname)
                    h_path = os.path.join(self.output_dir, h_name)
                    c_path = os.path.join(self.output_dir, c_name)
                    with open(h_path, "w", encoding="utf-8") as f:
                        f.write(header)
                    with open(c_path, "w", encoding="utf-8") as f:
                        f.write(source)
                    if self.verbose:
                        print(f"    {h_path} ({len(header)} bytes)")
                        print(f"    {c_path} ({len(source)} bytes)")

            # 生成共享宏文件
            if not self.project_mode or self.merge_only:
                common_path = os.path.join(self.output_dir, "reg_drv_common.h")
                with open(common_path, "w", encoding="utf-8") as f:
                    f.write(common_h)
                if self.verbose:
                    print(f"    {common_path} (shared macros)")

            if self.verbose and (not self.project_mode or self.merge_only):
                print(f"    (output.c includes {len(reg_drv_headers)} files directly)")
        else:
            drv_gen = CRegDriverGenerator(self.reg_map)
            header = drv_gen.generate_header()
            source = drv_gen.generate_source()
            h_path = os.path.join(self.output_dir, "reg_drv.h")
            c_path = os.path.join(self.output_dir, "reg_drv.c")
            with open(h_path, "w", encoding="utf-8") as f:
                f.write(header)
            with open(c_path, "w", encoding="utf-8") as f:
                f.write(source)
            if self.verbose:
                print(f"    {h_path} ({len(header)} bytes)")
                print(f"    {c_path} ({len(source)} bytes)")

        # -- 生成 merged output.c (向后兼容，工程模式下跳过) --
        if not self.project_mode or self.merge_only:
            codegen = CCodeGenerator(self.translation_unit, self.symtab)
            codegen._trace_enabled = True
            if hasattr(self, '_individual_reg_maps') and len(self._individual_reg_maps) > 1:
                main_code = codegen.generate(reg_drv_includes=reg_drv_headers)
            else:
                main_code = codegen.generate()
            out_path = os.path.join(self.output_dir, "output.c")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(main_code)
            if self.verbose:
                print(f"    {out_path} ({len(main_code)} bytes)")
            # generate trace files
            self._generate_trace_files(codegen, is_project=False)
        else:
            # 工程模式：仍然生成 merged_code 供 c_project 拆分使用
            codegen = CCodeGenerator(self.translation_unit, self.symtab)
            codegen._trace_enabled = True
            if hasattr(self, '_individual_reg_maps') and len(self._individual_reg_maps) > 1:
                main_code = codegen.generate(reg_drv_includes=reg_drv_headers)
            else:
                main_code = codegen.generate()

        # ──  方案B: 多文件工程输出 ──
        if self.project_mode and not self.merge_only:
            self._generate_project_output(reg_drv_headers, main_code)
            # generate trace files into c_project
            self._generate_trace_files(codegen, is_project=True)

    # ------------------------------------------------------------------
    # 方案B: 多文件C工程输出
    # ------------------------------------------------------------------

    def _generate_project_output(self, reg_drv_headers: List[str], merged_code: str) -> None:
        """Generate a multi-file C project from the DSL project.

        Output:
          output/c_project/
            ├── include/            ← 所有 .h 文件
            │   ├── 8m_globals.h
            │   ├── 8m_types.h
            │   ├── 8m_parser.h
            │   ├── 8m_switchX.h
            │   ├── 8m_egress.h
            │   └── reg_drv_*.h
            ├── src/                ← 所有 .c 文件
            │   ├── 8m_main.c
            │   ├── 8m_parser.c
            │   ├── 8m_switchX.c
            │   ├── 8m_egress.c
            │   └── reg_drv_*.c
            └── Makefile
        """
        import re
        import shutil

        proj_dir = os.path.join(self.output_dir, "c_project")
        inc_dir = os.path.join(proj_dir, "include")
        src_dir = os.path.join(proj_dir, "src")
        os.makedirs(inc_dir, exist_ok=True)
        os.makedirs(src_dir, exist_ok=True)

        # ── 1. 生成 8m_*.h 文件 → include/ ──
        # 1a. 运行时公共头文件
        runtime_h = self._gen_runtime_header()
        runtime_path = os.path.join(inc_dir, "8m_runtime.h")
        with open(runtime_path, "w", encoding="utf-8") as f:
            f.write(runtime_h)
        if self.verbose:
            print(f"    {runtime_path} ({len(runtime_h)} bytes)")

        # 1b. 用户 .h 文件
        for hf in self.h_files:
            hf_name = os.path.basename(hf)
            out_name = f"8m_{hf_name}"
            out_path = os.path.join(inc_dir, out_name)
            guard = f"_8M_{hf_name.upper().replace('.', '_')}_"

            text = self._spec_file_contents.get(hf_name, "")
            c_text = self._dsl_h_to_c_h(text, guard, hf_name)

            # 规则4: extern declarations
            base = os.path.splitext(hf_name)[0]
            for cf_name in [os.path.basename(c) for c in self.c_files]:
                cf_base = os.path.splitext(cf_name)[0]
                if cf_base == base:
                    externs = self._find_cross_file_externs(cf_name)
                    if externs:
                        c_text = c_text.replace(
                            f"/* @externs */",
                            "\n/* Cross-file extern declarations (auto-generated) */\n" +
                            "\n".join(f"extern {e};" for e in externs) + "\n"
                        )
                    else:
                        c_text = c_text.replace(f"/* @externs */\n", "")

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(c_text)
            if self.verbose:
                print(f"    {out_path} ({len(c_text)} bytes)")

        # ── 2. 拆分 merged_code → 8m_common.c（声明定义）+ 各函数文件 ──
        all_lines = merged_code.split('\n')
        split_idx = 0
        for i, l in enumerate(all_lines):
            if '@8m-file:' in l:
                split_idx = i
                break

        # preamble → 8m_common.c（只编译一次）+ 8m_globals_extern.h（extern 声明）
        preamble_lines = all_lines[:split_idx]
        # 去掉在 8m_runtime.h 中已有的函数定义，只保留变量声明
        # 去掉已在 8m_runtime.h 中定义的函数/宏（保留 weak 符号供 tb.c 覆盖）
        in_skip_block = False
        filtered_lines = []
        for l in preamble_lines:
            s = l.strip()
            if s.startswith('__attribute__') and 'weak' in s:
                filtered_lines.append(l)  # 保留 weak 函数（供 tb.c 覆盖）
                in_skip_block = True
                continue
            if s.startswith('static inline') or '#define FIELD_INDEX_GET' in s or '#define Max' in s or '#define Max3' in s or '_concat_range' in s:
                in_skip_block = True
                continue
            if in_skip_block:
                if s == '}':
                    in_skip_block = False
                continue
            if 'hash1' in s:
                continue
            filtered_lines.append(l)
        preamble_lines = filtered_lines
        preamble_text = '\n'.join(preamble_lines)
        for h_name in reg_drv_headers:
            preamble_text = preamble_text.replace(f'#include "{h_name}"',
                                                   f'#include "../include/{h_name}"')
        common_path = os.path.join(src_dir, "8m_common.c")
        with open(common_path, "w", encoding="utf-8") as f:
            f.write(preamble_text + '\n')
        if self.verbose:
            print(f"    {common_path} ({len(preamble_text)} bytes)")

        # 从 preamble 中提取变量声明 → extern 头文件
        extern_lines = []
        for l in preamble_lines:
            s = l.strip()
            # 匹配: uintXX_t varname = ...; 或 Type_entry_t varname;
            m = re.match(r'(?:\w+_entry_t|uint\d+_t|uint64_t)\s+(\w+)\s*=', s)
            if m:
                extern_lines.append(f"extern {s.split('=')[0].strip()};")
            elif re.match(r'\w+_entry_t\s+\w+\s*;', s):
                extern_lines.append(s)
        if extern_lines:
            extern_h = ("#ifndef _8M_GLOBALS_EXTERN_H_\n#define _8M_GLOBALS_EXTERN_H_\n\n"
                        "#include <stdint.h>\n\n"
                        + '\n'.join(extern_lines) + "\n\n"
                        "#endif /* _8M_GLOBALS_EXTERN_H_ */\n")
            extern_path = os.path.join(inc_dir, "8m_globals_extern.h")
            with open(extern_path, "w", encoding="utf-8") as f:
                f.write(extern_h)
            if self.verbose:
                print(f"    {extern_path} ({len(extern_h)} bytes) [extern decls]")

        # 各函数 → 独立 .c 文件（仅函数体 + include）
        current_file = None
        file_chunks: Dict[str, List[str]] = {}
        for l in all_lines[split_idx:]:
            m = re.match(r'/\* @8m-file:\s*(\S+)\s*\*/', l)
            if m:
                base = os.path.splitext(m.group(1))[0]
                current_file = f"8m_{base}.c"
                if current_file not in file_chunks:
                    file_chunks[current_file] = []  # 首次创建
                continue
            if current_file:
                file_chunks[current_file].append(l)

        base_includes = (
            '#include "../include/reg_drv_common.h"\n'
            '#include "../include/reg_drv_tinyReg.h"\n'
            '#include "../include/reg_drv_tinyReg2.h"\n'
            '#include "../include/8m_runtime.h"\n'
            '#include "../include/8m_globals_extern.h"\n'
            '#include <stdint.h>\n'
            '#include <string.h>\n'
            '\n'
            '/* Cross-file function prototypes */\n'
            'void parser(uint8_t *PacketByte);\n'
            'void switchX(void);\n'
            'void egress(void);\n'
            'void forward_tick(void);\n'
            'void updateStormCtrl_tick(void);\n'
            'void normalAging_tick(void);\n'
            'void fastAging_tick(void);\n'
            'void sendLoopDetect_tick(void);\n'
        )
        for fname, body_lines in file_chunks.items():
            body = '\n'.join(body_lines).strip()
            if not body:
                continue
            content = base_includes + '\n' + body + '\n'
            out_path = os.path.join(src_dir, fname)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
            if self.verbose:
                print(f"    {out_path} ({len(content)} bytes)")

        # ── 4. 直接在 c_project 内生成 reg_drv 文件 ──
        # .h → include/, .c → src/
        if hasattr(self, '_individual_reg_maps') and len(self._individual_reg_maps) > 1:
            # 共享宏文件 → include/
            common_macros = CRegDriverGenerator._gen_bitfield_macros()
            common_h = "#ifndef _REG_DRV_COMMON_H_\n#define _REG_DRV_COMMON_H_\n\n"
            common_h += "#include <stdint.h>\n\n"
            common_h += "\n".join(common_macros) + "\n\n"
            common_h += "#endif /* _REG_DRV_COMMON_H_ */\n"
            common_path = os.path.join(inc_dir, "reg_drv_common.h")
            with open(common_path, "w", encoding="utf-8") as f:
                f.write(common_h)
            if self.verbose:
                print(f"    {common_path} ({len(common_h)} bytes)")

            for i, reg_map in enumerate(self._individual_reg_maps):
                fname = os.path.splitext(os.path.basename(self.reg_paths[i]))[0] if i < len(self.reg_paths) else f"reg_{i}"
                drv_gen = CRegDriverGenerator(reg_map)
                header = drv_gen.generate_header(guard_suffix=fname)
                source = drv_gen.generate_source(header_name=fname)
                h_name = f"reg_drv_{fname}.h"
                c_name = f"reg_drv_{fname}.c"
                h_path = os.path.join(inc_dir, h_name)
                c_path = os.path.join(src_dir, c_name)
                with open(h_path, "w", encoding="utf-8") as f:
                    f.write(header)
                with open(c_path, "w", encoding="utf-8") as f:
                    f.write(source)
                if self.verbose:
                    print(f"    {h_path} ({len(header)} bytes)")
                    print(f"    {c_path} ({len(source)} bytes)")
        else:
            # 单 reg 文件 → 生成 reg_drv.h/.c 到 c_project
            drv_gen = CRegDriverGenerator(self.reg_map)
            header = drv_gen.generate_header()
            source = drv_gen.generate_source()
            h_path = os.path.join(inc_dir, "reg_drv.h")
            c_path = os.path.join(src_dir, "reg_drv.c")
            with open(h_path, "w", encoding="utf-8") as f:
                f.write(header)
            with open(c_path, "w", encoding="utf-8") as f:
                f.write(source)
            if self.verbose:
                print(f"    {h_path} ({len(header)} bytes)")
                print(f"    {c_path} ({len(source)} bytes)")

        # ── 5. 生成 Makefile ──
        c_files_in_src = sorted([f for f in os.listdir(src_dir) if f.endswith('.c')])
        objs = [f.replace('.c', '.o') for f in c_files_in_src]
        makefile = f"""# Auto-generated by 8m Compiler v0.2.0
# Project: {os.path.basename(self.spec_path)}

CC      = gcc
CFLAGS  = -std=c99 -w -fcommon -Iinclude
TARGET  = 8m_switch

SRCS    = {' '.join(f'src/{f}' for f in c_files_in_src)}
OBJS    = {' '.join(f'src/{f}' for f in objs)}

$(TARGET): $(OBJS)
\t$(CC) $(CFLAGS) -o $@ $^

src/%.o: src/%.c
\t$(CC) $(CFLAGS) -c -o $@ $<

.PHONY: clean
clean:
\trm -f $(OBJS) $(TARGET)

# Test with tb.c
tb: $(OBJS)
\t$(CC) $(CFLAGS) src/tb.c {' '.join(f'src/{f}' for f in c_files_in_src)} -o tb.exe
\t./tb.exe
"""
        mk_path = os.path.join(proj_dir, "Makefile")
        with open(mk_path, "w", encoding="utf-8") as f:
            f.write(makefile)
        if self.verbose:
            print(f"    {mk_path} ({len(makefile)} bytes)")

        print(f"\n  Multi-file C project generated: {proj_dir}")
        print(f"    include/  — header files (.h)")
        print(f"    src/      — source files (.c)")
        print(f"  Build: cd {proj_dir} && make")

        print(f"\n  Multi-file C project generated: {proj_dir}")
        print(f"  Build: cd {proj_dir} && make")

    # ------------------------------------------------------------------
    # Trace support: export switchX internal variables
    # ------------------------------------------------------------------

    def _generate_trace_files(self, codegen: CCodeGenerator, is_project: bool = False) -> None:
        """Generate 8m_trace_extern.h + 8m_trace.c from codegen trace data.

        After codegen._trace_enabled=True, _gen_function() collects
        all auto-declared + var-decl variable names per function.
        This method writes global extern declarations and definitions.
        """
        if not hasattr(codegen, '_trace_vars') or not codegen._trace_vars:
            return

        # Determine output directory
        if is_project:
            out_inc = os.path.join(self.output_dir, "c_project", "include")
            out_src = os.path.join(self.output_dir, "c_project", "src")
        else:
            out_inc = self.output_dir
            out_src = self.output_dir
        os.makedirs(out_inc, exist_ok=True)
        os.makedirs(out_src, exist_ok=True)

        # Collect all trace variable names (only uint32_t for now)
        all_trace_vars: set[str] = set()
        for fname, vnames in codegen._trace_vars.items():
            if fname == "_widths":
                continue
            if fname == "switchX":  # only export switchX internals
                all_trace_vars |= vnames

        if not all_trace_vars:
            return

        sorted_vars = sorted(all_trace_vars)

        # Generate 8m_trace_extern.h
        extern_lines = ['#ifndef _8M_TRACE_EXTERN_H_',
                        '#define _8M_TRACE_EXTERN_H_',
                        '',
                        '#include <stdint.h>',
                        '',
                        '/* Auto-generated trace variables for testbench observation */',
                        '/* These mirror switchX() local variables after each forward_tick() */',
                        '']
        for v in sorted_vars:
            extern_lines.append(f'extern uint32_t g_trace_{v};')
        extern_lines.append('')
        extern_lines.append('#endif /* _8M_TRACE_EXTERN_H_ */')
        extern_lines.append('')

        trace_h_path = os.path.join(out_inc, "8m_trace_extern.h")
        trace_h_content = '\n'.join(extern_lines)
        with open(trace_h_path, "w", encoding="utf-8") as f:
            f.write(trace_h_content)
        if self.verbose:
            print(f"    {trace_h_path} ({len(trace_h_content)} bytes) [trace externs]")

        # Generate 8m_trace.c (global variable definitions)
        trace_c_lines = ['/* Auto-generated trace variable definitions */',
                         '#include <stdint.h>',
                         '']
        for v in sorted_vars:
            trace_c_lines.append(f'uint32_t g_trace_{v} = 0;')
        trace_c_lines.append('')

        trace_c_path = os.path.join(out_src, "8m_trace.c")
        trace_c_content = '\n'.join(trace_c_lines)
        with open(trace_c_path, "w", encoding="utf-8") as f:
            f.write(trace_c_content)
        if self.verbose:
            print(f"    {trace_c_path} ({len(trace_c_content)} bytes) [trace defs]")

        # Also append the extern include to 8m_globals_extern.h for convenience
        globals_path = os.path.join(out_inc, "8m_globals_extern.h")
        if os.path.exists(globals_path):
            with open(globals_path, "r") as f:
                content = f.read()
            if '#include "8m_trace_extern.h"' not in content:
                # Insert before #endif
                content = content.replace(
                    '#endif /* _8M_GLOBALS_EXTERN_H_ */',
                    '#include "8m_trace_extern.h"\n\n#endif /* _8M_GLOBALS_EXTERN_H_ */'
                )
                with open(globals_path, "w") as f:
                    f.write(content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _gen_runtime_header(self) -> str:
        """Generate the 8m_runtime.h header with shared macros and helpers."""
        return """#ifndef _8M_RUNTIME_H_
#define _8M_RUNTIME_H_

#include <stdint.h>
#include <string.h>

#define FIELD_INDEX_GET(parent, field, idx) \\
    ((idx) == 0 ? (parent).field##0 : \\
     (idx) == 1 ? (parent).field##1 : \\
     (idx) == 2 ? (parent).field##2 : \\
     (parent).field##3)

/* External placeholder functions */
static inline uint32_t hash1(uint32_t v) { return v % 512; }
#define Max(a, b) ((a) > (b) ? (a) : (b))
#define Max3(a, b, c) Max(Max(a, b), c)
/* enqueue_packet/send_packet are weak symbols in 8m_common.c — tb.c overrides them */
void enqueue_packet(void *pkt, int len);
void send_packet(void *pkt, int len);

/* Global packet buffer */
extern uint8_t PacketByte[512];

static inline uint64_t _concat_range(uint32_t s, uint32_t e) {
    uint64_t result = 0;
    for (uint32_t i = s; i <= e; i++)
        result = (result << 8) | PacketByte[i];
    return result;
}

#endif /* _8M_RUNTIME_H_ */
"""

    def _dsl_h_to_c_h(self, text: str, guard: str, fname: str) -> str:
        """Convert a DSL .h file to a C .h file with include guard."""
        import re

        lines = []
        lines.append(f"#ifndef {guard}")
        lines.append(f"#define {guard}")
        lines.append("")
        lines.append("/* Auto-generated from DSL project */")
        lines.append("/* Original: " + fname + " */")
        lines.append("")
        lines.append("#include <stdint.h>")
        lines.append("")

        # 翻译 DSL 类型到 C 类型
        type_map = {
            'uint2': 'uint8_t', 'uint3': 'uint8_t', 'uint4': 'uint8_t', 'uint8': 'uint8_t',
            'uint12': 'uint16_t', 'uint16': 'uint16_t',
            'uint48': 'uint64_t', 'uint32': 'uint32_t',
            'bool': 'uint8_t',
        }

        in_struct = False
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped.startswith('/*') or stripped.startswith('**') or stripped.startswith('//'):
                lines.append(line)
                continue
            if not stripped:
                lines.append(line)
                continue

            if stripped.startswith('struct'):
                in_struct = True
            if in_struct and '}' in stripped:
                in_struct = False

            translated = line
            for dsl_t, c_t in type_map.items():
                translated = re.sub(r'\b' + dsl_t + r'\b', c_t, translated)
            translated = re.sub(r'\[\d+:\d+\]', '', translated)
            translated = re.sub(r'\s*=\s*\w+(\[\d+:\d+\])?\s*;', ';', translated)

            # DSL function prototype → C typed
            if re.match(r'\s*void\s+\w+\s*\(', translated):
                translated = re.sub(r'\(\s*PacketByte\s*\)', '(uint8_t *PacketByte)', translated)
            # 全局变量声明 → extern（但不在 struct 内部）
            elif not in_struct and re.match(r'\s*(?:uint8_t|uint16_t|uint32_t|uint64_t)\s+\w+', translated):
                if '=' not in translated:
                    translated = 'extern ' + translated
                    if not translated.rstrip().endswith(';'):
                        translated = translated.rstrip() + ';'

            lines.append(translated)

        lines.append("")
        lines.append("/* @externs */")
        lines.append("")
        lines.append(f"#endif /* {guard} */")
        return '\n'.join(lines)

    def _find_cross_file_externs(self, cf_name: str) -> List[str]:
        """Find variables defined in a .c that are used by other files.

        Returns list of C extern declarations like 'uint32_t prVlanId'.
        Skips function names (void parser, void switchX, etc.).
        """
        # Known function names (should NOT be extern-declared as variables)
        func_names = {'parser', 'switchX', 'egress',
                      'forward', 'updateStormCtrl', 'normalAging', 'fastAging', 'sendLoopDetect'}
        externs = []
        cf_base = os.path.splitext(cf_name)[0]
        cf_defines = self._file_defines.get(cf_name, set()) - func_names

        for other_cf in [os.path.basename(c) for c in self.c_files]:
            if other_cf == cf_name:
                continue
            other_uses = self._file_uses.get(other_cf, set()) - func_names
            common = cf_defines & other_uses
            for sym in common:
                externs.append(f"uint32_t {sym}")

        return externs
