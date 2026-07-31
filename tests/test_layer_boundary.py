"""分层通信铁律 —— AST 静态扫描，禁止 L3 裸 getattr 穿透 Runtime。

L3 (agent) 通过 Runtime Protocol 的显式方法与 L1/L2 交互。
需要访问 body / brain / memory / hooks 时，须先 ``isinstance(runtime, HasBrainBodyMemory)``
或 ``HasHooks``，禁止 ``getattr(x.runtime, ...)`` 穿透。
"""

from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_LAYER3_DIR = Path(__file__).resolve().parent.parent / "lca" / "layer3_agent"

_FORBIDDEN_GETATTR_ATTRS = frozenset({"body", "brain", "memory", "hooks"})


class _LayerBoundaryVisitor(ast.NodeVisitor):
    """扫描单个 AST 树，收集裸 getattr(runtime, ...) 越层访问。"""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            first_arg = node.args[0]
            second_arg = node.args[1]
            if (
                isinstance(first_arg, ast.Attribute)
                and first_arg.attr == "runtime"
                and isinstance(second_arg, ast.Constant)
                and isinstance(second_arg.value, str)
                and second_arg.value in _FORBIDDEN_GETATTR_ATTRS
            ):
                owner = "unknown"
                if isinstance(first_arg.value, ast.Name):
                    owner = first_arg.value.id
                self.violations.append(
                    f"{self.filename}:{node.lineno} — "
                    f"getattr({owner}.runtime, {second_arg.value!r}) 越层访问，"
                    f"请用 HasBrainBodyMemory / HasHooks + isinstance"
                )
        self.generic_visit(node)


class TestLayerBoundary(unittest.TestCase):
    """L3 agent 层不得裸 getattr 穿透 runtime 访问内部组件。"""

    def test_no_getattr_runtime_penetration_in_layer3(self) -> None:
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
            msg = "L3 层存在裸 getattr 穿透 runtime 的行为:\n"
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
