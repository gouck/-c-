"""
compiler/main.py
Command-line entry point for the 8m micro-compiler.

Usage:
    # 单文件模式
    python -m compiler.main <spec_file> <reg_files...> [-o OUTPUT_DIR] [--target c|rtl] [-v]

    # 工程模式（多文件伪代码工程）
    python -m compiler.main --project <spec_dir> <reg_files...> [-o OUTPUT_DIR] [--target c|rtl] [-v]
"""

from __future__ import annotations

import argparse
import os
import sys
import glob
from typing import List, Optional, Tuple


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


def _resolve_spec_files(spec_dir: str) -> Tuple[List[str], List[str]]:
    """Scan a project directory for .h and .c pseudo-code files.
    
    Returns:
        (h_files, c_files) — .h files first (globals, types, interfaces),
        then .c files.  Sorted for deterministic ordering.
    """
    all_h = sorted(glob.glob(os.path.join(spec_dir, "*.h")))
    all_c = sorted(glob.glob(os.path.join(spec_dir, "*.c")))
    
    # 确保 globals.h 和 types.h 排最前面
    priority = ["globals.h", "types.h"]
    h_files: List[str] = []
    for p in priority:
        path = os.path.join(spec_dir, p)
        if path in all_h:
            h_files.append(path)
            all_h.remove(path)
    h_files.extend(all_h)  # 其余 .h 按字母序
    
    return h_files, all_c


def _is_project_mode(spec_path: str) -> bool:
    """Detect if spec_path is a directory (project mode) or file (single mode)."""
    return os.path.isdir(spec_path)


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

    # 模式选择
    parser.add_argument(
        "--project", "-p",
        action="store_true",
        default=False,
        help="Project mode: treat spec_file as a directory containing .h/.c files",
    )
    parser.add_argument(
        "--merge-only",
        action="store_true",
        default=False,
        help="(Project mode) merge all files into single output.c (方案A兼容)",
    )

    # Positional arguments
    parser.add_argument(
        "spec_file",
        help="Pseudo-C source file (single mode) or project directory (--project mode)",
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

    # 判断模式
    project_mode = args.project or _is_project_mode(args.spec_file)
    
    print("8m Compiler v0.2.0")
    if project_mode:
        h_files, c_files = _resolve_spec_files(args.spec_file)
        if not c_files:
            print("Error: no .c files found in project directory.")
            return 1
        print(f"  Mode         : project ({len(h_files)} .h + {len(c_files)} .c)")
        if args.verbose:
            for hf in h_files:
                print(f"    H: {hf}")
            for cf in c_files:
                print(f"    C: {cf}")
    else:
        h_files, c_files = [], [args.spec_file]
        print(f"  Mode         : single file")
        print(f"  Spec file    : {args.spec_file}")

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
        h_files=h_files,
        c_files=c_files,
        project_mode=project_mode,
        merge_only=args.merge_only,
    )
    pipeline.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
