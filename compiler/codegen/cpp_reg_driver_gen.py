"""
compiler/codegen/c_reg_driver_gen.py
C register driver generator.
Generates C header (.h) and C source (.c) files from a RegMapDef AST,
providing struct definitions, address macros, and read/write functions.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from compiler.parser.ast_nodes import FieldDecl, MemTableDecl, RegisterDecl, RegMapDef


# ======================================================================
# Module-level helpers
# ======================================================================

# C keywords that conflict with field names
_C_KEYWORDS = {
    "static", "const", "volatile", "register", "auto",
    "extern", "typedef", "enum", "union", "struct",
    "sizeof", "if", "else", "for", "while", "do", "switch",
    "case", "break", "continue", "return", "goto", "default",
    "int", "char", "short", "long", "float", "double", "void",
}


def _sanitise_c_name(name: str) -> str:
    """Prefix C keywords with '__' to avoid conflicts (e.g. static → __static)."""
    if name in _C_KEYWORDS:
        return "__" + name
    return name


def _field_width(f: FieldDecl) -> int:
    """Bit-width of a field: hi_bit - lo_bit + 1."""
    return f.hi_bit - f.lo_bit + 1


def _decode_to_addr(pattern: str) -> int:
    """
    Convert a decode_pattern like 16'b00_100?_????_????_??  to a base address.

    Removes 'N'b prefix and '_' separators, replaces '?' with '0',
    then parses as binary → int (hex).
    """
    s = pattern.strip()
    # Remove Verilog-style width prefix  e.g. "16'b"
    if "'b" in s:
        _, _, s = s.partition("'b")
    # Remove underscores
    s = s.replace("_", "")
    # Replace wildcards with 0 for the base address
    s = s.replace("?", "0")
    return int(s, 2)


def _choose_uint_type(total_bits: int) -> str:
    """Return the smallest stdint uint type that holds total_bits bits."""
    if total_bits <= 8:
        return "uint8_t"
    if total_bits <= 16:
        return "uint16_t"
    if total_bits <= 32:
        return "uint32_t"
    return "uint64_t"


def _verilog_default_to_c(dv: str) -> str:
    """
    Convert a Verilog-style default value to a valid C 整数字面量.

    Supports:
        N'bXXXX  →  integer or  0xHHH...  (binary parsed)
        N'hXXXX  →  0xXXXX                (hex)
        plain decimal string → returned as-is
    """
    dv = dv.strip()
    # -- plain integer --
    if dv.isdigit() or (dv.startswith("-") and dv[1:].isdigit()):
        return dv
    # -- Verilog hex:  N'hXXXX --
    if "'h" in dv.lower():
        _, _, hex_part = dv.lower().partition("'h")
        hex_part = hex_part.replace("_", "")
        val = int(hex_part, 16)
        # Use 十六进制字面量 for readability if > 9
        if val <= 9:
            return str(val)
        return hex(val)  #  "0x..."
    # -- Verilog binary: N'bXXXX --
    if "'b" in dv.lower():
        _, _, bin_part = dv.lower().partition("'b")
        bin_part = bin_part.replace("_", "")
        val = int(bin_part, 2)
        if val <= 9:
            return str(val)
        return hex(val)  #  "0x..."
    # -- 回退方案: return as-is with a warning comment --
    return dv


# ======================================================================
# CRegDriverGenerator
# ======================================================================

class CRegDriverGenerator:
    """
    Generates C header and source files for register-level hardware access.

    The output is pure C (not C++) – uses <stdint.h>, struct bit-fields,
    and function-style register access macros.
    """

    def __init__(self, reg_map: RegMapDef) -> None:
        """
        Initialize the generator with a parsed register map.

        Args:
            reg_map: The RegMapDef AST node containing all memory tables
                     and register declarations.
        """
        self._reg_map: RegMapDef = reg_map

    # ==================================================================
    # Address macro generation
    # ==================================================================

    def _gen_address_macros(self) -> List[str]:
        """Generate #define address macros for all tables and registers."""
        lines: List[str] = []
        lines.append("/* =========================================================")
        lines.append(" * Address Macros")
        lines.append(" * ========================================================= */")
        lines.append("")

        # MemReg tables → NAME_ADDR_BASE + NAME_DEPTH
        for table in self._reg_map.mem_tables:
            name_upper = table.name.upper()
            addr = _decode_to_addr(table.decode_pattern)
            lines.append(
                "#define %-35s 0x%04X" % (name_upper + "_ADDR_BASE", addr)
            )
            lines.append(
                "#define %-35s %d" % (name_upper + "_DEPTH", table.num_entries)
            )
        lines.append("")

        # Registers → NAME_ADDR
        for reg in self._reg_map.registers:
            name_upper = reg.name.upper()
            addr = _decode_to_addr(reg.decode_pattern)
            lines.append(
                "#define %-35s 0x%04X" % (name_upper + "_ADDR", addr)
            )
        lines.append("")
        return lines

    # ==================================================================
    # BITFIELD macros
    # ==================================================================

    @staticmethod
    def _gen_bitfield_macros() -> List[str]:
        """Generate BITFIELD_GET / BITFIELD_SET helper macros."""
        return [
            "/* =========================================================",
            " * BITFIELD helper macros",
            " * ========================================================= */",
            "",
            "#define BITFIELD_GET(val, hi, lo) \\",
            "    (((val) >> (lo)) & ((1ULL << ((hi) - (lo) + 1)) - 1))",
            "",
            "#define BITFIELD_SET(val, hi, lo, field_val) \\",
            "    ((val) = ((val) & ~(((1ULL << ((hi) - (lo) + 1)) - 1) << (lo))) | \\",
            "     (((uint64_t)(field_val) & ((1ULL << ((hi) - (lo) + 1)) - 1)) << (lo)))",
            "",
        ]

    # ==================================================================
    # MemTable struct generation
    # ==================================================================

    def _gen_mem_table_struct(self, table: MemTableDecl) -> List[str]:
        """Generate struct + array declaration for a single memory table."""
        lines: List[str] = []
        name = table.name
        entry_type = name + "_entry_t"
        mem_array = name + "_mem"

        # -- special-case DsMacKey (8 words → uint32_t word[8]) --
        if name == "DsMacKey":
            return self._gen_dsmackey_struct(table, entry_type, mem_array)

        lines.append("/* =========================================================")
        lines.append(
            " * %s  (%d entries × %d word%s)"
            % (name, table.num_entries, table.words, "s" if table.words > 1 else "")
        )
        lines.append(" * ========================================================= */")

        # -- group fields by offset --
        by_offset: Dict[int, List[FieldDecl]] = {}
        for f in table.fields:
            by_offset.setdefault(f.offset, []).append(f)

        # -- determine base type per offset --
        offset_types: Dict[int, str] = {}
        for off, flist in by_offset.items():
            total = sum(_field_width(f) for f in flist)
            offset_types[off] = _choose_uint_type(total)

        # -- build struct body --
        lines.append("typedef struct {")
        for off in sorted(by_offset.keys()):
            flist = by_offset[off]
            base_type = offset_types[off]
            used_bits = 0
            for f in sorted(flist, key=lambda x: x.lo_bit):
                cname = _sanitise_c_name(f.name)
                w = _field_width(f)
                hi_lo = ("[%d]" % f.hi_bit) if f.hi_bit == f.lo_bit else "[%d:%d]" % (f.hi_bit, f.lo_bit)
                lines.append(
                    "    %-10s %-24s : %-2d;  /* offset=%d, %s */"
                    % (base_type, cname, w, off, hi_lo)
                )
                used_bits += w
            # pad if not filled to type width boundary
            type_width = {"uint8_t": 8, "uint16_t": 16, "uint32_t": 32, "uint64_t": 64}[base_type]
            if used_bits < type_width:
                pad_bits = type_width - used_bits
                lines.append(
                    "    %-10s __pad%-19d : %-2d;  /* padding */"
                    % (base_type, off, pad_bits)
                )
        lines.append("} %s;" % entry_type)
        lines.append("")
        lines.append("%s %s[%d];" % (entry_type, mem_array, table.num_entries))
        lines.append("")
        return lines

    # ==================================================================
    # DsMacKey special handling (8 words → uint32_t word[8] + inline fns)
    # ==================================================================

    def _gen_dsmackey_struct(
        self, table: MemTableDecl, entry_type: str, mem_array: str
    ) -> List[str]:
        """DsMacKey: 8-word table → raw word array + accessor inline functions."""
        lines: List[str] = []
        lines.append("/* =========================================================")
        lines.append(
            " * %s  (%d entries × %d words)  [raw word array]"
            % (table.name, table.num_entries, table.words)
        )
        lines.append(" * ========================================================= */")
        lines.append("")
        lines.append("typedef struct {")
        lines.append("    uint32_t word[%d];" % table.words)
        lines.append("} %s;" % entry_type)
        lines.append("")
        lines.append("%s %s[%d];" % (entry_type, mem_array, table.num_entries))
        lines.append("")

        # -- inline accessors: fid / macAddr per group g (0..3) --
        lines.append("/* ---- DsMacKey inline accessors ---- */")
        lines.append("")
        lines.append(
            "static inline uint16_t DsMacKey_get_fid(%s *e, int g) {" % entry_type
        )
        lines.append("    return (uint16_t)(e->word[g * 2] & 0xFFF);")
        lines.append("}")
        lines.append("")
        lines.append(
            "static inline uint64_t DsMacKey_get_macAddr(%s *e, int g) {" % entry_type
        )
        lines.append("    uint64_t hi = ((uint64_t)(e->word[g * 2] >> 16)) & 0xFFFF;")
        lines.append("    uint64_t lo = (uint64_t)e->word[g * 2 + 1];")
        lines.append("    return (hi << 32) | lo;")
        lines.append("}")
        lines.append("")
        lines.append(
            "static inline void DsMacKey_set_fid(%s *e, int g, uint16_t fid) {" % entry_type
        )
        lines.append("    e->word[g * 2] = (e->word[g * 2] & 0xFFFFF000) | (fid & 0xFFF);")
        lines.append("}")
        lines.append("")
        lines.append(
            "static inline void DsMacKey_set_macAddr(%s *e, int g, uint64_t mac) {"
            % entry_type
        )
        lines.append("    e->word[g * 2] = (e->word[g * 2] & 0xFFF) | ((uint32_t)((mac >> 32) & 0xFFFF) << 16);")
        lines.append("    e->word[g * 2 + 1] = (uint32_t)(mac & 0xFFFFFFFF);")
        lines.append("}")
        lines.append("")
        return lines

    # ==================================================================
    # Register struct generation
    # ==================================================================

    def _gen_register_struct(self, reg: RegisterDecl) -> List[str]:
        """Generate struct + global variable for a single register."""
        lines: List[str] = []
        name = reg.name
        struct_type = name + "_t"

        lines.append("/* =========================================================")
        lines.append(
            " * %s Register (%d word%s)"
            % (name, reg.words, "s" if reg.words > 1 else "")
        )
        lines.append(" * ========================================================= */")

        # -- group fields by offset --
        by_offset: Dict[int, List[FieldDecl]] = {}
        for f in reg.fields:
            by_offset.setdefault(f.offset, []).append(f)

        # -- determine base type per offset --
        offset_types: Dict[int, str] = {}
        for off, flist in by_offset.items():
            total = sum(_field_width(f) for f in flist)
            offset_types[off] = _choose_uint_type(total)

        lines.append("typedef struct {")
        for off in sorted(by_offset.keys()):
            flist = by_offset[off]
            base_type = offset_types[off]
            used_bits = 0
            for f in sorted(flist, key=lambda x: x.lo_bit):
                cname = _sanitise_c_name(f.name)
                w = _field_width(f)
                hi_lo = ("[%d]" % f.hi_bit) if f.hi_bit == f.lo_bit else "[%d:%d]" % (f.hi_bit, f.lo_bit)
                # annotate default value if present
                default_note = ""
                if f.default_value is not None:
                    default_note = "  /* default=%s */" % f.default_value
                lines.append(
                    "    %-10s %-24s : %-2d;  /* offset=%d, %s */%s"
                    % (base_type, cname, w, off, hi_lo, default_note)
                )
                used_bits += w
            # pad if not filled
            type_width = {"uint8_t": 8, "uint16_t": 16, "uint32_t": 32, "uint64_t": 64}[base_type]
            if used_bits < type_width:
                pad_bits = type_width - used_bits
                lines.append(
                    "    %-10s __pad%-19d : %-2d;  /* padding */"
                    % (base_type, off, pad_bits)
                )
        lines.append("} %s;" % struct_type)
        lines.append("")
        # -- global variable (no initialiser; reg_init handles defaults) --
        lines.append("extern %s %s;" % (struct_type, name))
        lines.append("")
        return lines

    # ==================================================================
    # reg_init helper
    # ==================================================================

    def _gen_reg_init_decl(self) -> List[str]:
        """Declaration of reg_init() for the header."""
        return [
            "/* =========================================================",
            " * Register initialisation",
            " * ========================================================= */",
            "",
            "void reg_init(void);",
            "",
        ]

    def _gen_reg_init_impl(self) -> List[str]:
        """Implementation of reg_init() that sets default values."""
        lines: List[str] = []
        lines.append("/* =========================================================")
        lines.append(" * reg_init – apply default register values at startup")
        lines.append(" * ========================================================= */")
        lines.append("void reg_init(void) {")

        for reg in self._reg_map.registers:
            has_defaults = any(f.default_value is not None for f in reg.fields)
            if not has_defaults:
                continue
            lines.append("    /* ---- %s ---- */" % reg.name)
            for f in reg.fields:
                if f.default_value is None:
                    continue
                cname = _sanitise_c_name(f.name)
                dv = f.default_value
                c_val = _verilog_default_to_c(dv)
                lines.append(
                    "    %s.%s = %s;  /* default=%s, %s */"
                    % (reg.name, cname, c_val, dv, f.description)
                )
        lines.append("}")
        lines.append("")
        return lines

    # ==================================================================
    # Header generation
    # ==================================================================

    def generate_header(self, guard_suffix: str = "") -> str:
        """
        Generate the C header file content.

        Args:
            guard_suffix: If non-empty, appended to the include guard macro name
                          to allow multiple reg_drv headers to coexist.
                          e.g. "tinyReg" → _REG_DRV_TINYREG_H_

        Returns:
            A string containing the complete C header file.
        """
        buf: List[str] = []

        # -- unique include guard --
        guard = "_REG_DRV_H_"
        if guard_suffix:
            guard = f"_REG_DRV_{guard_suffix.upper()}_H_"
        buf.append(f"#ifndef {guard}")
        buf.append(f"#define {guard}")
        buf.append("")
        buf.append("#include <stdint.h>")
        buf.append("")

        # -- address macros --
        buf.extend(self._gen_address_macros())

        # -- bitfield macros (only in the base header, skip for split files) --
        if not guard_suffix:
            buf.extend(self._gen_bitfield_macros())

        # -- mem table structs --
        for table in self._reg_map.mem_tables:
            buf.extend(self._gen_mem_table_struct(table))

        # -- register structs --
        for reg in self._reg_map.registers:
            buf.extend(self._gen_register_struct(reg))

        # -- reg_init declaration --
        buf.extend(self._gen_reg_init_decl())

        # -- include guard close --
        buf.append(f"#endif /* {guard} */")
        return "\n".join(buf) + "\n"

    # ==================================================================
    # Source generation
    # ==================================================================

    def generate_source(self, header_name: str = "") -> str:
        """
        Generate the C source file content.

        Args:
            header_name: If non-empty, used as the #include target instead
                         of the default "reg_drv.h".  Used in split-reg mode.
                         e.g. "tinyReg" → #include "reg_drv_tinyReg.h"

        Returns:
            A string containing the complete C source file.
        """
        buf: List[str] = []

        inc = f'"reg_drv_{header_name}.h"' if header_name else '"reg_drv.h"'
        buf.append(f'#include {inc}')
        buf.append("")

        # -- global register variable definitions --
        for reg in self._reg_map.registers:
            buf.append("%s_t %s;" % (reg.name, reg.name))
        buf.append("")

        # -- reg_init implementation --
        buf.extend(self._gen_reg_init_impl())

        return "\n".join(buf) + "\n"
