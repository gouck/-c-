"""
compiler/main.py
Command-line entry point for the 8m micro-compiler.

Usage:
    python -m compiler.main <spec_file> <reg_file> [-o OUTPUT_DIR] [--target c|rtl] [-v]
"""

from __future__ import annotations

import argparse
import os
import sys
import glob
from typing import List, Optional


def _resolve_reg_files(reg_args: List[str]) -> List[str]:
    """Resolve reg_file arguments to a flat list of reg file paths.
    
    Each argument can be:
      - a single .txt file → added directly
      - a directory → all *.txt files inside are added (sorted)
    """
    files: List[str] = []
    for arg in reg_args:
        if os.path.isdir(arg):
            found = sorted(glob.glob(os.path.join(arg, "*.txt")))
            if not found:
                print(f"Warning: no .txt files found in {arg}")
            files.extend(found)
        else:
            files.append(arg)
    return files


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
        "reg_files",
        nargs="+",
        help="tinyReg.txt file(s) and/or directory(ies) of .txt files",
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

    reg_files = _resolve_reg_files(args.reg_files)
    if not reg_files:
        print("Error: no register files found.")
        return 1

    print("8m Compiler v0.1.0")
    print(f"  Spec file   : {args.spec_file}")
    print(f"  Register file(s): {len(reg_files)} file(s)")
    if len(reg_files) <= 5:
        for rf in reg_files:
            print(f"    - {rf}")
    print(f"  Output dir  : {args.output_dir}")
    print(f"  Target      : {args.target}")
    print(f"  Verbose     : {args.verbose}")

    from compiler.pipeline import CompilerPipeline
    pipeline = CompilerPipeline(
        spec_path=args.spec_file,
        reg_paths=reg_files,
        output_dir=args.output_dir,
        target=args.target,
        verbose=args.verbose,
    )
    pipeline.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
