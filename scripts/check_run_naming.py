#!/usr/bin/env python3
"""check_run_naming —— ADR-0065 §七 / PR-10。

``traces/runs/`` 下目录名必须是不可猜测的 ``<run_id>``(ULID-like:
``run_<hex>`` 形式);**禁止**本地时间戳前缀 + 部分 hash 后缀模式
(如 ``20260821-111932_<hash>``,0064 旧布局)。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO / "traces" / "runs"

# ULID-like: 4-26 字符 [a-z0-9_]-,前缀 "run_"
_RUN_ID_RE = re.compile(r"^run_[a-z0-9]{4,26}$")

# 旧布局: 8 数字 + "-" + 6 数字 + "_" + 长 hex
_OLD_LAYOUT_RE = re.compile(r"^\d{8}-\d{6}_[a-f0-9]{16,}$")


def main() -> int:
    if not RUNS_DIR.exists():
        print(f"OK: {RUNS_DIR} not present")
        return 0

    violations: list[tuple[Path, str]] = []
    for path in RUNS_DIR.iterdir():
        if not path.is_dir():
            continue
        name = path.name
        if _RUN_ID_RE.match(name):
            continue
        if _OLD_LAYOUT_RE.match(name):
            violations.append((path, "old-layout: <timestamp>_<hash>"))
            continue
        violations.append((path, f"invalid run_id format: {name!r}"))

    if violations:
        for path, reason in violations:
            print(f"VIOLATION {path.name}: {reason}")
        print(
            f"\nADR-0065 §七: {len(violations)} violations. "
            f"Run dir names must be 'run_<hex>' (ULID)."
        )
        return 1

    print(f"OK: {RUNS_DIR.relative_to(REPO)}/* all use run_<hex> naming")
    return 0


if __name__ == "__main__":
    sys.exit(main())
