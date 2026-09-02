#!/usr/bin/env python3
"""ADR-0169 L12 / I-CURSOR-4:cordis event name 必须由 EventDescriptor 派生。

业务 / plugin 代码禁止直字面 ``ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')``。
所有 cordis 事件名必须经 ``EventDescriptor.derive(execution_point)`` 走
``lca.contracts.observability.cordis_event_table`` 派生表查表得到;防止
业务 / 插件自创事件词表绕过 spine L10 单写约束(评审 §S4 处方)。

PR-30 强化(评审 §S4 + §D9):
- 业务层 ``ctx.emit`` 违规从 WARNING 升级为 ERROR(exit 1);
- 增 I-CURSOR-4 结构门禁:``EventDescriptor`` 必须含 ``cordis_name`` 字段;
- 增 cordis 双词表收口结构门禁:``lca/cognition/event_bus.py`` 必须删除
  (评审 §S4 处方 + §D9 删除清单);``event_bus.py`` 文件名仍可作为 audit
  hook-attach 的语义性 allowlist,但 CordisEventBus 业务包装不可再出现;
- 扫描范围(业务 + 横切层):
    - ``lca/cognition/``
    - ``lca/runtime/``
    - ``lca/agent/``
  注意:仓库内不存在 ``lca/body/`` 顶层目录;``lca/cognition/body/`` 是
  替代(对应 task spec 提及的 ``lca/body``)。本脚本对应读取 spec 中
  的语义,扫描真实存在的业务代码路径。

退出码:0 = pass;非 0 = 列出每条违规(CI fail-fast)。

用法::

    uv run python scripts/check_cordis_event_derivation.py

设计依据:
- ADR-0169 §L12(I-CURSOR-4):cordis event name 由 EventDescriptor.cordis_name 派生
- ADR-0168-final §D14:cursor.emit 只在 descriptor.cordis_name is not None 时调用
- ADR-0169 §D9 删除清单条目 ``coord.emit_phase / coord.emit`` 均为本门禁的目标
- ADR-0169 §D9 + 评审 §S4:CordisEventBus 业务包装必须删除,只有 spine 单写
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Violation:
    """单条 PR-30 违规,带 file:line:event 前缀与 reason。"""

    path: str
    line: int
    message: str
    category: str  # "L12" | "I-CURSOR-4" | "I-CURSOR-4-removal"


def _is_skippable_line(stripped: str) -> bool:
    """该行是否应跳过(纯注释或 docstring 单行起点)。"""
    return any(stripped.startswith(prefix) for prefix in _COMMENT_PREFIXES) or stripped.startswith(
        ('"', "'", '"""', "'''")
    )


