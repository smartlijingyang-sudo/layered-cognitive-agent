#!/usr/bin/env python3
"""Pre-commit hook: 禁止领域语义的裸字符串字面量（ADR-0017）。

检测应该使用枚举却使用了裸字符串的比较场景：
  - action_type == "respond"      → 应用 ActionType.RESPOND
  - status == "completed"         → 应用 TaskStatus.COMPLETED
  - verdict == "on_track"         → 应用 ReflectionVerdict.ON_TRACK
  - event_name == "post_act"      → 应用 HookEvent.POST_ACT

白名单排除：
  - 日志/错误消息中的字符串
  - 注释行
  - 测试文件
  - contracts/enums.py（枚举定义本身）
"""

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# ── 已知领域枚举值 → 枚举引用名 ──
_DOMAIN_STRINGS = {
    '"respond"': "ActionType.RESPOND",
    '"use_tool"': "ActionType.USE_TOOL",
    '"delegate"': "ActionType.DELEGATE",
    '"handoff"': "ActionType.HANDOFF",
    '"completed"': "TaskStatus.COMPLETED",
    '"failed"': "TaskStatus.FAILED",
    '"working"': "TaskStatus.WORKING",
    '"on_track"': "ReflectionVerdict.ON_TRACK",
    '"needs_correction"': "ReflectionVerdict.NEEDS_CORRECTION",
    '"blocked"': "ReflectionVerdict.BLOCKED",
    '"degraded_but_completed"': "ReflectionVerdict.DEGRADED_BUT_COMPLETED",
    '"post_act"': "HookEvent.POST_ACT",
    '"pre_think"': "HookEvent.PRE_THINK",
    '"post_reflect"': "HookEvent.POST_REFLECT",
    '"on_start"': "HookEvent.ON_START",
    '"on_error"': "HookEvent.ON_ERROR",
    '"on_complete"': "HookEvent.ON_COMPLETE",
    '"ok"': "SpanStatus.OK",
    '"error"': "SpanStatus.ERROR",
    '"roster_coverage"': "CompletionPolicyName.ROSTER_COVERAGE",
}

# ── 文件级白名单 ──
_FILE_ALLOWLIST = frozenset(
    {
        "lca/contracts/enums.py",
        "lca/contracts/semantic_keys.py",
    }
)


def _should_skip_line(line):
    stripped = line.strip()
    # 跳过注释行（包括 docstring 内的注释）
    if stripped.startswith("#") or stripped.startswith("-"):
        return True
    # 跳过日志/错误/格式化字符串
    if re.search(r"(print|logger|logging|raise\s+\w+Error)", stripped):
        return True
    # 跳过 f-string
    if re.search(r'f["\']', stripped):
        return True
    # 跳过 Literal 类型定义
    return "Literal[" in stripped


def _check_file(filepath):
    rel = str(filepath.relative_to(_ROOT))
    if rel in _FILE_ALLOWLIST:
        return []
    if "tests/" in rel:
        return []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    violations = []
    lines = content.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if _should_skip_line(stripped):
            continue

        for str_literal, enum_ref in _DOMAIN_STRINGS.items():
            # 只匹配 == "value" 或 != "value" 模式（比较操作）
            pattern = re.compile(r"[!=]=\s*" + re.escape(str_literal))
            if pattern.search(stripped):
                violations.append(f"  {rel}:{i}: 裸字符串比较 {str_literal} → 请用 {enum_ref}")
                violations.append(f"    {stripped}")

    return violations


def main():
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:] if f.endswith(".py")]
    else:
        files = sorted((_ROOT / "lca").rglob("*.py"))

    all_violations = []
    for f in files:
        if f.is_file():
            all_violations.extend(_check_file(f))

    if all_violations:
        print("❌ 发现领域语义裸字符串比较（ADR-0017）：")
        print()
        for v in all_violations:
            print(v)
        print()
        print("请使用对应的枚举常量替代裸字符串。")
        print("详见 lca/contracts/enums.py 和 ADR-0017。")
        return 1

    print("✅ 裸字符串检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
