"""
compiler/extension_loader.py
扫描 source/ 目录下的 .ext 文件，转换为 ExtensionDef 对象供流水线使用。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ExtensionDef:
    """从 .ext 文件解析出的单个语言扩展定义。"""
    name: str = ""
    ext_type: str = ""
    keyword: str = ""
    operator: str = ""
    precedence: int = 0
    c_template: str = ""
    syntax: str = ""
    description: str = ""


def load_extensions(source_dir: str) -> List[ExtensionDef]:
    """扫描 source_dir/*.ext 并返回 ExtensionDef 对象列表。"""
    extensions: List[ExtensionDef] = []
    src = Path(source_dir)
    if not src.is_dir():
        return extensions
    for ext_file in sorted(src.glob("*.ext")):
        # 跳过文档文件
        if ext_file.name.upper().startswith("README"):
            continue
        exts = _parse_ext_file(ext_file)
        if exts:
            extensions.extend(exts)
    return extensions


def get_keywords_from_extensions(extensions: List[ExtensionDef]) -> Dict[str, str]:
    """从扩展中提取 keyword→token_name 映射。

    返回类似 {"flush": "FLUSH"} 的字典，可合并到词法分析器的
    _KEYWORDS 表中。
    """
    result: Dict[str, str] = {}
    for ext in extensions:
        if ext.keyword:
            token_name = ext.keyword.upper()
            result[ext.keyword.lower()] = token_name
    return result


def get_hw_primitives_from_extensions(extensions: List[ExtensionDef]) -> Dict[str, str]:
    """提取硬件原语 keyword→C_template 映射。"""
    result: Dict[str, str] = {}
    for ext in extensions:
        if ext.ext_type == "hardware_primitive" and ext.keyword:
            result[ext.keyword] = ext.c_template
    return result


def _parse_ext_file(filepath: Path) -> Optional[List[ExtensionDef]]:
    """解析单个 .ext 文件，返回所有扩展定义（以 --- 分隔多个定义）。"""
    try:
        raw_text = filepath.read_text(encoding="utf-8")
    except Exception:
        return None

    # 按 "---" 分割多个定义块
    blocks = [b.strip() for b in raw_text.split("\n---\n") if b.strip()]
    # 也支持 "═══" 作为分隔符
    if len(blocks) <= 1:
        blocks = [b.strip() for b in raw_text.split("\n═══\n") if b.strip()]

    extensions: List[ExtensionDef] = []
    for block in blocks:
        ext = _parse_block(block, filepath.stem)
        if ext:
            extensions.append(ext)
    return extensions if extensions else None


def _parse_block(block_text: str, file_stem: str) -> Optional[ExtensionDef]:
    """解析一个定义块（不含分隔符）为 ExtensionDef。"""
    ext = ExtensionDef()
    ext.name = file_stem

    for line in block_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "名称":
            ext.name = value
        elif key == "类型":
            ext.ext_type = value
        elif key == "关键字":
            ext.keyword = value
        elif key == "操作符":
            ext.operator = value
        elif key == "优先级":
            try:
                ext.precedence = int(value)
            except ValueError:
                pass
        elif key == "C模板":
            ext.c_template = value
        elif key == "语法":
            ext.syntax = value
        elif key == "描述":
            ext.description = value
    return ext
