"""
compiler/main.py
Command-line entry point for the 8m micro-compiler.

Usage:
    python -m compiler.main <spec_file> <reg_file> [-o OUTPUT_DIR] [--target c|rtl] [-v]
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for the 8m compiler.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 on success, non-zero on error).
    """
    parser = argparse.ArgumentParser(
        prog="8mc",
        description="8m Micro-Compiler – compiles pseudo-C switch descriptions to C or RTL",
    )

    # Positional arguments
    parser.add_argument(
        "spec_file",
        help="Pseudo-C source file describing switch behaviour",
    )
    parser.add_argument(
        "reg_file",
        help="tinyReg.txt register table DSL file",
    )

    # Optional arguments
    parser.add_argument(
        "-o", "--output-dir",
        default="./output",
        help="Output directory for generated files (default: ./output)",
    )
    parser.add_argument(
        "--target",
        choices=["c", "rtl"],
        default="c",
        help="Target language for code generation (default: c)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose output",
    )

    args = parser.parse_args(argv)

    print("8m Compiler v0.1.0")
    print(f"  Spec file   : {args.spec_file}")
    print(f"  Register file: {args.reg_file}")
    print(f"  Output dir  : {args.output_dir}")
    print(f"  Target      : {args.target}")
    print(f"  Verbose     : {args.verbose}")

    from compiler.pipeline import CompilerPipeline
    pipeline = CompilerPipeline(
        spec_path=args.spec_file,
        reg_path=args.reg_file,
        output_dir=args.output_dir,
        target=args.target,
        verbose=args.verbose,
    )
    pipeline.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
