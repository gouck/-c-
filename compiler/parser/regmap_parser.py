"""
compiler/parser/regmap_parser.py
Converts the output of TabLexer (structured dict) into AST node objects
(RegMapDef, MemTableDecl, RegisterDecl, FieldDecl).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from compiler.parser.ast_nodes import FieldDecl, MemTableDecl, RegisterDecl, RegMapDef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _str_to_bool(s: str) -> bool:
    """Convert "Y"/"N" (or "y"/"n") to Python bool."""
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
    Parser that transforms the TabLexer tokenize() output dictionary
    into a hierarchy of AST node objects.
    """

    def __init__(self, tab_lexer_result: Dict[str, Any]) -> None:
        """
        Initialize the parser with the lexer's output dictionary.

        Args:
            tab_lexer_result: The dictionary returned by TabLexer.tokenize(),
                              containing "config", "mem_tables", and "registers".
        """
        self._data: Dict[str, Any] = tab_lexer_result

    # ------------------------------------------------------------------
    # parse
    # ------------------------------------------------------------------

    def parse(self) -> RegMapDef:
        """
        Convert the raw lexer data into a RegMapDef AST node.

        Returns:
            A RegMapDef object populated with MemTableDecl and RegisterDecl
            nodes built from the lexer output.

        Raises:
            ValueError: If required fields are missing from the lexer data.
        """
        # -- validate top-level keys --
        for key in ("mem_tables", "registers"):
            if key not in self._data:
                raise ValueError(
                    f"Missing required key '{key}' in lexer output"
                )

        # -- convert mem_tables --
        mem_tables: List[MemTableDecl] = []
        for mt_dict in self._data["mem_tables"]:
            mem_tables.append(self._build_mem_table(mt_dict))

        # -- convert registers --
        registers: List[RegisterDecl] = []
        for reg_dict in self._data["registers"]:
            registers.append(self._build_register(reg_dict))

        return RegMapDef(
            mem_tables=mem_tables,
            registers=registers,
        )

    # ------------------------------------------------------------------
    # Field conversion (shared by mem_tables and registers)
    # ------------------------------------------------------------------

    def _build_field(self, field_dict: Dict[str, Any]) -> FieldDecl:
        """
        Convert a single field dictionary to a FieldDecl AST node.

        Handles both MemReg-style fields (read_trigger / write_trigger)
        and Register-style fields (read_only / read_indicate /
        write_indicate / write_one_indicate / default_value).

        Args:
            field_dict: Raw field dict from TabLexer output.

        Returns:
            A populated FieldDecl dataclass instance.

        Raises:
            ValueError: If required keys (name, offset, hi_bit, lo_bit)
                        are missing.
        """
        # -- required fields --
        for required in ("name", "offset", "hi_bit", "lo_bit"):
            if required not in field_dict:
                raise ValueError(
                    f"Field dict missing required key '{required}': {field_dict}"
                )

        # -- common attributes --
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

        # -- Register-specific booleans --
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

        # -- Register-specific default value --
        default_value: Optional[str] = None
        if "default" in field_dict:
            default_value = str(field_dict["default"])

        return FieldDecl(
            name=name,
            field_type=None,        # deferred to semantic analysis
            width=None,             # deferred to semantic analysis
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
    # MemTable conversion
    # ------------------------------------------------------------------

    def _build_mem_table(self, mt_dict: Dict[str, Any]) -> MemTableDecl:
        """
        Convert a raw mem_table dict to a MemTableDecl AST node.

        Args:
            mt_dict: Raw dict from TabLexer output's "mem_tables" list.

        Returns:
            A populated MemTableDecl dataclass instance.

        Raises:
            ValueError: If required keys are missing.
        """
        # -- validate required top-level keys --
        required_keys = (
            "name", "full_name", "num_entries", "words",
            "addr_bits", "decode_pattern", "description",
        )
        for key in required_keys:
            if key not in mt_dict:
                raise ValueError(
                    f"MemTable dict missing required key '{key}': {mt_dict}"
                )

        # -- convert fields --
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
    # Register conversion
    # ------------------------------------------------------------------

    def _build_register(self, reg_dict: Dict[str, Any]) -> RegisterDecl:
        """
        Convert a raw register dict to a RegisterDecl AST node.

        Args:
            reg_dict: Raw dict from TabLexer output's "registers" list.

        Returns:
            A populated RegisterDecl dataclass instance.

        Raises:
            ValueError: If required keys are missing.
        """
        # -- validate required top-level keys --
        required_keys = (
            "name", "full_name", "words", "decode_pattern", "description",
        )
        for key in required_keys:
            if key not in reg_dict:
                raise ValueError(
                    f"Register dict missing required key '{key}': {reg_dict}"
                )

        # -- convert fields --
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
