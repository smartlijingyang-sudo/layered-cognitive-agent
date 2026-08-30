#!/usr/bin/env python3
"""Pre-commit hook: 装配期只读不算（契约 2）—— spawn.py 不允许 if/else 字符串比较分支。

检测 application/spawn.py 中是否出现字符串比较分支（如 `if x == "supervisor"`），
这类分支违反"装配期只读不算"原则：spawn 只应取值 -> 传参 -> 组装，
业务判断逻辑应放在策略层或运行时。
"""

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ASSEMBLY = _ROOT / "lca" / "application" / "spawn.py"


def _check_file(filepath):
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    violations = []
    lines = content.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # skip comments
        if stripped.startswith("#"):
            continue
        # skip raise messages
        if re.search(r"raise\s+\w+Error", stripped):
            continue
        # skip isinstance checks
        if re.search(r"\bisinstance\s*\(", stripped):
            continue
        # detect == "string" or != "string" patterns (excluding format strings)
        if re.search(r'[!=]=\s*"[^"]*"', stripped) and not re.search(r'(format|f["\'])', stripped):
            rel = str(filepath.relative_to(_ROOT))
            violations.append(f"  {rel}:{i}: spawn string comparison: {stripped}")
            violations.append("    -> violates contract 2 (spawn is read-only compose)")

    return violations


def main():
    if not _ASSEMBLY.is_file():
        return 0

    violations = _check_file(_ASSEMBLY)

    if violations:
        print("FAILED: spawn.py has string comparison branches")
        print("        (violates contract 2: spawn is read-only compose)")
        print()
        for v in violations:
            print(v)
        return 1

    print("PASS: spawn.py purity check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