def _scan_file_business_emit(path: Path) -> list[Violation]:
    """扫描单个 .py 文件,返回 L12 (ctx.emit 字面量) 违规列表。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[Violation] = []
    rel = str(path.relative_to(REPO_ROOT))

    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if _is_skippable_line(stripped):
            continue
        match = EMIT_RE.search(line)
        if match is None:
            continue
        event_name = match.group(1)
        if any(event_name.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            out.append(
                Violation(
                    path=rel,
                    line=idx,
                    message=f"ctx.emit({event_name!r}) — 业务禁止直字面 emit",
                    category="L12",
                )
            )
    return out


def _check_event_descriptor_has_cordis_name() -> list[Violation]:
    """I-CURSOR-4:``EventDescriptor`` 必须含 ``cordis_name`` 字段。

    用 AST 静态解析 dataclass 字段;若 ``cordis_name`` 缺失或被 rename 为
    其他名字 ⇒ 违规(防止 EventDescriptor 失掉 cordis 派生职责)。
    """
    out: list[Violation] = []
    descriptor_path = REPO_ROOT / "lca" / "contracts" / "observability" / "event_descriptor.py"
    if not descriptor_path.exists():
        return [
            Violation(
                path="lca/contracts/observability/event_descriptor.py",
                line=0,
                message="EventDescriptor 模块不存在(ADR-0169 §D6 / I-CURSOR-4 必存)",
                category="I-CURSOR-4",
            )
        ]

    source = descriptor_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(descriptor_path))
    except SyntaxError as exc:
        return [
            Violation(
                path=str(descriptor_path.relative_to(REPO_ROOT)),
                line=exc.lineno or 0,
                message=f"EventDescriptor AST 解析失败: {exc.msg}",
                category="I-CURSOR-4",
            )
        ]

    rel = str(descriptor_path.relative_to(REPO_ROOT))
    found_class: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "EventDescriptor":
            found_class = node
            break
    if found_class is None:
        return [
            Violation(
                path=rel,
                line=0,
                message="EventDescriptor 类缺失(ADR-0169 §D6 / I-CURSOR-4 必存)",
                category="I-CURSOR-4",
            )
        ]

    has_cordis_name = any(
        isinstance(stmt, ast.AnnAssign)
        and isinstance(stmt.target, ast.Name)
        and stmt.target.id == "cordis_name"
        for stmt in found_class.body
    )
    if not has_cordis_name:
        out.append(
            Violation(
                path=rel,
                line=found_class.lineno,
                message="EventDescriptor 缺 cordis_name 字段(ADR-0169 I-CURSOR-4)",
                category="I-CURSOR-4",
            )
        )
    return out


def _check_cordis_event_bus_removed() -> list[Violation]:
    """评审 §S4 + ADR-0169 §D9:CordisEventBus 业务包装必须删除。

    ``lca/cognition/event_bus.py`` 是 cordis 双词表收口目标 —— 所有
    cordis 事件总线职责已转移到 ``EventDescriptor.derive()`` 单派生表。
    本 PR 之后,任何残留的 CordisEventBus 类定义都视为违规。
    """
    out: list[Violation] = []
    target = REPO_ROOT / "lca" / "cognition" / "event_bus.py"
    if not target.exists():
        return out

    source = target.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(target))
    except SyntaxError:
        # 文件存在但语法错:仍按存在处理,违规。
        return [
            Violation(
                path=str(target.relative_to(REPO_ROOT)),
                line=0,
                message="CordisEventBus 模块未删除(ADR-0169 §D9 / 评审 §S4)",
                category="I-CURSOR-4-removal",
            )
        ]

    rel = str(target.relative_to(REPO_ROOT))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CordisEventBus":
            out.append(
                Violation(
                    path=rel,
                    line=node.lineno,
                    message="CordisEventBus 类未删除(ADR-0169 §D9 / 评审 §S4)",
                    category="I-CURSOR-4-removal",
                )
            )
            break
        if isinstance(node, ast.FunctionDef) and node.name == "cordis_event_bus":
            out.append(
                Violation(
                    path=rel,
                    line=node.lineno,
                    message="cordis_event_bus() 工厂未删除(ADR-0169 §D9 / 评审 §S4)",
                    category="I-CURSOR-4-removal",
                )
            )
            break
    return out


def _scan_business_emit() -> list[Violation]:
    """跨所有扫描目录收集 L12 (ctx.emit 字面量) 违规。"""
    violations: list[Violation] = []
    for directory in SCAN_DIRS:
        if not directory.exists():
            continue
        for py_file in sorted(directory.rglob("*.py")):
            if not py_file.is_file():
                continue
            violations.extend(_scan_file_business_emit(py_file))
    return violations


def main() -> int:
    """主入口:返回 0 = pass,非 0 = fail-fast。

    PR-30 强化:三种违规都视为 ERROR 并整体 fail-fast。
    """
    emit_violations = _scan_business_emit()
    descriptor_violations = _check_event_descriptor_has_cordis_name()
    removal_violations = _check_cordis_event_bus_removed()
    all_violations = emit_violations + descriptor_violations + removal_violations

    if all_violations:
        print("PR-30 cordis double-vocabulary gate FAILED:")
        by_cat: dict[str, list[Violation]] = {}
        for v in all_violations:
            by_cat.setdefault(v.category, []).append(v)

        if "L12" in by_cat:
            print("\n[L12] 业务代码直字面 emit(评估 §S4 处方):")
            for v in by_cat["L12"]:
                print(f"  - {v.path}:{v.line}: {v.message}")
        if "I-CURSOR-4" in by_cat:
            print("\n[I-CURSOR-4] EventDescriptor 缺 cordis_name 字段:")
            for v in by_cat["I-CURSOR-4"]:
                print(f"  - {v.path}:{v.line}: {v.message}")
        if "I-CURSOR-4-removal" in by_cat:
            print("\n[I-CURSOR-4-removal] CordisEventBus 业务包装未删除:")
            for v in by_cat["I-CURSOR-4-removal"]:
                print(f"  - {v.path}:{v.line}: {v.message}")

        print(
            "\nBusiness code MUST NOT call ctx.emit('agent.*' / 'phase.*' / "
            "'tool.*' / 'llm.*') directly.\n"
            "Use: EventDescriptor.derive(execution_point) -> ctx.emit(descriptor.cordis_name)"
        )
        return 1

    print(
        "PR-30 OK: 0 violations "
        "(L12 业务 emit + I-CURSOR-4 EventDescriptor + I-CURSOR-4-removal CordisEventBus 全部通过)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
