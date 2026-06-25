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
        reg_path: str,
        output_dir: str,
        target: str,
        verbose: bool,
    ) -> None:
        self.spec_path: str = spec_path
        self.reg_path: str = reg_path
        self.output_dir: str = output_dir
        self.target: str = target
        self.verbose: bool = verbose

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
        # tinyReg.txt → structured dict
        with open(self.reg_path, "r", encoding="utf-8") as f:
            reg_text = f.read()
        lexer = TabLexer(reg_text)
        self.reg_data = lexer.tokenize()
        if self.verbose:
            print(f"    Register file: {len(self.reg_data.get('mem_tables',[]))} tables, "
                  f"{len(self.reg_data.get('registers',[]))} registers")

        # 8mSpec_0821.c → Token list
        with open(self.spec_path, "r", encoding="utf-8") as f:
            spec_text = f.read()
        spec_lexer = PseudoCLexer(spec_text)
        tokens = spec_lexer.tokenize()
        self.spec_tokens = [t for t in tokens if t.type != TokenType.NEWLINE]
        if self.verbose:
            print(f"    Spec file: {len(tokens)} tokens ({len(self.spec_tokens)} non-NEWLINE)")
        self.unknown_keywords = getattr(spec_lexer, '_unknown_keywords', set())

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
        # Register map → RegMapDef
        parser = RegMapParser(self.reg_data)
        self.reg_map = parser.parse()
        if self.verbose:
            print(f"    Register map: {len(self.reg_map.mem_tables)} tables, "
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
            # 排除已知的表名、寄存器名（这些是数据，不是语法）
            reg_names = set()
            if self.reg_data:
                for t in self.reg_data.get('mem_tables', []):
                    reg_names.add(t.get('name', ''))
                for r in self.reg_data.get('registers', []):
                    reg_names.add(r.get('name', ''))
            # 排除已知的 built-in 宏和全局变量
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

        # -- reg_drv.h / reg_drv.c --
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

        # -- output.c (main logic) --
        codegen = CCodeGenerator(self.translation_unit, self.symtab)
        main_code = codegen.generate()
        out_path = os.path.join(self.output_dir, "output.c")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(main_code)
        if self.verbose:
            print(f"    {out_path} ({len(main_code)} bytes)")
