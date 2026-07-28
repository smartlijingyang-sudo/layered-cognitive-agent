#!/usr/bin/env python3
"""CI 15.4：校验 CognitiveRuntime._loop 调用顺序符合 ADR-0002。

期望序列（相对顺序，按源码行号）：
  perceive_and_retrieve | perceive
  → think
  → act
  → reflect
  → update_multi_level | update
  → outcome_policy.resolve  (judge)
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOOP_FILE = ROOT / "lca" / "layer2_runtime" / "runtime_loop.py"

EXPECTED_STEPS: list[tuple[str, frozenset[str]]] = [
    ("perceive", frozenset({"perceive_and_retrieve", "perceive"})),
    ("think", frozenset({"think"})),
    ("act", frozenset({"act"})),
    ("reflect", frozenset({"reflect"})),
    ("update", frozenset({"update_multi_level", "update"})),
    ("judge", frozenset({"resolve"})),
]


def _attr_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _collect_calls_in_order(func: ast.AsyncFunctionDef | ast.FunctionDef) -> list[tuple[int, str]]:
    """按源码行号收集函数体内的调用名。"""
    found: list[tuple[int, str]] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        name = _attr_name(node.func)
        if name is None:
            continue
        found.append((node.lineno, name))
    found.sort(key=lambda x: x[0])
    return found


def main() -> int:
    source = LOOP_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(LOOP_FILE))
    loop_func: ast.AsyncFunctionDef | ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_loop":
            loop_func = node
            break
    if loop_func is None:
        print("FAIL: 未找到 CognitiveRuntime._loop")
        return 1

    ordered = _collect_calls_in_order(loop_func)
    calls = [name for _, name in ordered]
    cursor = 0
    matched: list[str] = []
    for step_name, aliases in EXPECTED_STEPS:
        found_at = None
        for i in range(cursor, len(calls)):
            if calls[i] in aliases:
                found_at = i
                break
        if found_at is None:
            print(f"FAIL: _loop 中未找到步骤 {step_name}（期望调用 {sorted(aliases)}）")
            print(f"  实际调用序列: {calls}")
            return 1
        matched.append(step_name)
        cursor = found_at + 1

    print(f"OK: cognitive loop order = {' → '.join(matched)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
