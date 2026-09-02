#!/usr/bin/env python3
"""ADR-0169 L12 / I-CURSOR-4:cordis event name 必须由 EventDescriptor 派生。

业务 / plugin 代码禁止直字面 ``ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')``。
所有 cordis 事件名必须经 ``EventDescriptor.derive(execution_point)`` 走
``lca.contracts.observability.cordis_event_table`` 派生表查表得到;防止
业务 / 插件自创事件词表绕过 spine L10 单写约束(评审 §S4 处方)。

扫描范围(业务 + 横切层;PR-13 与 PR-30 共同生效):
- ``lca/cognition/``
- ``lca/runtime/``
- ``lca/agent/``

注意:仓库内不存在 ``lca/body/`` 顶层目录;``lca/cognition/body/`` 是
替代(对应 task spec 提及的 ``lca/body``)。本脚本对应读取 spec 中
的语义,扫描真实存在的业务代码路径。

退出码:0 = pass;非 0 = 列出每条 L12 违规(CI fail-fast)。

用法::

    uv run python scripts/check_cordis_event_derivation.py

设计依据:
- ADR-0169 §L12(I-CURSOR-4):cordis event name 由 EventDescriptor.cordis_name 派生
- ADR-0168-final §D14:cursor.emit 只在 descriptor.cordis_name is not None 时调用
- ADR-0169 §D9 删除清单条目 ``coord.emit_phase / coord.emit`` 均为本门禁的目标
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 业务层 + 协调层路径(与 check_writable_matrix_boundaries.py 对齐)
SCAN_DIRS: tuple[Path, ...] = (
    REPO_ROOT / "lca" / "cognition",
    REPO_ROOT / "lca" / "runtime",
    REPO_ROOT / "lca" / "agent",
)

# ADR-0169 §L12 + 评审 §S4 处方:禁止业务 emit 这些前缀。
# 这些前缀只能由 ``EventDescriptor.cordis_name`` 派生;业务代码不能直字面写。
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "agent.",
    "phase.",
    "tool.",
    "llm.",
)

# 匹配 ``ctx.emit('foo.bar')`` 或 ``ctx.emit("foo.bar")`` 单行形式;
# 多行 emit(call 跨行)不在本 PR 范围,后续 PR 按需扩展。
#   - ctx.emit('agent.step.start')
#   - self._ctx.emit("phase.think.fold")
EMIT_RE: re.Pattern[str] = re.compile(r"""ctx\.emit\(\s*['"]([^'"]+)['"]""")

# 跳过这些行段(注释行与 docstring)
_COMMENT_PREFIXES = ("#",)


def _is_skippable_line(stripped: str) -> bool:
    """该行是否应跳过(纯注释或 docstring 单行起点)。"""
    return any(stripped.startswith(prefix) for prefix in _COMMENT_PREFIXES) or stripped.startswith(
        ('"', "'", '"""', "'''")
    )


def _scan_file(path: Path) -> list[str]:
    """扫描单个 .py 文件,返回 L12 违规列表(带 file:line:event 前缀)。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []

    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if _is_skippable_line(stripped):
            continue
        match = EMIT_RE.search(line)
        if match is None:
            continue
        event_name = match.group(1)
        if any(event_name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            rel = path.relative_to(REPO_ROOT)
            out.append(f"{rel}:{idx}: ctx.emit({event_name!r})")
    return out


def _scan() -> list[str]:
    """跨所有扫描目录收集 L12 违规。"""
    violations: list[str] = []
    for directory in SCAN_DIRS:
        if not directory.exists():
            continue
        for py_file in sorted(directory.rglob("*.py")):
            if not py_file.is_file():
                continue
            violations.extend(_scan_file(py_file))
    return violations


def main() -> int:
    """主入口:返回 0 = pass,非 0 = fail-fast。"""
    violations = _scan()
    if violations:
        print("L12 cordis_name derivation guard FAILED:")
        for v in violations:
            print(f"  - {v}")
        print(
            "\nBusiness code MUST NOT call ctx.emit('agent.*' / 'phase.*' / "
            "'tool.*' / 'llm.*') directly.\n"
            "Use: EventDescriptor.derive(execution_point) -> ctx.emit(descriptor.cordis_name)"
        )
        return 1

    print("L12 OK: 0 violations (cordis_name derivation gate passes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
