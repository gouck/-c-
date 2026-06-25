"""
compiler/utils/bit_utils.py
Bit-manipulation utility functions used throughout the compiler.
"""

from __future__ import annotations

from typing import Optional


def bit_width(value: int) -> int:
    """
    Return the minimum number of bits required to represent a non-negative integer.

    Args:
        value: A non-negative integer.

    Returns:
        The bit-width needed to represent ``value`` in binary.
        Returns 1 for value == 0 (since 0 is represented as 1'b0).

    Examples:
        >>> bit_width(0)
        1
        >>> bit_width(1)
        1
        >>> bit_width(255)
        8
        >>> bit_width(256)
        9
    """
    if value < 0:
        raise ValueError(f"bit_width() expects a non-negative integer, got {value}")
    if value == 0:
        return 1
    return value.bit_length()


def try_constant_fold(op: str, left: object, right: object) -> Optional[int]:
    """
    Attempt to constant-fold a binary operation at compile time.

    Args:
        op: The operator string (e.g. "+", "-", "*", "/", "%",
            "<<", ">>", "&", "|", "^").
        left: Left operand (must be int for folding to succeed).
        right: Right operand (must be int for folding to succeed).

    Returns:
        The folded integer result, or None if folding is not possible
        (e.g. non-integer operands, division by zero, unknown operator).
    """
    if not isinstance(left, int) or not isinstance(right, int):
        return None

    try:
        if op == "+":
            return left + right
        elif op == "-":
            return left - right
        elif op == "*":
            return left * right
        elif op == "/":
            return left // right if right != 0 else None
        elif op == "%":
            return left % right if right != 0 else None
        elif op == "<<":
            return left << right
        elif op == ">>":
            return left >> right
        elif op == "&":
            return left & right
        elif op == "|":
            return left | right
        elif op == "^":
            return left ^ right
        else:
            return None
    except (TypeError, ValueError):
        return None


def parse_bin_literal(s: str) -> tuple[int, int]:
    """
    Parse a binary literal string and return (value, width).

    Supports formats:
        - "0b1010"       -> (10, 4)
        - "0b0101_1100"  -> (92, 8)   (underscores ignored)
        - "4'b1010"      -> (10, 4)   (Verilog-style)

    Args:
        s: The binary literal string.

    Returns:
        A tuple of (integer_value, bit_width).

    Raises:
        ValueError: If the string is not a valid binary literal.
    """
    original = s.strip()

    # Verilog-style: N'bXXXX
    if "'b" in original.lower():
        width_str, _, bits_str = original.partition("'b")
        if not width_str.isdigit():
            raise ValueError(f"Invalid binary literal width: {original}")
        width = int(width_str)
        bits = bits_str.replace("_", "")
    elif original.startswith("0b") or original.startswith("0B"):
        bits = original[2:].replace("_", "")
        width = len(bits)
    else:
        raise ValueError(f"Unrecognized binary literal format: {original}")

    # Validate all characters are 0/1
    for ch in bits:
        if ch not in ("0", "1"):
            raise ValueError(f"Invalid character '{ch}' in binary literal: {original}")

    value = int(bits, 2)
    return value, width
