#!/usr/bin/env python3
"""检测隐式实现 contracts Protocol 但未显式继承的类。

扫描 ``lca/contracts/protocols/`` 下所有 Protocol 定义，提取方法名集合，
再扫描 ``lca/`` 全量代码，找出"方法集覆盖某 Protocol 全部方法、
但 class 定义里没有继承该 Protocol"的类。

用法：
    uv run python scripts/check_protocol_impl.py          # 默认扫描
    uv run python scripts/check_protocol_impl.py --fix    # 输出建议修复行

退出码：0 = 通过，1 = 发现隐式实现，2 = 内部错误。
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_PROTOCOLS_DIR = _ROOT / "lca" / "contracts" / "protocols"
_SCAN_DIRS = [
    _ROOT / "lca",
    _ROOT / "gateway",
]
_SKIP_DIRS = {"__pycache__", ".mypy_cache", ".venv", "node_modules"}
_DUNDER_SKIP = frozenset(
    {
        "__init__",
        "__init_subclass__",
        "__post_init__",
        "__repr__",
        "__str__",
        "__hash__",
        "__eq__",
        "__ne__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
        "__call__",
        "__getattr__",
        "__setattr__",
        "__delattr__",
        "__enter__",
        "__exit__",
        "__aiter__",
        "__anext__",
        "__await__",
        "__iter__",
        "__next__",
    }
)


@dataclass(frozen=True)
class ProtocolInfo:
    """一个 Protocol 的结构摘要。"""

    name: str
    methods: frozenset[str]
    attrs: frozenset[str]
    bases: frozenset[str]
    source_file: str


@dataclass
class ClassInfo:
    """一个 class 的结构摘要。"""

    name: str
    file: Path
    lineno: int
    bases: list[str]
    methods: set[str] = field(default_factory=set)
    attrs: set[str] = field(default_factory=set)
    is_protocol: bool = False
    is_abc: bool = False


# ── 收集 ─────────────────────────────────────────────────────────


def _parse_file(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _base_name(node: ast.expr) -> str:
    """从 AST 节点提取基类名称字符串。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_base_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return ""


def _collect_protocols() -> list[ProtocolInfo]:
    """扫描 contracts/protocols/ 下所有 Protocol 定义。"""
    protos: list[ProtocolInfo] = []
    for py in sorted(_PROTOCOLS_DIR.rglob("*.py")):
        tree = _parse_file(py)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(_base_name(b) == "Protocol" for b in node.bases):
                continue
            methods: set[str] = set()
            attrs: set[str] = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_") and item.name not in _DUNDER_SKIP:
                        continue
                    if item.name.startswith("_"):
                        continue
                    methods.add(item.name)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    attrs.add(item.target.id)
            if methods or attrs:
                protos.append(
                    ProtocolInfo(
                        name=node.name,
                        methods=frozenset(methods),
                        attrs=frozenset(attrs),
                        bases=frozenset(
                            base
                            for base in (_base_name(base_node) for base_node in node.bases)
                            if base and base not in {"Protocol", "runtime_checkable"}
                        ),
                        source_file=str(py.relative_to(_ROOT)),
                    )
                )
    return protos


def _collect_classes() -> list[ClassInfo]:
    """扫描代码目录下所有 class 定义。"""
    classes: list[ClassInfo] = []
    for scan_dir in _SCAN_DIRS:
        for py in sorted(scan_dir.rglob("*.py")):
            if any(part in _SKIP_DIRS for part in py.parts):
                continue
            rel = str(py.relative_to(_ROOT))
            if "contracts/protocols" in rel:
                continue
            tree = _parse_file(py)
            if tree is None:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = [_base_name(b) for b in node.bases]
                is_protocol = any(base in {"Protocol", "runtime_checkable"} for base in bases)
                is_abc = any(base in {"ABC", "ABCMeta"} for base in bases)
                # 也检查 metaclass=ABCMeta
                for kw in node.keywords:
                    if kw.arg == "metaclass" and _base_name(kw.value) == "ABCMeta":
                        is_abc = True

                ci = ClassInfo(
                    name=node.name,
                    file=py,
                    lineno=node.lineno,
                    bases=bases,
                    is_protocol=is_protocol,
                    is_abc=is_abc,
                )
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not item.name.startswith("_"):
                            ci.methods.add(item.name)
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        ci.attrs.add(item.target.id)
                classes.append(ci)
    return classes


