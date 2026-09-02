#!/usr/bin/env python3
"""ADR-0169 评审 §S1 处方 + PR-1.9 grep 门禁 + ADR-0170 PR-3 增量校验。

StdLoopCursor 仅持 spine handle + _state;
不得持有 deriver / projections / persistence / llm_hook / model_visible_recorder 字段。

PR-3 增量校验策略(精准):
- 不钉死文件 SHA256(合法改动如 PR-11 引入 Incarnation 会被误伤)
- 改为钉死 class 字段集合:`StdLoopCursor.__init__` 内的 `self.<_attr>` 赋值
  集合必须在 `_ALLOWED_STD_LOOP_CURSOR_FIELDS` 内
- PR-3 引入的字段漂移检测:任何不在白名单的字段名都被拒绝
- 白名单约定:`_spine` (PR-1) + `_state` (PR-1) + 派生字段 (allowed below)

用法:
    uv run python scripts/check_loop_cursor_no_deriver_hold.py
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_FILE = REPO_ROOT / "lca" / "infrastructure" / "observability" / "loop_cursor" / "std.py"

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
    # 评审 §潜在 #11 / ContextVar 隐式依赖
    "_host",
    "_capture",
    "_barrier",
    # Generic bag slots
    "_bag",
    "_state_extra",
)

# 合法字段白名单(ADR-0169 §D8 / D1 + 后续合法扩展)
# 任何字段变更必须先有 ADR 改 ADR-0169 D8 / D11,然后才能加进此白名单。
_ALLOWED_STD_LOOP_CURSOR_FIELDS: frozenset[str] = frozenset(
    {
        # PR-1 引入(spine + state)
        "_spine",
        "_state",
        # PR-11 引入(incarnation explicit identity,L14 envelope)
        "_incarnation",
        # 派生计算缓存(PR-11 起)
        "_snapshot_cache",
    }
)


def _class_field_names(node: ast.ClassDef) -> list[str]:
    """收集 class 内 __init__ / 直接赋值的私有字段。"""
    fields: list[str] = []
    for stmt in node.body:
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

    # L1:禁止字段检查
    violations: list[str] = []
    for cls in classes:
        for fname in _class_field_names(cls):
            if fname in FORBIDDEN_ATTRS:
                violations.append(f"{cls.name}.{fname} (forbidden)")

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

    # L2:白名单检查 — 任何不在白名单的字段都是新引入,需 ADR
    new_fields: list[str] = []
    for cls in classes:
        for fname in _class_field_names(cls):
            if fname not in _ALLOWED_STD_LOOP_CURSOR_FIELDS:
                new_fields.append(f"{cls.name}.{fname}")

    if new_fields:
        print(
            "FAIL: StdLoopCursor 引入未在白名单的字段(评审 §S1):",
            file=sys.stderr,
        )
        for nf in new_fields:
            print(f"  - {nf}", file=sys.stderr)
        print(
            f"\n合法白名单: {sorted(_ALLOWED_STD_LOOP_CURSOR_FIELDS)}\n"
            "新增字段必须先有 ADR 改 ADR-0169 D8 / D11,然后才能加进白名单。",
            file=sys.stderr,
        )
        return 1

    current_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(
        f"PASS: {TARGET_FILE.relative_to(REPO_ROOT)} "
        f"无 forbidden fields & 字段集合在白名单内"
    )
    print(f"  file_sha256: {current_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
