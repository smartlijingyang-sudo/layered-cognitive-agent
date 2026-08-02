#!/usr/bin/env python3
"""Pre-commit hook: ADR 与代码同步校验（ADR-0017）。

解析 ADR-0017 中列出的枚举类型清单，AST 扫描 lca/contracts/enums.py
确认每个枚举类型确实存在。不存在则报错，防止 ADR 与代码脱节。
"""

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ADR_0017 = _ROOT / "docs" / "adr" / "0017-no-bare-strings-no-any.md"
_ENUMS = _ROOT / "lca" / "contracts" / "enums.py"

# 正则匹配 ADR-0017 枚举表格行：| `EnumName` | values | examples |
# 要求3列（枚举名 | 值域 | 替代的裸字符串），排除2列的工具表
_ADR_ENUM_PATTERN = re.compile(r"^\| `(\w+)` \| .+ \| .+ \|")


def _parse_adr_enums(filepath):
    """从 ADR-0017 表格中提取枚举类型名。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()

    enums = set()
    for line in content.splitlines():
        m = _ADR_ENUM_PATTERN.match(line)
        if m:
            enums.add(m.group(1))
    return enums


def _parse_code_enums(filepath):
    """从 enums.py 中提取所有 class XXX(str, Enum) 定义。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()

    pattern = re.compile(r"^class (\w+)\(str,\s*Enum\):", re.MULTILINE)
    return set(pattern.findall(content))


def main():
    if not _ADR_0017.is_file():
        print("warning: ADR-0017 not found, skipping sync check")
        return 0
    if not _ENUMS.is_file():
        print("warning: lca/contracts/enums.py not found, skipping sync check")
        return 0

    adr_enums = _parse_adr_enums(_ADR_0017)
    code_enums = _parse_code_enums(_ENUMS)

    # NodeType, EdgeType are in graph.py; TaskStatus is in lifecycle.py
    known_non_enums_py = {"NodeType", "EdgeType", "TaskStatus"}
    adr_only = adr_enums - code_enums - known_non_enums_py
    code_only = code_enums - adr_enums

    has_errors = False

    if adr_only:
        print("FAILED: ADR-0017 mentions enum types not in enums.py:")
        for name in sorted(adr_only):
            print("  - " + name)
        has_errors = True

    if code_only:
        print("WARNING: enums.py has types not in ADR-0017:")
        for name in sorted(code_only):
            print("  - " + name)
        print("  Please add these to the ADR-0017 enum table.")

    if not has_errors and not code_only:
        print("PASS: ADR-0017 and enums.py are in sync")

    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
