#!/usr/bin/env python3
"""check_evidence_atomic —— ADR-0065 L5 摘要不匹配必须显式 raise。

扫描 ``lca/layer0_infra/observability/evidence/`` 与
``lca/plugins/{seam,providers}/evidence_*.py``,确保 EvidenceStore.prepare
实现路径内不出现静默 try/except 把 ``EvidenceIntegrityError`` 吞掉。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SCAN_DIRS = (
    REPO / "lca" / "layer0_infra" / "observability" / "evidence",
    REPO / "lca" / "plugins",
)

VIOLATION_PATTERNS = (
    re.compile(
        r"except[^:]*:\s*\n\s*pass\s*$",
        re.MULTILINE,
    ),
    re.compile(
        r"except[^:]*:\s*\n\s*return\s*$",
        re.MULTILINE,
    ),
)


def main() -> int:
    violations: list[tuple[Path, int, str]] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            # 只扫描 evidence 相关文件
            if "evidence" not in path.name and "evidence" not in str(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for pattern in VIOLATION_PATTERNS:
                for match in pattern.finditer(text):
                    line = text[: match.start()].count("\n") + 1
                    violations.append((path, line, match.group(0).splitlines()[0]))

    if violations:
        for path, line, snippet in violations:
            print(f"VIOLATION {path}:{line}: {snippet.strip()!r}")
        print(
            f"\nADR-0065 L5: EvidenceIntegrityError must be raised explicitly. "
            f"Found {len(violations)} suspicious silent-except blocks."
        )
        return 1

    print("OK: no silent-except in evidence code paths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
