#!/usr/bin/env python3
"""CI gate: 拦截 envelope 字段名漂移(ADR-0096 §I2 + §6 实施序列 PR-0 gate)。

扫描 ``lca/infrastructure/observability/`` 下所有 ``.py`` 文件,拦截:

- ``.data = ...`` 属性写入
- ``dataclasses.replace(..., data=...)``(含 ``from dataclasses import replace``)
- 源码中的 ``data.data`` 嵌套

后续 envelope 字段改名必须先改 ADR-0096,再改本门禁与实现。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "lca" / "infrastructure" / "observability"

# journal_io.py still writes JournalRecord.data via dataclasses.replace after
# Task 3's EnvelopeV2 overlay (disk jsonl still uses ADR-0065 `data`).
# TODO(adr-0096): remove once write-path payload rename (data → payload) lands.
ALLOWLIST = {
    "lca/infrastructure/observability/journal/journal_io.py",  # MVA-1 Task 3 overlay
}


def _is_dataclasses_replace(func: ast.expr) -> bool:
    """True for dataclasses.replace(...) and a bare replace(...) import alias."""
    text = ast.unparse(func)
    if "dataclasses" in text and "replace" in text:
        return True
    return isinstance(func, ast.Name) and func.id == "replace"


def find_data_field_writes(tree: ast.Module) -> list[tuple[str, int]]:
    """检测 .data = ... 或 dataclasses.replace(record, data=...) 模式."""
    findings: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "data":
                    findings.append(("write_to_data_field", node.lineno))
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "data" and _is_dataclasses_replace(node.func):
                    findings.append(("dataclasses_replace_data_kwarg", node.lineno))
    return findings


def find_data_data_nesting(source: str) -> list[tuple[str, int]]:
    """检测源码中的 data.data 嵌套字符串(ADR-0096 §I2 / CV3)."""
    findings: list[tuple[str, int]] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        if "data.data" in line:
            findings.append(("data_data_nesting", lineno))
    return findings


def main() -> int:
    bad: list[str] = []
    if not ROOT.is_dir():
        print(f"FAIL: scan root missing: {ROOT}", file=sys.stderr)
        return 2
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if rel in ALLOWLIST:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as err:
            print(f"FAIL: cannot read {rel}: {err}", file=sys.stderr)
            return 2
        try:
            tree = ast.parse(source, filename=rel)
        except SyntaxError as err:
            print(f"FAIL: cannot parse {rel}: {err}", file=sys.stderr)
            return 2
        for kind, line in find_data_field_writes(tree):
            bad.append(f"{rel}:{line}: {kind}")
        for kind, line in find_data_data_nesting(source):
            bad.append(f"{rel}:{line}: {kind}")
    if bad:
        print("FAIL: envelope field name drift detected (ADR-0096 §I2)")
        for item in bad:
            print(f"  {item}")
        return 1
    print("PASS: no envelope field drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
