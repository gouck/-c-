"""
compiler/parser/regmap_parser.py
将 TabLexer 的输出（结构化字典）转换为 AST 节点对象
(RegMapDef, MemTableDecl, RegisterDecl, FieldDecl).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from compiler.parser.ast_nodes import FieldDecl, MemTableDecl, RegisterDecl, RegMapDef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _str_to_bool(s: str) -> bool:
    """将 "Y"/"N"（或 "y"/"n"）转换为 Python bool"""
    ch = s.strip().upper() if s else ""
    if ch == "Y":
        return True
    if ch == "N":
        return False
    raise ValueError(f"Expected 'Y' or 'N', got {s!r}")


# ---------------------------------------------------------------------------
# RegMapParser
# ---------------------------------------------------------------------------

class RegMapParser:
    """
    将 TabLexer.tokenize() 的输出字典转换为
    AST 节点对象层次结构
    """

    def __init__(self, tab_lexer_result: Dict[str, Any]) -> None:
        """
        用词法分析器的输出字典初始化解析器

        Args:
            tab_lexer_result: TabLexer.tokenize() 返回的字典
                              containing "config", "mem_tables", and "registers".
        """
        self._data: Dict[str, Any] = tab_lexer_result

    # ------------------------------------------------------------------
    # parse
    # ------------------------------------------------------------------

    def parse(self) -> RegMapDef:
        """
        将原始词法分析器数据转换为 RegMapDef AST 节点

        Returns:
            由 MemTableDecl 和 RegisterDecl 填充的 RegMapDef 对象
            节点（由词法分析器输出构建）

        Raises:
            ValueError: 词法分析器数据中缺少必需字段时抛出
        """
        # -- 验证顶层键 --
        for key in ("mem_tables", "registers"):
            if key not in self._data:
                raise ValueError(
                    f"Missing required key '{key}' in lexer output"
                )

        # -- 转换 mem_tables --
        mem_tables: List[MemTableDecl] = []
        for mt_dict in self._data["mem_tables"]:
            mem_tables.append(self._build_mem_table(mt_dict))

        # -- 转换 registers --
        registers: List[RegisterDecl] = []
        for reg_dict in self._data["registers"]:
            registers.append(self._build_register(reg_dict))

        return RegMapDef(
            mem_tables=mem_tables,
            registers=registers,
        )

    # ------------------------------------------------------------------
    # 字段转换（内存表和寄存器共用）
    # ------------------------------------------------------------------

    def _build_field(self, field_dict: Dict[str, Any]) -> FieldDecl:
        """
        将单个字段字典转换为 FieldDecl AST 节点

        同时处理 MemReg 风格字段（read_trigger / write_trigger）
        和 Register 风格字段（read_only / read_indicate /
        write_indicate / write_one_indicate / default_value）

        Args:
            field_dict: TabLexer 输出中的原始字段字典

        Returns:
            填充好的 FieldDecl 数据类实例

        Raises:
            ValueError: 缺少必需的键（name, offset, hi_bit, lo_bit）时抛出
                        are missing.
        """
        # -- 必需字段 --
        for required in ("name", "offset", "hi_bit", "lo_bit"):
            if required not in field_dict:
                raise ValueError(
                    f"Field dict missing required key '{required}': {field_dict}"
                )

        # -- 公共属性 --
        name: str = field_dict["name"]
        offset: int = int(field_dict["offset"])
        hi_bit: int = int(field_dict["hi_bit"])
        lo_bit: int = int(field_dict["lo_bit"])
        description: str = field_dict.get("description", "")

        # -- MemReg-specific booleans (present → convert; absent → False) --
        read_trigger: bool = False
        write_trigger: bool = False
        if "read_trigger" in field_dict:
            read_trigger = _str_to_bool(field_dict["read_trigger"])
        if "write_trigger" in field_dict:
            write_trigger = _str_to_bool(field_dict["write_trigger"])

        # -- Register 特有布尔值 --
        read_only: bool = False
        read_indicate: bool = False
        write_indicate: bool = False
        write_one_indicate: bool = False
        if "read_only" in field_dict:
            read_only = _str_to_bool(field_dict["read_only"])
        if "read_indicate" in field_dict:
            read_indicate = _str_to_bool(field_dict["read_indicate"])
        if "write_indicate" in field_dict:
            write_indicate = _str_to_bool(field_dict["write_indicate"])
        if "write_one_indicate" in field_dict:
            write_one_indicate = _str_to_bool(field_dict["write_one_indicate"])

        # -- Register 特有默认值 --
        default_value: Optional[str] = None
        if "default" in field_dict:
            default_value = str(field_dict["default"])

        return FieldDecl(
            name=name,
            field_type=None,        #  推迟到语义分析阶段确定
            width=None,             #  推迟到语义分析阶段确定
            offset=offset,
            hi_bit=hi_bit,
            lo_bit=lo_bit,
            description=description,
            read_trigger=read_trigger,
            write_trigger=write_trigger,
            read_only=read_only,
            read_indicate=read_indicate,
            write_indicate=write_indicate,
            write_one_indicate=write_one_indicate,
            default_value=default_value,
        )

    # ------------------------------------------------------------------
    # 内存表转换
    # ------------------------------------------------------------------

    def _build_mem_table(self, mt_dict: Dict[str, Any]) -> MemTableDecl:
        """
        将原始内存表字典转换为 MemTableDecl AST 节点

        Args:
            mt_dict: TabLexer 输出中 "mem_tables" 列表的原始字典

        Returns:
            填充好的 MemTableDecl 数据类实例

        Raises:
            ValueError: 缺少必需键时抛出
        """
        # -- 验证必需的顶层键 --
        required_keys = (
            "name", "full_name", "num_entries", "words",
            "addr_bits", "decode_pattern", "description",
        )
        for key in required_keys:
            if key not in mt_dict:
                raise ValueError(
                    f"MemTable dict missing required key '{key}': {mt_dict}"
                )

        # -- 转换字段 --
        fields: List[FieldDecl] = []
        for fd in mt_dict.get("fields", []):
            fields.append(self._build_field(fd))

        return MemTableDecl(
            name=mt_dict["name"],
            full_name=mt_dict["full_name"],
            num_entries=int(mt_dict["num_entries"]),
            words=int(mt_dict["words"]),
            addr_bits=int(mt_dict["addr_bits"]),
            decode_pattern=mt_dict["decode_pattern"],
            description=mt_dict["description"],
            fields=fields,
        )

    # ------------------------------------------------------------------
    # 寄存器转换
    # ------------------------------------------------------------------

    def _build_register(self, reg_dict: Dict[str, Any]) -> RegisterDecl:
        """
        Convert a raw register dict to a RegisterDecl AST node.

        Args:
            reg_dict: Raw dict from TabLexer output's "registers" list.

        Returns:
            A populated RegisterDecl dataclass instance.

        Raises:
            ValueError: 缺少必需键时抛出
        """
        # -- 验证必需的顶层键 --
        required_keys = (
            "name", "full_name", "words", "decode_pattern", "description",
        )
        for key in required_keys:
            if key not in reg_dict:
                raise ValueError(
                    f"Register dict missing required key '{key}': {reg_dict}"
                )

        # -- 转换字段 --
        fields: List[FieldDecl] = []
        for fd in reg_dict.get("fields", []):
            fields.append(self._build_field(fd))

        return RegisterDecl(
            name=reg_dict["name"],
            full_name=reg_dict["full_name"],
            words=int(reg_dict["words"]),
            decode_pattern=reg_dict["decode_pattern"],
            description=reg_dict["description"],
            fields=fields,
        )
