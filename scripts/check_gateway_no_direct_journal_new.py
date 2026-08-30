#!/usr/bin/env python3
"""check_gateway_no_direct_journal_new —— ADR-0065 L9 / PR-5。

``gateway/runs/`` 路径不允许直接 ``new`` Journal / Ledger / LiveTail /
ProcessJournal 等实现;必须经 ``ctx.require("run_ledger_factory")`` 等
capability 装配。

具体禁止:
- ``JsonlJournalProjector(...)`` 实例化
- ``LiveTail(...)`` 实例化
- ``ProcessJournal(...)`` 实例化
- ``RunStore(...)`` / ``RunLedger(...)`` 实例化

class 定义 / type annotation 不算 new;调用方(``x = LiveTail()`` / ``as
LiveTail()`` / 函数实参)才算。测试 / fixture 场景可通过 ``#  ADR-0065 PR-5
exempt`` 显式标记豁免。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIR = REPO / "gateway" / "runs"

FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {
        "JsonlJournalProjector",
        "LiveTail",
        "ProcessJournal",
        "RunStore",
        "RunLedger",
    }
)


def _is_exempt(node: ast.Call, source_lines: list[str], filename: str) -> bool:
    """call 所在行 / 文件是否被 PR-5 exempt 注释豁免。

    _journal_factory.py / process_journal.py / live.py 是 factory 路径,
    文件级豁免(check 认定它们是构造集中点);其它文件需逐行豁免。
    """
    if filename.endswith("_journal_factory.py"):
        return True
    if filename in {"process_journal.py", "live.py"}:
        return True
    line = source_lines[node.lineno - 1]
    return "PR-5 exempt" in line or "PR-5 gateway-exempt" in line


def _is_call_target(node: ast.Call) -> str | None:
    """若 call 的 func 是 ``Name(id=X)`` 且 X 在禁止列表,返回 X;否则 None。"""
    func = node.func
    if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
        return func.id
    return None


def main() -> int:
    if not SCAN_DIR.exists():
        print(f"OK: {SCAN_DIR} not present")
        return 0

    violations: list[tuple[Path, int, str, str]] = []
    for path in SCAN_DIR.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        source_lines = text.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            forbidden = _is_call_target(node)
            if forbidden is None:
                continue
            if _is_exempt(node, source_lines, str(path.name)):
                continue
            snippet = source_lines[node.lineno - 1].strip()
            violations.append((path, node.lineno, forbidden, snippet))

    if violations:
        for path, line_no, label, snippet in violations:
            print(f"VIOLATION {path}:{line_no}: {label}(...): {snippet}")
        print(
            f"\nADR-0065 L9: {len(violations)} direct-new violations in gateway/runs/. "
            f"Use ctx.require('run_ledger_factory') / 'run_locator' / 'evidence_store' instead."
        )
        return 1

    print(f"OK: no direct-new violations in {SCAN_DIR.relative_to(REPO)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
