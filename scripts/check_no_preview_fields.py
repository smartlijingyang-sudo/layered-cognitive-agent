#!/usr/bin/env python3
"""check_no_preview_fields —— ADR-0065 §四 + PR-3。

扫描 ``lca/contracts/models/observability/`` 与 ``lca/cognition/body/``
确保 ``*_preview`` 字段全部从 journal event dataclass 字段集删除。
PR-3 引入期允许多少残留(0),后续 PR 必须保持零。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIRS = (
    REPO / "lca" / "contracts" / "models" / "observability",
    REPO / "lca" / "cognition" / "body",
)
ALLOW_FILE_OVERRIDES: tuple[str, ...] = (
    # 0065 显式否决项;暂留迁移期兼容
)


def main() -> int:
    pattern = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*_preview)\s*:")
    violations: list[tuple[Path, str]] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            if path.name in ALLOW_FILE_OVERRIDES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for match in pattern.finditer(text):
                violations.append((path, match.group(1)))

    if violations:
        for path, field in violations:
            print(f"VIOLATION {path}: field {field!r} violates ADR-0065 §四")
        print(
            f"\nFound {len(violations)} '*_preview' field declarations. "
            f"Use EvidenceRef instead (ADR-0065 §四)."
        )
        return 1

    print("OK: no '*_preview' fields in journal event contracts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