# ── 匹配 ─────────────────────────────────────────────────────────

# 已知允许的结构化匹配（白名单）。注释说明原因。
_ALLOWLIST: set[tuple[str, str]] = {
    # ObservabilityHub 显式继承了 ObservabilityBackend，不会被检出。
    # 以下是有意的结构化匹配，无需显式继承：
    # DeclarativeRuntimeDriver（lca/runtime/declarative_runtime.py）：
    #   脚本按方法名同构匹配到 Runtime Protocol，但 run(state: Any) /
    #   resume(checkpoint: DeclarativeCheckpoint) 与 Runtime.run(task, ctx, *,
    #   max_steps, max_wall_clock_seconds, agent_role) / resume(snapshot, input,
    #   max_steps) 签名不一致；前者是 PhaseGraph 解释器，后者是认知循环入口，
    #   概念正交（ADR-0076 §一 Constitution / Execution 分面）。架构上
    #   DeclarativeRuntimeDriver 不应继承 Runtime Protocol，避免误导读者以为
    #   该 driver 可作 task 入口使用。
    ("DeclarativeRuntimeDriver", "Runtime"),
    # RunModeRegistry（lca/plugins/seams.state.run_mode_registry）：
    #   脚本按方法名同构匹配到 ActionHandlerRegistry，但 register(adapter:
    #   ModeAdapter) / resolve(model: str) / registered() -> tuple[RegisteredMode, ...]
    #   与 ActionHandlerRegistry.register(action_type, handler) /
    #   resolve(action_type) / registered() -> tuple[str, ...] 参数语义完全不同。
    #   RunModeRegistry 没有对应 Protocol（plugin manifest 仅以字符串
    #   implements=["RunModeRegistry"] 声明），属 ADR-0076 §六 独立 seam。
    ("RunModeRegistry", "ActionHandlerRegistry"),
}

# 跳过名称含这些关键词的类（通常是 mock / stub / 测试辅助）
_SKIP_CLASS_PATTERNS = re.compile(
    r"(Mock|Stub|Fake|Dummy|Test|Spy|Record|Capture|Probe|Sentinel|NoOp|Null)",
    re.IGNORECASE,
)


def _inherits_protocol(
    base_names: list[str] | frozenset[str],
    protocol_name: str,
    protocols_by_name: dict[str, ProtocolInfo],
) -> bool:
    """Return whether a class base explicitly reaches a Protocol through inheritance."""
    pending = list(base_names)
    visited: set[str] = set()
    while pending:
        base = pending.pop()
        if base == protocol_name:
            return True
        if base in visited:
            continue
        visited.add(base)
        parent_protocol = protocols_by_name.get(base)
        if parent_protocol is not None:
            pending.extend(parent_protocol.bases)
    return False


def _is_implicit_impl(
    cls: ClassInfo,
    proto: ProtocolInfo,
    protocols_by_name: dict[str, ProtocolInfo],
) -> bool:
    """判断 cls 是否隐式实现了 proto（方法集全部覆盖但未继承）。"""
    # 已经直接或经由子 Protocol 显式继承。
    if _inherits_protocol(cls.bases, proto.name, protocols_by_name):
        return False
    # Protocol 方法非空且 cls 全部实现
    if not proto.methods:
        return False
    if not proto.methods.issubset(cls.methods):
        return False
    # 跳过 Mock/Stub/Fake 等测试辅助
    if _SKIP_CLASS_PATTERNS.search(cls.name):
        return False
    # 跳过自身是 Protocol 或 ABC 的类（它们是抽象定义，不是实现）
    if cls.is_protocol or cls.is_abc:
        return False
    # 跳过 __init__.py 中的 re-export wrapper
    if cls.file.name == "__init__.py":
        return False
    # 白名单
    if (cls.name, proto.name) in _ALLOWLIST:
        return False
    # 方法数过少时（1-2 个），要求类名和 Protocol 名有词素关联，减少误报
    if len(proto.methods) <= 2:
        proto_stem = _extract_stem(proto.name)
        if proto_stem and proto_stem.lower() not in cls.name.lower():
            return False
    return True


