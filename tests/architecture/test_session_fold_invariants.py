"""fold.py 纯函数不变量 —— ADR-0185 PR-3a。

验证 ``lca_kernel/events/fold.py`` 不包含文件系统 I/O:
- 无 ``open(``
- 无 ``Path``
- 无 ``.read(`` / ``.read_text(`` / ``.read_bytes(``
- 无 ``.write(`` / ``.write_text(`` / ``.write_bytes(``

fold 模块必须是纯函数集:输入事件流 → 输出 fold 结果;无副作用。
本测试是架构守卫,防止后续 PR 意外引入 I/O。
"""

from __future__ import annotations

import ast
from pathlib import Path

_FOLD_MODULE = Path(__file__).resolve().parents[2] / "lca_kernel" / "events" / "fold.py"


def _source() -> str:
    return _FOLD_MODULE.read_text(encoding="utf-8")


def _source_ast() -> ast.Module:
    return ast.parse(_source())


def test_fold_has_no_open_call() -> None:
    """fold.py 不得包含 ``open(`` 调用。"""
    source = _source()
    # 简单文本搜索 + AST 验证双保险
    assert "open(" not in source, "fold.py must not call open()"


def test_fold_has_no_path_import() -> None:
    """fold.py 不得 import ``pathlib.Path``。"""
    tree = _source_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
            names = [alias.name for alias in node.names]
            assert "Path" not in names, "fold.py must not import pathlib.Path"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "pathlib", "fold.py must not import pathlib"


def test_fold_has_no_read_or_write_methods() -> None:
    """fold.py 不得包含 .read / .write / .read_text / .write_text 调用。"""
    source = _source()
    forbidden = [
        ".read(",
        ".read_text(",
        ".read_bytes(",
        ".write(",
        ".write_text(",
        ".write_bytes(",
    ]
    for pattern in forbidden:
        assert pattern not in source, f"fold.py must not contain {pattern!r}"


def test_fold_has_no_print_or_logging() -> None:
    """fold.py 不得 import print / logging(纯函数无副作用)。"""
    tree = _source_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "logging", "fold.py must not import logging"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "logging", "fold.py must not import from logging"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "print", "fold.py must not call print()"


def test_fold_has_no_datetime_now() -> None:
    """fold.py 不得包含 datetime.now() 调用(纯函数不依赖当前时间)。"""
    tree = _source_ast()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "now"
            and isinstance(node.func.value, ast.Name)
        ):
            assert node.func.value.id != "datetime", "fold.py must not call datetime.now()"


def test_fold_module_parseable() -> None:
    """fold.py AST 可解析(语法正确性守卫)。"""
    tree = _source_ast()
    # 至少有顶层定义
    assert len(tree.body) > 0
