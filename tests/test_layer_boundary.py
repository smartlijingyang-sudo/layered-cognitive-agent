"""分层通信铁律 —— AST 静态扫描，禁止 L3 越层访问 L1 组件内部状态。

L3 (agent) 只能通过 Runtime Protocol 的显式方法（run）与 L1/L2 交互。
直接访问 self.runtime.body / self.runtime.brain / getattr(self.runtime, ...) 全部违规。
"""

from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_LAYER3_DIR = Path(__file__).resolve().parent.parent / "lca" / "layer3_agent"

_FORBIDDEN_ATTRS = frozenset({"body", "brain"})


class _LayerBoundaryVisitor(ast.NodeVisitor):
    """扫描单个 AST 树，收集所有越层访问。"""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # self.runtime.body / self.runtime.brain
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "runtime"
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "self"
            and node.attr in _FORBIDDEN_ATTRS
        ):
            self.violations.append(
                f"{self.filename}:{node.lineno} — "
                f"self.runtime.{node.attr} 越层访问，请通过协议接口交互"
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # getattr(self.runtime, "body") / getattr(self.runtime, "brain")
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            first_arg = node.args[0]
            second_arg = node.args[1]
            if (
                isinstance(first_arg, ast.Attribute)
                and first_arg.attr == "runtime"
                and isinstance(first_arg.value, ast.Name)
                and first_arg.value.id == "self"
                and isinstance(second_arg, ast.Constant)
                and isinstance(second_arg.value, str)
                and second_arg.value in _FORBIDDEN_ATTRS
            ):
                self.violations.append(
                    f"{self.filename}:{node.lineno} — "
                    f"getattr(self.runtime, {second_arg.value!r}) 越层访问，"
                    f"请通过协议接口交互"
                )
        self.generic_visit(node)


class TestLayerBoundary(unittest.TestCase):
    """L3 agent 层不得直接访问 runtime.body / runtime.brain。"""

    def test_no_cross_layer_access_in_layer3(self) -> None:
        py_files = sorted(_LAYER3_DIR.rglob("*.py"))
        self.assertTrue(py_files, f"layer3_agent 目录下没有 .py 文件: {_LAYER3_DIR}")

        all_violations: list[str] = []
        for py_file in py_files:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
            visitor = _LayerBoundaryVisitor(
                str(py_file.relative_to(Path(__file__).resolve().parent.parent))
            )
            visitor.visit(tree)
            all_violations.extend(visitor.violations)

        if all_violations:
            msg = "L3 层存在越层访问 L1 组件的行为（请通过协议接口交互）:\n"
            msg += "\n".join(f"  - {v}" for v in all_violations)
            self.fail(msg)

    def test_no_type_ignore_attr_defined_on_runtime(self) -> None:
        """检测 # type: ignore[attr-defined] 紧跟 self.runtime. 的模式。"""
        py_files = sorted(_LAYER3_DIR.rglob("*.py"))
        violations: list[str] = []

        for py_file in py_files:
            lines = py_file.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, start=1):
                if "type: ignore[attr-defined]" in line and "self.runtime." in line:
                    rel = py_file.relative_to(Path(__file__).resolve().parent.parent)
                    violations.append(f"{rel}:{i} — {line.strip()}")

        if violations:
            msg = "L3 层存在 type: ignore[attr-defined] + self.runtime. 模式:\n"
            msg += "\n".join(f"  - {v}" for v in violations)
            self.fail(msg)


if __name__ == "__main__":
    unittest.main()
