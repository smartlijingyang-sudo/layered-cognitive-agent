#!/usr/bin/env python3
"""CI 15.1：含 AgentState 标注的协议方法，首个非 self 参数应命名为 state。

扫描范围：lca/contracts/protocols/**、lca/contracts/mechanisms.py、lca/contracts/action.py
渐进收紧：当前仅对「第一个参数类型为 AgentState」做强制；
若 AgentState 出现在非首参位置，输出 WARN 不失败（历史签名兼容）。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_PATHS = [
    ROOT / "lca" / "contracts" / "protocols",
    ROOT / "lca" / "contracts" / "mechanisms.py",
    ROOT / "lca" / "contracts" / "action.py",
]


def _ann_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # X | None
        return _ann_name(node.left) or _ann_name(node.right)
    if isinstance(node, ast.Subscript):
        return _ann_name(node.value)
    return None


def _check_file(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(ROOT)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # 只检查 Protocol 方法（... body 或 docstring + ...）
        args = list(node.args.args)
        if not args or args[0].arg != "self":
            continue
        non_self = args[1:]
        typed_state_positions = [
            i for i, a in enumerate(non_self) if _ann_name(a.annotation) == "AgentState"
        ]
        if not typed_state_positions:
            continue
        first = non_self[0]
        if _ann_name(first.annotation) == "AgentState" and first.arg != "state":
            errors.append(
                f"{rel}:{node.lineno} {node.name}() — 首个非 self 参数类型为 AgentState "
                f"但命名为 {first.arg!r}，应为 'state'"
            )
        elif typed_state_positions[0] != 0:
            warnings.append(
                f"{rel}:{node.lineno} {node.name}() — AgentState 不在首参 "
                f"(位置 {typed_state_positions[0] + 1})，建议逐步调整为 state 首参"
            )
    return errors, warnings


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    files: list[Path] = []
    for p in SCAN_PATHS:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            files.append(p)

    for f in files:
        if f.name == "__init__.py" and f.parent.name == "protocols":
            # re-export only
            continue
        e, w = _check_file(f)
        errors.extend(e)
        warnings.extend(w)

    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        print("FAIL: AgentState 首参命名违规（ADR-0016 / CI 15.1）:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK: check_state_first_param ({len(files)} files, {len(warnings)} warnings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
