#!/usr/bin/env python3
"""Pre-commit hook: 禁止裸 Any 类型标注。

扫描 lca/ 下所有 .py 文件，检测 `from typing import Any` 的使用。
以下场景允许 Any（白名单模式）：
  - dict[str, Any]          — 开放 schema 容器（extra, attributes, arguments）
  - **kwargs: Any           — Protocol / hook 可变关键字参数
  - payload: Any            — 通用载荷（Observation.payload, Event.payload 等）
  - capabilities: Any       — 动态能力注入
  - replacement/wrapper: Any — 装饰器模式动态替换
  - impl: Any               — 泛型注册表
  - contracts/protocols/*   — Protocol 定义文件（结构性多态）

其余 Any 使用一律禁止，提交时阻断。
"""

import re
import sys
from pathlib import Path

# ── 白名单：这些文件/目录允许 Any ──
_FILE_ALLOWLIST = frozenset(
    {
        "lca/contracts/types.py",
        "lca/contracts/mechanisms.py",
    }
)

_DIR_ALLOWLIST = frozenset(
    {
        "lca/contracts/protocols/",  # Protocol 定义，结构性多态
    }
)

# ── 行级白名单模式 ──
_LINE_ALLOW_PATTERNS = [
    re.compile(r"dict\[str,\s*Any\]"),  # dict[str, Any]
    re.compile(r"\*\*kwargs:\s*Any"),  # **kwargs: Any
    re.compile(r"\*\*capabilities:\s*Any"),  # **capabilities: Any
    re.compile(r"payload:\s*Any"),  # payload: Any
    re.compile(r"replacement:\s*Any"),  # 装饰器模式
    re.compile(r"wrapper:\s*Any"),  # 装饰器模式
    re.compile(r"impl:\s*Any"),  # 泛型注册表
    re.compile(r"NamedRegistry\[Any\]"),  # 泛型注册表容器
    re.compile(r"\*\*attributes:\s*Any"),  # span 遥测可变属性
    re.compile(r"\*\*_ignored:\s*Any"),  # 工厂签名吞多余参数
    re.compile(r"members:\s*list\[Any\]"),  # 已标注注释说明
    re.compile(r"supervisor:\s*Any"),  # 跨层引用（有注释）
    re.compile(r"shared_memory:\s*Any"),  # 跨层引用（有注释）
    re.compile(r"ledger_factory.*Any"),  # 工厂返回类型
    re.compile(r"^\s*#"),  # 注释行
    re.compile(r"# .*(Any|protocol|跨层|动态|注册表)"),  # 带解释的 Any
    re.compile(r"from typing import.*\bAny\b.*# noqa"),
    re.compile(r"Callable\[\[Any\]"),  # Callable[[Any], ...]
    re.compile(r"list\[Any\]"),  # list[Any] (已审查)
    re.compile(r"-> Any"),  # 返回 Any（动态工厂）
    re.compile(r"_client:\s*Any"),  # 第三方 SDK 类型
    re.compile(r"validator:\s*Any"),  # getattr 动态属性
    re.compile(r"kind:\s*Any\s*="),  # extra.get 动态提取
    re.compile(r"final_output:\s*Any"),  # 框架运行槽位
    re.compile(r"retrieved_context:\s*list\[Any\]"),  # 检索结果多态
    re.compile(r"_team_progress:\s*Any"),  # 可选能力槽位
    re.compile(r"hook_fn:\s*Any"),  # hook 注册（动态类型）
    re.compile(r"last_observation:\s*Any"),  # 异常附带数据
    re.compile(r"approval_request:\s*Any"),  # 审批请求数据
    re.compile(r"_OPS.*dict\[type,\s*Any\]"),  # 操作映射表
    re.compile(r"_get_mcp_session.*->\s*Any"),  # 第三方 SDK session
    re.compile(r"_subs.*dict\[str.*Any"),  # 事件总线内部
]

_ROOT = Path(__file__).resolve().parent.parent


def _is_line_allowed(line):
    return any(pat.search(line) for pat in _LINE_ALLOW_PATTERNS)


def _check_file(filepath):
    """返回违规行列表（空 = 通过）。"""
    rel = str(filepath.relative_to(_ROOT))
    if rel in _FILE_ALLOWLIST:
        return []
    if any(rel.startswith(d) for d in _DIR_ALLOWLIST):
        return []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    if "Any" not in content:
        return []

    violations = []
    lines = content.splitlines()

    has_any_import = False
    for line in lines:
        if re.search(r"from\s+typing\s+import.*\bAny\b", line):
            has_any_import = True
            break

    if not has_any_import:
        return []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.search(r"^\s*(from\s+typing\s+import|import\s+typing)", stripped):
            continue
        if "TYPE_CHECKING" in stripped:
            continue
        if not re.search(r"\bAny\b", stripped):
            continue
        if _is_line_allowed(stripped):
            continue
        violations.append(f"  {rel}:{i}: {stripped}")

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
        print("❌ 发现裸 Any 类型标注：")
        print()
        for v in all_violations:
            print(v)
        print()
        print("允许模式: dict[str, Any] / **kwargs: Any / payload: Any 等")
        print("详见脚本顶部注释。")
        return 1

    print("✅ Any 检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
