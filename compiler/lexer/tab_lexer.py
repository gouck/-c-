"""
compiler/lexer/tab_lexer.py
制表符分隔的寄存器表DSL词法分析器.
Reads tinyReg.txt (tab-delimited register table DSL) and parses it
into structured data.
"""

from typing import Any, Dict, List, Optional, Tuple


class TabLexerError(Exception):
    """制表符DSL词法分析过程中遇到的异常"""

    def __init__(self, message: str, line_no: int = 0) -> None:
        line_info = f" (line {line_no})" if line_no else ""
        super().__init__(f"TabLexerError{line_info}: {message}")
        self.line_no = line_no


class TabLexer:
    """
    制表符分隔的寄存器表DSL（tinyReg.txt）词法分析器

    将源文本解析为包含三个部分的结构化字典：
        - config:        全局配置键值对
        - mem_tables:    内存映射表定义列表
        - registers:     寄存器定义列表

    每条内存表条目包含：
        name, full_name, num_entries, words, addr_bits, decode_pattern,
        description, fields (list of field dicts)

    每条寄存器条目包含：
        name, full_name, words, decode_pattern, description,
        fields (list of field dicts)

    每条字段条目包含：
        name, offset, hi_bit, lo_bit, plus table/register-specific attributes
    """

    def __init__(self, source_text: str) -> None:
        """
        用DSL文件的完整源文本初始化词法分析器

        Args:
            source_text: tinyReg.txt 文件的完整内容字符串
        """
        self.source_text: str = source_text
        self._lines: list[str] = []
        self._pos: int = 0

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_int(s: str) -> int:
        """将去除空白的字符串转换为整数；失败时抛出 TabLexerError"""
        try:
            return int(s.strip())
        except ValueError:
            raise TabLexerError(f"Expected integer, got '{s}'")

    # ------------------------------------------------------------------
    # 主解析方法 tokenize
    # ------------------------------------------------------------------

    def tokenize(self) -> Dict[str, Any]:
        """
        解析源文本并返回结构化数据

        Returns:
            包含以下键的字典：
                "config"      -> 全局设置字典
                "mem_tables"  -> 内存表条目字典列表
                "registers"   -> 寄存器条目字典列表

        Raises:
            TabLexerError: 源文本无法解析时抛出
        """
        raw_lines: List[str] = self.source_text.splitlines()

        # ---- 过滤完全空行，保留基于1的行号 ----
        lines: List[Tuple[int, str]] = []  #  (line_no, stripped_content)
        for i, raw in enumerate(raw_lines, start=1):
            s = raw.strip()
            if s:
                lines.append((i, s))

        if len(lines) < 2:
            raise TabLexerError(
                "File must contain at least a header row and a config row"
            )

        result: Dict[str, Any] = {
            "config": {},
            "mem_tables": [],
            "registers": [],
        }

        # ---- 解析状态 ----
        section: Optional[str] = None  #  "regmem" | "mem_fields" | "register" | "reg_fields"
        current_table_name: str = ""
        current_mem_table: Optional[Dict[str, Any]] = None
        current_register: Optional[Dict[str, Any]] = None
        skip_next: bool = False  #  在MemRegFields之后设置，用于跳过字段表头

        idx: int = 0

        # -- line 0: config column header → skip --
        idx += 1  #  skip "FileName\tPrefix\tAddrUpper\tAddrLower\tFlopInput"

        # -- 第1行：配置数据 --
        if idx >= len(lines):
            raise TabLexerError("Missing config row")
        _, config_line = lines[idx]
        idx += 1
        config_parts: List[str] = config_line.split("\t")
        if len(config_parts) < 5:
            raise TabLexerError(
                f"Config row has {len(config_parts)} columns, expected >=5"
            )
        result["config"] = {
            "file_name": config_parts[0].strip(),
            "prefix": config_parts[1].strip(),
            "addr_upper": self._safe_int(config_parts[2]),
            "addr_lower": self._safe_int(config_parts[3]),
            "flop_input": config_parts[4].strip(),
        }

        # ---- 主状态机循环 ----
        while idx < len(lines):
            lineno, line = lines[idx]

            # -- 处理延迟的字段表头跳过（MemRegFields之后） --
            if skip_next:
                # This line must be a "Fields\t..." header for mem fields → skip
                skip_next = False
                idx += 1
                continue

            first_col: str = line.split("\t", 1)[0].strip()

            # ==================================================================
            # 段落检测
            # ==================================================================

            if first_col == "RegMem":
                # RegMem section column-header row → skip, enter regmem mode
                section = "regmem"
                idx += 1
                continue

            if first_col == "MemRegFields":
                # MemRegFields\tTableName  →  进入 mem_fields 模式
                parts = line.split("\t")
                if len(parts) < 2:
                    raise TabLexerError(
                        f"MemRegFields line missing table name", lineno
                    )
                current_table_name = parts[1].strip()
                section = "mem_fields"
                skip_next = True  #  next line is the "Fields\t..." header → skip
                idx += 1
                continue

            if first_col == "Register":
                # Register section column-header row → skip, enter register mode
                section = "register"
                idx += 1
                continue

            if first_col == "Fields":
                # "Fields" header row — distinguish by section context
                if section == "regmem":
                    # Fields immediately after a RegMem entry list → register fields
                    parts = line.split("\t")
                    # last column holds the register name
                    current_table_name = ""  #  not relevant for registers
                    # Determine register name: the last non-empty column
                    reg_name = parts[-1].strip() if len(parts) > 1 else ""
                    # Find the register this belongs to
                    # match by name in existing registers list
                    current_register = None
                    for reg in result["registers"]:
                        if reg["name"] == reg_name:
                            current_register = reg
                            break
                    if current_register is None:
                        # If we can't match, create a 占位 note
                        # (should not happen with well-formed input)
                        current_register = None
                    section = "reg_fields"
                    idx += 1
                    continue
                else:
                    # In "register" section or unknown context → register fields
                    parts = line.split("\t")
                    reg_name = parts[-1].strip() if len(parts) > 1 else ""
                    # Try to match to an existing register
                    for reg in result["registers"]:
                        if reg["name"] == reg_name:
                            current_register = reg
                            break
                    section = "reg_fields"
                    idx += 1
                    continue

            # ==================================================================
            # 按段落解析数据
            # ==================================================================

            if section == "regmem":
                # 解析 RegMem 条目：
                # name | full_name | num_entries | words | addr_bits | decode_pattern | description
                parts = line.split("\t")
                if len(parts) < 7:
                    raise TabLexerError(
                        f"RegMem entry has {len(parts)} columns, expected >=7",
                        lineno,
                    )
                entry: Dict[str, Any] = {
                    "name": parts[0].strip(),
                    "full_name": parts[1].strip(),
                    "num_entries": self._safe_int(parts[2]),
                    "words": self._safe_int(parts[3]),
                    "addr_bits": self._safe_int(parts[4]),
                    "decode_pattern": parts[5].strip(),
                    "description": parts[6].strip(),
                    "fields": [],
                }
                result["mem_tables"].append(entry)
                idx += 1
                continue

            if section == "mem_fields":
                # 解析内存表字段：
                # name | offset | hi_bit | lo_bit | read_trigger | write_trigger | description
                parts = line.split("\t")
                if len(parts) < 7:
                    raise TabLexerError(
                        f"MemReg field line has {len(parts)} columns, expected >=7",
                        lineno,
                    )
                field: Dict[str, Any] = {
                    "name": parts[0].strip(),
                    "offset": self._safe_int(parts[1]),
                    "hi_bit": self._safe_int(parts[2]),
                    "lo_bit": self._safe_int(parts[3]),
                    "read_trigger": parts[4].strip(),
                    "write_trigger": parts[5].strip(),
                    "description": parts[6].strip(),
                }
                # 按名称追加到对应的内存表
                for tbl in result["mem_tables"]:
                    if tbl["name"] == current_table_name:
                        tbl["fields"].append(field)
                        break
                idx += 1
                continue

            if section == "register":
                # 解析 Register 条目：
                # name | full_name | words | decode_pattern | description
                parts = line.split("\t")
                if len(parts) < 5:
                    raise TabLexerError(
                        f"Register entry has {len(parts)} columns, expected >=5",
                        lineno,
                    )
                reg: Dict[str, Any] = {
                    "name": parts[0].strip(),
                    "full_name": parts[1].strip(),
                    "words": self._safe_int(parts[2]),
                    "decode_pattern": parts[3].strip(),
                    "description": parts[4].strip(),
                    "fields": [],
                }
                result["registers"].append(reg)
                idx += 1
                continue

            if section == "reg_fields":
                # 解析寄存器字段：
                # name | offset | hi_bit | lo_bit | read_only | read_indicate
                # | write_indicate | write_one_indicate | description | default
                parts = line.split("\t")
                if len(parts) < 9:
                    raise TabLexerError(
                        f"Register field line has {len(parts)} columns, expected >=9",
                        lineno,
                    )
                reg_field: Dict[str, Any] = {
                    "name": parts[0].strip(),
                    "offset": self._safe_int(parts[1]),
                    "hi_bit": self._safe_int(parts[2]),
                    "lo_bit": self._safe_int(parts[3]),
                    "read_only": parts[4].strip(),
                    "read_indicate": parts[5].strip(),
                    "write_indicate": parts[6].strip(),
                    "write_one_indicate": parts[7].strip(),
                    "description": parts[8].strip(),
                }
                # 第9列（如果存在）为默认值
                if len(parts) >= 10:
                    reg_field["default"] = parts[9].strip()
                # 追加到匹配的寄存器
                if current_register is not None:
                    current_register["fields"].append(reg_field)
                idx += 1
                continue

            # ---- 无法识别的行 ----
            raise TabLexerError(
                f"Unexpected section: '{first_col}'",
                lineno,
            )

        return result
