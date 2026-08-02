"""contracts/ 纯净性门禁 —— AST 静态扫描。

规则（ADR-0015）：contracts/ 下的非 Protocol 类必须是 @dataclass，
且不允许定义除 __post_init__ / dunder 以外的自定义实例方法。
这防止有人顺手把默认实现塞进 contracts/ 目录。

已存在的例外通过 _GRANDFATHERED_* 显式列举，防止新增违规。
"""

from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "lca" / "contracts"

_ALLOWED_DUNDERS = frozenset(
    {
        "__post_init__",
        "__init__",
        "__repr__",
        "__str__",
        "__eq__",
        "__hash__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
    }
)

# 已存在的 dataclass 方法——在 ADR-0015 之前就已存在，
# 显式列举以防止新增类似违规。
_GRANDFATHERED_METHODS: dict[str, frozenset[str]] = {
    "ExecutionGraph": frozenset(
        {
            "add_node",
            "add_edge",
            "outgoing",
            "incoming",
            "validate",
            "_check_acyclic",
            "topological_order",
        }
    ),
    "Result": frozenset({"failed", "from_observation", "from_state"}),
    "Budget": frozenset({"exceeded"}),
    "AgentState": frozenset({"snapshot", "delegated_by", "teammates_text"}),
    "Observation": frozenset({"from_result"}),
    "StopDecision": frozenset({"should_stop"}),
}

# 已存在的非 dataclass / 非 Protocol / 非异常 / 非枚举类——
# 在 ADR-0015 之前就已存在，显式列举以防止新增类似违规。
# ActionRegistry 已迁至 layer1（ADR-0015/0016），不再需要 grandfather
_GRANDFATHERED_CLASSES: frozenset[str] = frozenset()

# 标准异常基类——用于识别异常类（跳过检查）
_STD_EXCEPTION_BASES = frozenset(
    {
        "Exception",
        "BaseException",
        "ValueError",
        "TypeError",
        "RuntimeError",
    }
)

# 枚举基类——用于识别 Enum 类（跳过检查）
_ENUM_BASES = frozenset({"Enum", "IntEnum", "str"})


def _get_base_names(node: ast.ClassDef) -> list[str]:
    """提取类定义中的基类名称。"""
    names: list[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def _collect_exception_classes(tree: ast.Module) -> set[str]:
    """两遍扫描：收集文件中所有异常类名（含传递继承）。"""
    class_bases: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_bases[node.name] = _get_base_names(node)

    exception_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, bases in class_bases.items():
            if name in exception_names:
                continue
            if any(b in _STD_EXCEPTION_BASES or b in exception_names for b in bases):
                exception_names.add(name)
                changed = True
    return exception_names


def _is_protocol_class(node: ast.ClassDef) -> bool:
    """判断一个类是否继承自 Protocol。"""
    return any(
        (isinstance(base, ast.Name) and base.id == "Protocol")
        or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
        for base in node.bases
    )


def _is_enum_class(node: ast.ClassDef) -> bool:
    """判断一个类是否继承自 Enum。"""
    return any(isinstance(base, ast.Name) and base.id in _ENUM_BASES for base in node.bases)


def _has_dataclass_decorator(node: ast.ClassDef) -> bool:
    """检查类是否有 @dataclass 或 @dataclass(...) 装饰器。"""
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "dataclass":
            return True
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "dataclass"
        ):
            return True
    return False


class _ContractsVisitor(ast.NodeVisitor):
    """扫描单个文件的类定义，收集违规。"""

    def __init__(self, filename: str, exception_classes: set[str]) -> None:
        self.filename = filename
        self.violations: list[str] = []
        self._exception_classes = exception_classes

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if _is_protocol_class(node):
            self.generic_visit(node)
            return

        if node.name in self._exception_classes:
            self.generic_visit(node)
            return

        if _is_enum_class(node):
            self.generic_visit(node)
            return

        if not _has_dataclass_decorator(node):
            if node.name in _GRANDFATHERED_CLASSES:
                self.generic_visit(node)
                return
            self.violations.append(
                f"{self.filename}:{node.lineno} — "
                f"class {node.name} 不是 @dataclass 也不是 Protocol，"
                f"contracts/ 不允许包含行为类 (ADR-0015)"
            )
            self.generic_visit(node)
            return

        grandfathered = _GRANDFATHERED_METHODS.get(node.name, frozenset())
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = item.name
            if name.startswith("__") and name.endswith("__"):
                if name not in _ALLOWED_DUNDERS:
                    self.violations.append(
                        f"{self.filename}:{item.lineno} — "
                        f"{node.name}.{name}() 不在允许的 dunder 列表中"
                    )
            elif name not in grandfathered:
                self.violations.append(
                    f"{self.filename}:{item.lineno} — "
                    f"{node.name}.{name}() 是自定义方法，"
                    f"contracts/ 的 @dataclass 不允许包含行为逻辑 (ADR-0015)。"
                    f"如果是已有方法，请添加到 _GRANDFATHERED_METHODS"
                )

        self.generic_visit(node)


class TestContractsPurity(unittest.TestCase):
    """contracts/ 目录下不得包含行为类（ADR-0015）。"""

    def test_no_behavior_classes_in_contracts(self) -> None:
        py_files = sorted(_CONTRACTS_DIR.rglob("*.py"))
        self.assertTrue(py_files, f"contracts 目录下没有 .py 文件: {_CONTRACTS_DIR}")

        all_violations: list[str] = []
        for py_file in py_files:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
            rel_path = str(py_file.relative_to(Path(__file__).resolve().parent.parent))
            exception_classes = _collect_exception_classes(tree)
            visitor = _ContractsVisitor(rel_path, exception_classes)
            visitor.visit(tree)
            all_violations.extend(visitor.violations)

        if all_violations:
            msg = "contracts/ 存在行为类违规（具体实现应放在对应实现层，ADR-0015）:\n"
            msg += "\n".join(f"  - {v}" for v in all_violations)
            self.fail(msg)


if __name__ == "__main__":
    unittest.main()
