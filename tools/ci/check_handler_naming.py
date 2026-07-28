#!/usr/bin/env python3
"""CI 15.3：禁止新增 class .*Handler 命名（ADR-0016）。

允许：
- 过渡期 alias 赋值（Handler = Operation，不是 class 定义）
- 本文件维护的 GRANDFATHERED 清单（应随删除而清空）
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = ROOT / "lca"

# 过渡期允许残留的 class 名；目标是清空
GRANDFATHERED: frozenset[str] = frozenset()


def main() -> int:
    violations: list[str] = []
    for path in sorted(SCAN_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Handler"):
                if node.name in GRANDFATHERED:
                    continue
                violations.append(f"{rel}:{node.lineno} class {node.name}")

    if violations:
        print("FAIL: 禁止 class .*Handler 命名（请用 Operation/Policy，ADR-0016）:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("OK: check_handler_naming")
    return 0


if __name__ == "__main__":
    sys.exit(main())
