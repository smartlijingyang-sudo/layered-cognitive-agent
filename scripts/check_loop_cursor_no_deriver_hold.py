#!/usr/bin/env python3
"""ADR-0169 评审 §S1 处方 + PR-1.9 grep 门禁。

StdLoopCursor 仅持 spine handle + _state;
不得持有 deriver / projections / persistence / llm_hook / model_visible_recorder 字段。

用法:
    uv run python scripts/check_loop_cursor_no_deriver_hold.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_FILE = (
    REPO_ROOT
    / "lca"
    / "infrastructure"
    / "observability"
    / "loop_cursor"
    / "std.py"
)

FORBIDDEN_ATTRS: tuple[str, ...] = (
    # 投影 / 持久化 / LLM hook / model_visible 字段(ADR-0169 D8 拆分)
    "_derivers",
    "_projections",
    "_persistence",
    "_llm_hook",
    "_model_visible_recorder",
    "_registry",
    # 评审额外关注:不当存储
    "_subjects",
    "_subscribers",
)


def _class_field_names(node: ast.ClassDef) -> list[str]:
    """收集 class 内 __init__ / 直接赋值的私有字段。"""
    fields: list[str] = []
    for stmt in node.body:
        # __init__ 内的 self.X = ...
        if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
            for inner in ast.walk(stmt):
                if isinstance(inner, ast.Assign):
                    for target in inner.targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                            and target.attr.startswith("_")
                        ):
                            fields.append(target.attr)
    return fields


def main() -> int:
    if not TARGET_FILE.exists():
        print(f"FAIL: {TARGET_FILE} 不存在", file=sys.stderr)
        return 1

    tree = ast.parse(TARGET_FILE.read_text(encoding="utf-8"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if not classes:
        print(f"FAIL: {TARGET_FILE} 中无 class 定义", file=sys.stderr)
        return 1

    violations: list[str] = []
    for cls in classes:
        for fname in _class_field_names(cls):
            if fname in FORBIDDEN_ATTRS:
                violations.append(f"{cls.name}.{fname} (forbidden)")

    # 也直接 grep — 防 AST 解析漏网(如 dataclass 字段、TYPE_CHECKING 等)
    text = TARGET_FILE.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_ATTRS:
        if forbidden in text:
            violations.append(f"file: {forbidden} (forbidden literal)")

    if violations:
        print(
            "FAIL: StdLoopCursor 持有 ADR-0169 D8 禁止的字段(评审 §S1 处方):",
            file=sys.stderr,
        )
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\n修正方案:把这些字段迁移到 ProjectionHost / PersistenceCoordinator "
            "/ ModelVisibleCapture / CloseBarrier 五缝组件(ADR-0169 §D8)。",
            file=sys.stderr,
        )
        return 1

    print(f"PASS: {TARGET_FILE.relative_to(REPO_ROOT)} 无 forbidden fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())