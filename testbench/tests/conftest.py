"""
conftest.py — pytest 配置

放在 tests/ 目录下，自动被 pytest 发现。
"""

import sys
import os

# 把 python/ 目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))