def _extract_stem(protocol_name: str) -> str:
    """从 Protocol 名称提取核心词干。

    ``TeamStrategy`` → ``Team``,
    ``ActionRegistryProtocol`` → ``ActionRegistry``.
    """
    stem = protocol_name.removesuffix("Protocol")
    # 取 CamelCase 的第一个词素组（如果是复合名取前缀）
    return stem


# ── 报告 ─────────────────────────────────────────────────────────


def main() -> int:
    fix_mode = "--fix" in sys.argv
    protos = _collect_protocols()
    classes = _collect_classes()

    if not protos:
        print("⚠️  未找到任何 Protocol 定义", file=sys.stderr)
        return 2

    protocols_by_name = {proto.name: proto for proto in protos}
    findings: list[tuple[ClassInfo, ProtocolInfo]] = []
    for cls in classes:
        for proto in protos:
            if _is_implicit_impl(cls, proto, protocols_by_name):
                findings.append((cls, proto))

    # 去重：同一 class 匹配多个 Protocol 时全部保留（可能实现多个接口）
    # 但排除：如果 A ⊂ B 且 cls 匹配 B，则 A 的匹配是冗余的
    findings = _dedup_subsets(findings)

    if not findings:
        print("✅ 所有 Protocol 实现均已显式继承")
        return 0

    print(f"❌ 发现 {len(findings)} 处隐式 Protocol 实现（未显式继承）：\n")
    for cls, proto in sorted(findings, key=lambda x: (str(x[0].file), x[0].lineno)):
        rel = str(cls.file.relative_to(_ROOT))
        methods_str = ", ".join(sorted(proto.methods))
        print(f"  {rel}:{cls.lineno}: {cls.name} → {proto.name}")
        print(f"    方法集: {{{methods_str}}}")
        if fix_mode:
            # 给出修复建议
            proto_module = _proto_import_path(proto.source_file)
            print(f"    修复: from {proto_module} import {proto.name}")
            print(f"    改为: class {cls.name}({proto.name}):")
        print()

    print(f"共 {len(findings)} 处。加 --fix 输出修复建议。")
    return 1


def _dedup_subsets(
    findings: list[tuple[ClassInfo, ProtocolInfo]],
) -> list[tuple[ClassInfo, ProtocolInfo]]:
    """如果同一 class 匹配 P_small 和 P_big，且 P_small ⊂ P_big，去掉小集合匹配。"""
    by_class: dict[str, list[ProtocolInfo]] = {}
    for cls, proto in findings:
        key = f"{cls.file}:{cls.name}"
        by_class.setdefault(key, []).append(proto)

    kept: list[tuple[ClassInfo, ProtocolInfo]] = []
    for cls, proto in findings:
        key = f"{cls.file}:{cls.name}"
        siblings = by_class[key]
        is_subset = any(
            other is not proto
            and proto.methods.issubset(other.methods)
            and len(proto.methods) < len(other.methods)
            for other in siblings
        )
        if not is_subset:
            kept.append((cls, proto))
    return kept


def _proto_import_path(source_file: str) -> str:
    """将 ``lca/contracts/protocols/infra.py`` 转为 ``lca.contracts.protocols.runtime.infra``。"""
    return source_file.removesuffix(".py").replace("/", ".")


if __name__ == "__main__":
    sys.exit(main())
