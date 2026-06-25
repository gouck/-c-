"""
compiler/lexer/tab_lexer.py
Tab-separated register table DSL lexer.
Reads tinyReg.txt (tab-delimited register table DSL) and parses it
into structured data.
"""

from typing import Any, Dict, List, Optional, Tuple


class TabLexerError(Exception):
    """Exception raised for errors encountered during lexing of the tab-separated DSL."""

    def __init__(self, message: str, line_no: int = 0) -> None:
        line_info = f" (line {line_no})" if line_no else ""
        super().__init__(f"TabLexerError{line_info}: {message}")
        self.line_no = line_no


class TabLexer:
    """
    Lexer for the tab-separated register table DSL (tinyReg.txt).

    Parses the source text into a structured dictionary with three sections:
        - config:        global configuration key-value pairs
        - mem_tables:    list of memory-mapped table definitions
        - registers:     list of register definitions

    Each mem_table entry contains:
        name, full_name, num_entries, words, addr_bits, decode_pattern,
        description, fields (list of field dicts)

    Each register entry contains:
        name, full_name, words, decode_pattern, description,
        fields (list of field dicts)

    Each field entry contains:
        name, offset, hi_bit, lo_bit, plus table/register-specific attributes
    """

    def __init__(self, source_text: str) -> None:
        """
        Initialize the lexer with the full source text of the DSL file.

        Args:
            source_text: The complete contents of the tinyReg.txt file as a string.
        """
        self.source_text: str = source_text
        self._lines: list[str] = []
        self._pos: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_int(s: str) -> int:
        """Convert a stripped string to int; raises TabLexerError on failure."""
        try:
            return int(s.strip())
        except ValueError:
            raise TabLexerError(f"Expected integer, got '{s}'")

    # ------------------------------------------------------------------
    # Main tokenize
    # ------------------------------------------------------------------

    def tokenize(self) -> Dict[str, Any]:
        """
        Parse the source text and return structured data.

        Returns:
            A dictionary with keys:
                "config"      -> dict of global settings
                "mem_tables"  -> list of memory table entry dicts
                "registers"   -> list of register entry dicts

        Raises:
            TabLexerError: If the source text cannot be parsed.
        """
        raw_lines: List[str] = self.source_text.splitlines()

        # ---- filter out completely empty lines, preserving 1-based line numbers ----
        lines: List[Tuple[int, str]] = []  # (line_no, stripped_content)
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

        # ---- parsing state ----
        section: Optional[str] = None  # "regmem" | "mem_fields" | "register" | "reg_fields"
        current_table_name: str = ""
        current_mem_table: Optional[Dict[str, Any]] = None
        current_register: Optional[Dict[str, Any]] = None
        skip_next: bool = False  # set after MemRegFields to skip the field header

        idx: int = 0

        # -- line 0: config column header → skip --
        idx += 1  # skip "FileName\tPrefix\tAddrUpper\tAddrLower\tFlopInput"

        # -- line 1: config data --
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

        # ---- main state-machine loop ----
        while idx < len(lines):
            lineno, line = lines[idx]

            # -- handle deferred field-header skip (after MemRegFields) --
            if skip_next:
                # This line must be a "Fields\t..." header for mem fields → skip
                skip_next = False
                idx += 1
                continue

            first_col: str = line.split("\t", 1)[0].strip()

            # ==================================================================
            # Section detection
            # ==================================================================

            if first_col == "RegMem":
                # RegMem section column-header row → skip, enter regmem mode
                section = "regmem"
                idx += 1
                continue

            if first_col == "MemRegFields":
                # MemRegFields\tTableName  →  enter mem_fields mode
                parts = line.split("\t")
                if len(parts) < 2:
                    raise TabLexerError(
                        f"MemRegFields line missing table name", lineno
                    )
                current_table_name = parts[1].strip()
                section = "mem_fields"
                skip_next = True  # next line is the "Fields\t..." header → skip
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
                    current_table_name = ""  # not relevant for registers
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
                        # If we can't match, create a placeholder note
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
            # Data parsing by section
            # ==================================================================

            if section == "regmem":
                # Parse RegMem entry:
                #   name | full_name | num_entries | words | addr_bits | decode_pattern | description
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
                # Parse memory table field:
                #   name | offset | hi_bit | lo_bit | read_trigger | write_trigger | description
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
                # Append to the correct mem_table by name
                for tbl in result["mem_tables"]:
                    if tbl["name"] == current_table_name:
                        tbl["fields"].append(field)
                        break
                idx += 1
                continue

            if section == "register":
                # Parse Register entry:
                #   name | full_name | words | decode_pattern | description
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
                # Parse register field:
                #   name | offset | hi_bit | lo_bit | read_only | read_indicate
                #   | write_indicate | write_one_indicate | description | default
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
                # Column 9 (if present) is the default value
                if len(parts) >= 10:
                    reg_field["default"] = parts[9].strip()
                # Append to the matched register
                if current_register is not None:
                    current_register["fields"].append(reg_field)
                idx += 1
                continue

            # ---- unrecognized line ----
            raise TabLexerError(
                f"Unexpected section: '{first_col}'",
                lineno,
            )

        return result
