#!/usr/bin/env python3
"""check_no_double_encoding —— ADR-0065 §四 + PR-3。

扫描 ``lca/cognition/body/`` 与 ``lca/infrastructure/observability/``
不允许 ``result_preview`` / ``*_preview`` 是 JSON 字符串(triple-encoded 旧坑)。
typed 字段不应是字符串化的结构。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIRS = (
    REPO / "lca" / "cognition" / "body",
    REPO / "lca" / "infrastructure" / "observability",
)
VIOLATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.preview\s*=\s*json\.dumps\("),
    re.compile(r"json\.dumps\([^)]*\.preview"),
    re.compile(r"JSON\.parse\([^)]*preview"),
)


def main() -> int:
    violations: list[tuple[Path, str]] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for pattern in VIOLATION_PATTERNS:
                for match in pattern.finditer(text):
                    snippet = match.group(0).splitlines()[0]
                    violations.append((path, snippet))

    if violations:
        for path, snippet in violations:
            print(f"VIOLATION {path}: {snippet!r}")
        print(
            f"\nFound {len(violations)} double-encoding patterns. "
            f"Use typed field + EvidenceRef instead."
        )
        return 1

    print("OK: no double-encoding patterns in journal payload paths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
