#!/usr/bin/env python3
"""check_no_flat_runs —— ADR-0065 §七 / PR-11。

0065 强制 traces/runs/ 顶层只能有 per-run 目录 ``<run_id>/``;
flat 文件 ``<id>.jsonl`` / ``<id>.doctor.json`` /
``<id>.*.jsonl`` 都是旧 v1 残留,新代码不应再产生。

检查范围::

    traces/runs/
    ├── run_<hex>/                     OK —— per-run 目录
    ├── run_xxx.jsonl                  VIOLATION —— flat 账本(应移进 run_xxx/journal.jsonl)
    ├── run_xxx.doctor.json            VIOLATION —— flat 诊断(应并入 run_xxx/manifest.json)
    └── unrelated.txt                  VIOLATION —— 任何非目录文件

run_id 命名合法性由 ``scripts/check_run_naming.py`` 独立把守;本脚本只管
"是否有 flat 残留 / 异常文件"。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO / "traces" / "runs"

# 已知会"误判为遗留"的合法场景:无 — 若有必须 ADR 化(0065 §一 拒绝自由形状)。
_LEGACY_FLAT_SUFFIXES = (
    ".jsonl",  # 账本后缀
    ".doctor.json",  # 老 doctor 报告
)

# run_id 命名规范(与 check_run_naming.py 同源)
_RUN_ID_RE = re.compile(r"^run_[a-z0-9]{4,26}$")


def _classify(name: str) -> str:
    """返回违规类别;'' 表示通过。"""
    if _RUN_ID_RE.match(name):
        return ""  # 合法 per-run 目录名
    if any(name.endswith(suffix) for suffix in _LEGACY_FLAT_SUFFIXES):
        return "flat-file (must live inside per-run dir)"
    return "unexpected entry in traces/runs/"


def main() -> int:
    if not RUNS_DIR.exists():
        print(f"OK: {RUNS_DIR} not present")
        return 0
    violations: list[tuple[Path, str]] = []
    for entry in sorted(RUNS_DIR.iterdir()):
        kind = _classify(entry.name)
        if kind:
            violations.append((entry, kind))
        elif entry.is_file():
            violations.append((entry, "non-directory entry under traces/runs/"))
    if violations:
        for path, reason in violations:
            print(f"VIOLATION {path.name}: {reason}")
        print(
            f"\nADR-0065 §七: {len(violations)} violations. "
            f"Only 'run_<hex>/' per-run dirs are allowed at {RUNS_DIR}/."
        )
        print(
            "Run `uv run python scripts/migrate_traces_flat_to_v2_layout.py --apply` "
            "to migrate legacy flat files."
        )
        return 1
    print(f"OK: {RUNS_DIR.relative_to(REPO)}/* all conform to per-run dir layout")
    return 0


if __name__ == "__main__":
    sys.exit(main())
