#!/usr/bin/env python3
"""观测面 SSOT 守门:任何 reader/writer/CLI 必须走 :mod:`lca.contracts.observability.ssot`。

背景:docs/notes/proposed/seam/2026-09-03-observation-ssot-registry.md L3。
设计:CI 阻断硬编码文件名 / 路径 / Status 字面字符串 / 反向耦合 / 重复 SSOT。

覆盖反模式:
1. 文件名裸字符串("events.jsonl" / "journal.json" / "manifest.json" 等)
2. Status 字符串字面(in {"success","failed","cancelled",...})
3. ExecutionOutcome 字面 Literal["completed",...]
4. RunStatus 反向耦合(plugin → session.session)
5. to_jsonable 重复定义(全 src = 1 命中)
6. seam_key: str 字面(CapabilityKey 应取代)
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# ── 白名单:这些文件定义 SSOT,允许裸字符串 ──
_FILE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "lca/contracts/observability/ssot.py",
        "lca/infrastructure/observability/spine/sinks/naming.py",
        "lca/infrastructure/observability/backends/run_locator_fs.py",
        "lca/contracts/observability/run_locator.py",
        "lca/contracts/observability/model_visible_capture.py",
        "lca/infrastructure/observability/spine/sinks/file_sink.py",
        "scripts/check_observation_ssot.py",
    }
)
"""SSOT 定义文件 + 本守门脚本自身。"""

_DIR_ALLOWLIST: frozenset[str] = frozenset(
    {
        "tests/",  # 测试可写硬编码(模拟 fixture / 期望值)
        "vendor/",  # vendored 代码不动
        "lobehub-ui/",  # LobeHub 同步目录不动
        ".lca-ops/",  # 运行产物
        "docs/notes/",  # note 文本内可引用字符串字面
    }
)
"""目录白名单(整目录豁免)。"""

# ── 反模式规则 ───────────────────────────────────

# 反模式 1:文件名裸字符串
_FILE_NAME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ('"events.jsonl"', re.compile(r'"events\.jsonl"')),
    ('"journal.json"', re.compile(r'"journal\.json"')),
    ('"manifest.json"', re.compile(r'"manifest\.json"')),
    ('"journal.narrative.md"', re.compile(r'"journal\.narrative\.md"')),
    ('"kernel.log"', re.compile(r'"kernel\.log"')),
    ('"<run_id>.exceptions.jsonl"', re.compile(r'f?"{run_id}\.exceptions\.jsonl"')),
    ('"profile_snapshot.json"', re.compile(r'"profile_snapshot\.json"')),
]

# 反模式 2:Status 字符串字面 in {...}
_STATUS_SET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        'in {"success","failed","cancelled","paused"}',
        re.compile(r'\bin\s*\{\s*"success"\s*,\s*"failed"\s*,\s*"cancelled"\s*,\s*"paused"\s*\}'),
    ),
    (
        'in {"success","failed","cancelled"}',
        re.compile(r'\bin\s*\{\s*"success"\s*,\s*"failed"\s*,\s*"cancelled"'),
    ),
    (
        'in {"completed","paused","failed"}',
        re.compile(r'\bin\s*\{\s*"completed"\s*,\s*"paused"\s*,\s*"failed"'),
    ),
    (
        'in {"completed","succeeded","failed","canceled"}',
        re.compile(r'\bin\s*\{\s*"completed"\s*,\s*"succeeded"\s*,\s*"failed"\s*,\s*"canceled"'),
    ),
]

# 反模式 3:ExecutionOutcome 字面 Literal
_EXECUTION_OUTCOME_LITERAL: list[tuple[str, re.Pattern[str]]] = [
    (
        'Literal["completed","failed","paused","stopped","in_progress"]',
        re.compile(
            r'Literal\["completed"\s*,\s*"failed"\s*,\s*"paused"\s*,\s*"stopped"\s*,\s*"in_progress"\]'
        ),
    ),
    (
        'Literal["completed","paused","failed"]',
        re.compile(r'Literal\["completed"\s*,\s*"paused"\s*,\s*"failed"\]'),
    ),
    (
        'Literal["completed","paused","failed","effect_uncertain"]',
        re.compile(
            r'Literal\["completed"\s*,\s*"paused"\s*,\s*"failed"\s*,\s*"effect_uncertain"\]'
        ),
    ),
]

# 反模式 4:RunStatus 反向耦合(plugin → session.session)
_PLUGIN_RUN_STATUS_IMPORT: list[tuple[str, re.Pattern[str]]] = [
    (
        "plugin/transport → session.session RunStatus import",
        re.compile(
            r"from\s+lca\.plugins\.transport\.webserver\.handlers\.runs\.session\.session\s+import\s+.*RunStatus"
        ),
    ),
]

# 反模式 5:to_jsonable 重复(全 repo 应只有 1 处定义)
_TO_JSONABLE_DEF: list[tuple[str, re.Pattern[str]]] = [
    ("def to_jsonable", re.compile(r"^def\s+to_jsonable\s*\(")),
]

# 反模式 6:seam_key: str 字面(CapabilityKey 应取代)
_SEAM_KEY_STR: list[tuple[str, re.Pattern[str]]] = [
    ("seam_key: str (pure, not Union)", re.compile(r"seam_key:\s*str(?:\s|$|\)|,)")"),
]


def _is_path_allowed(rel: str) -> bool:
    if rel in _FILE_ALLOWLIST:
        return True
    return any(rel.startswith(d) for d in _DIR_ALLOWLIST)


def _line_in_docstring(line: str) -> bool:
    """启发式:跳过 docstring / 注释行(以 # 开头或空行)。"""
    stripped = line.strip()
    if not stripped:
        return True
    return bool(stripped.startswith("#"))


def _check_file(
    path: Path,
    rules: list[tuple[str, re.Pattern[str]]],
) -> list[str]:
    """扫描单个 .py 文件,返回违规行号。"""
    rel = str(path.relative_to(_ROOT))
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    violations: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if _line_in_docstring(line):
            continue
        for label, pattern in rules:
            if pattern.search(line):
                violations.append(f"  {rel}:{i}: {label}: {line.strip()[:80]}")
    return violations


def _check_to_jsonable_def(files: Iterable[Path]) -> list[str]:
    """to_jsonable 必须只在 contracts/observability/ssot.py 定义 1 次。"""
    matches: list[str] = []
    for f in files:
        if f.suffix != ".py":
            continue
        rel = str(f.relative_to(_ROOT))
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for j, line in enumerate(text.splitlines(), 1):
            if _TO_JSONABLE_DEF[0][1].match(line):
                matches.append(f"  {rel}:{j}: def to_jsonable")
    expected_count = 1
    extra = len(matches) - expected_count
    if extra <= 0:
        return []
    return [
        f"❌ def to_jsonable 定义 {len(matches)} 处,应为 {expected_count};多出的命中:\n"
        + "\n".join(matches)
    ]


def _collect_python_files() -> list[Path]:
    return sorted((_ROOT / "lca").rglob("*.py"))


def main() -> int:
    files = _collect_python_files()
    files = [f for f in files if not _is_path_allowed(str(f.relative_to(_ROOT)))]

    all_violations: list[str] = []

    rule_groups: list[tuple[str, list[tuple[str, re.Pattern[str]]]]] = [
        ("反模式 1:文件名裸字符串", _FILE_NAME_PATTERNS),
        ("反模式 2:Status 字符串字面", _STATUS_SET_PATTERNS),
        ("反模式 3:ExecutionOutcome 字面 Literal", _EXECUTION_OUTCOME_LITERAL),
        ("反模式 4:RunStatus 反向耦合", _PLUGIN_RUN_STATUS_IMPORT),
        ("反模式 6:seam_key: str 字面", _SEAM_KEY_STR),
    ]

    for label, rules in rule_groups:
        per_file_violations: list[str] = []
        for f in files:
            per_file_violations.extend(_check_file(f, rules))
        if per_file_violations:
            all_violations.append(f"\n## {label}\n" + "\n".join(per_file_violations))

    # 反模式 5(too_jsonable 重复)需要看全 repo,包括 SSOT 定义侧
    all_py = list(_ROOT.rglob("*.py"))
    to_jsonable_violations = _check_to_jsonable_def(all_py)
    if to_jsonable_violations:
        all_violations.append(
            "\n## 反模式 5:to_jsonable 重复定义\n" + "\n".join(to_jsonable_violations)
        )

    if all_violations:
        print("❌ 观测面 SSOT 守门失败:")
        print("\n".join(all_violations))
        print()
        print("请走 lca.contracts.observability.ssot 的 helper / RunLocator 协议。")
        print("详见 docs/notes/proposed/seam/2026-09-03-observation-ssot-registry.md L3。")
        return 1

    print("✅ 观测面 SSOT 守门通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
