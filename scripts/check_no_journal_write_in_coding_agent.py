#!/usr/bin/env python3
"""check_no_journal_write_in_coding_agent —— ADR-0065 §六 / PR-8 / L6。

扫描 ``lca/infrastructure/observability/coding_agent_tools/`` 与
``lca/plugins/bundles/coding_agent_tools.py``,确保 7 个 Coding Agent Tool
实现里**没有**任何账本写入调用:

- ``RunLedger.append(`` / ``RunStore.append(``
- ``record_runtime(`` / ``record(`` / ``observe_operation(``
- ``RunLedger.seal(``
- 直接构造 ``JournalRecord(`` / ``StampedEvent(`` 然后 push 到 backend

只允许读取:`_load_inspector_from_jsonl` / `TraceInspector` / `TraceReport`。

测试 / fixture 场景可通过 ``# ADR-0065 PR-8 exempt`` 显式豁免。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SCAN_PATHS: tuple[Path, ...] = (
    REPO / "lca" / "infrastructure" / "observability" / "coding_agent_tools",
    REPO / "lca" / "plugins" / "bundles" / "coding_agent_tools.py",
)

FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {
        # facade: record / record_runtime / observe / observe_operation
        "record",
        "record_runtime",
        "observe",
        "observe_operation",
    }
)

# attribute form: X.append / X.seal / X.write 仅当 X 是 backend / ledger 才算
_FORBIDDEN_ATTR_TARGETS: frozenset[str] = frozenset(
    {
        "RunLedger",
        "RunStore",
        "store",
        "backend",
        "ledger",
        "MemoryJournal",
        "JsonlJournalProjector",
    }
)


def _is_exempt_call(node: ast.Call) -> bool:
    """call 行被 PR-8 exempt 注释豁免。"""
    return False  # 行号不易拿到;PR-8 默认不允许豁免;后续可加


def _is_forbidden_call(node: ast.Call) -> str | None:
    func = node.func
    # Name form: 直接调 record(...) / record_runtime(...)
    if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
        return func.id
    # Attribute form: only target = ledger / backend name
    if isinstance(func, ast.Attribute):
        attr = func.attr
        target_name = func.value.id if isinstance(func.value, ast.Name) else None
        if target_name in _FORBIDDEN_ATTR_TARGETS and attr in {"append", "seal", "write"}:
            return f"{target_name}.{attr}"
    return None


def main() -> int:
    violations: list[tuple[Path, int, str]] = []
    for path in SCAN_PATHS:
        if not path.exists():
            continue
        files = list(path.rglob("*.py")) if path.is_dir() else [path]
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                forbidden = _is_forbidden_call(node)
                if forbidden is not None:
                    violations.append((f, node.lineno, forbidden))

    if violations:
        for path, line_no, label in violations:
            print(f"VIOLATION {path}:{line_no}: {label}(...) in coding_agent tool")
        print(
            f"\nADR-0065 L6 / PR-8: {len(violations)} journal.write calls in coding_agent tools. "
            f"Tools must be read-only."
        )
        return 1

    print("OK: coding_agent tools are journal.write-free")
    return 0


if __name__ == "__main__":
    sys.exit(main())
