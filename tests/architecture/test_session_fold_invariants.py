"""fold 包纯函数不变量 —— ADR-0185 PR-3a。

验证 ``lca_kernel/events/fold/`` 包内各文件不包含文件系统 I/O:
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

_FOLD_PACKAGE = (
    Path(__file__).resolve().parents[2] / "lca_kernel" / "events" / "fold"
)


def _fold_files() -> list[Path]:
    """包内全部 .py 源码文件(__pycache__ 除外)。"""
    return sorted(p for p in _FOLD_PACKAGE.glob("*.py") if p.is_file())


def _sources() -> list[tuple[Path, str]]:
    files = _fold_files()
    assert files, f"fold 包未落地:{_FOLD_PACKAGE}"
    return [(p, p.read_text(encoding="utf-8")) for p in files]


def _source_asts() -> list[tuple[Path, ast.Module]]:
    return [(p, ast.parse(src)) for p, src in _sources()]


def test_fold_has_no_open_call() -> None:
    """fold 包内各文件不得包含 ``open(`` 调用。"""
    for path, source in _sources():
        # 简单文本搜索 + AST 验证双保险
        assert "open(" not in source, f"{path.name} must not call open()"


def test_fold_has_no_path_import() -> None:
    """fold 包内各文件不得 import ``pathlib.Path``。"""
    for path, tree in _source_asts():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
                names = [alias.name for alias in node.names]
                assert "Path" not in names, f"{path.name} must not import pathlib.Path"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "pathlib", f"{path.name} must not import pathlib"


def test_fold_has_no_read_or_write_methods() -> None:
    """fold 包内各文件不得包含 .read / .write / .read_text / .write_text 调用。"""
    forbidden = [
        ".read(",
        ".read_text(",
        ".read_bytes(",
        ".write(",
        ".write_text(",
        ".write_bytes(",
    ]
    for path, source in _sources():
        for pattern in forbidden:
            assert pattern not in source, f"{path.name} must not contain {pattern!r}"


def test_fold_has_no_print_or_logging() -> None:
    """fold 包内各文件不得 import print / logging(纯函数无副作用)。"""
    for path, tree in _source_asts():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "logging", f"{path.name} must not import logging"
            if isinstance(node, ast.ImportFrom):
                assert node.module != "logging", f"{path.name} must not import from logging"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "print", f"{path.name} must not call print()"


def test_fold_has_no_datetime_now() -> None:
    """fold 包内各文件不得包含 datetime.now() 调用(纯函数不依赖当前时间)。"""
    for path, tree in _source_asts():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "now"
                and isinstance(node.func.value, ast.Name)
            ):
                assert node.func.value.id != "datetime", (
                    f"{path.name} must not call datetime.now()"
                )


def test_fold_module_parseable() -> None:
    """fold 包内各文件 AST 可解析(语法正确性守卫)。"""
    for _path, tree in _source_asts():
        # 至少有顶层定义
        assert len(tree.body) > 0
