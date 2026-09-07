#!/usr/bin/env python3
"""Route legacy code patterns to their delivery PR (ADR-0074 历史迁移)。

PR-0 audit 测量网产生 4 个基线:control-surface / state-writers /
direct-commands / hook-attach。本脚本把这些违规按归属文件路由到 ADR-0074
实施矩阵中的 owner PR，输出人可读的迁移路线图，可被:

- tracker §"历史迁移路线图" 段同步使用
- lca-ops status adr-supervision 子命令展示
- 检查脚本(建议)固定基线是否下降

PR-0199-P1-14 扩展:新增两个 ADR-0199 §11 / §12.1 审计种类:

- ``facade_bypass`` — ``resolve_profile`` / ``compile_plan`` 调用出现在
  ``lca/application/runtime/`` 之外的生产代码(HPC-L2)。harness 是合法
  内部使用方;tests / scripts / vendor / lca_kernel 全部豁免。
- ``intent_construction_outside_adapters`` — ``RunIntent(...)`` 构造出现在
  ``lca/application/runtime/adapters/`` 与 ``default_facade.py`` 之外
  (I-HPC-1)。仅当文件 import 了 ``lca.contracts.runtime.intent.RunIntent``
  才计入;transport handlers 内的本地同名词 dataclass 不误报。

退出码 0 = 总是返回(无 fail 路径;本脚本只生成迁移建议 / 列出违规)。

用法:
  uv run python scripts/route_legacy_patterns.py              # human
  uv run python scripts/route_legacy_patterns.py --json       # machine
  uv run python scripts/route_legacy_patterns.py --md         # markdown

Authority: ADR-0199 §11 (CI / 架构门禁扩展) + §12.1 (COMPAT 模板)。
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# Scripts at the top level must bootstrap ``sys.path`` so the in-repo ``lca``
# package is importable when invoked as ``python scripts/<name>.py``.
sys.path.insert(0, str(_REPO))


# ── ADR-0074 PR owner table ───────────────────────────────────
#
# Each bucket is keyed by an audit-kind and a path-prefix (relative to repo
# root). Match longest prefix wins.
#
# Owner PR numbering follows the tracker §1 status table.

_OWNER_TABLE: dict[str, list[tuple[str, str, str]]] = {
    "state_writers": [
        # (path-prefix, owner-PR, rationale)
        ("lca/cognition/body/", "PR-7", "CommandEnvelope 收口 + Body.execute 5 闸"),
        ("lca/cognition/memory/", "PR-3", "MemoryPolicy / CapabilityPlan 中读写"),
        ("lca/cognition/brain/", "PR-4", "ModularBrain / Reasoner 写入"),
        ("lca/cognition/skill_router/", "PR-4", "SkillRouter 决策写"),
        ("lca/cognition/sensors/", "PR-3", "PerceiveHub / Sensor 收敛"),
        ("lca/runtime/", "PR-4", "runtime_loop;停止决策由 State 群 StopPolicy 提供"),
        ("lca/agent/", "PR-4", "Team / DecisionGate"),
    ],
    "direct_commands": [
        ("lca/cognition/body/", "PR-7", "Body.execute 必经 envelope"),
        ("lca/plugins/body/", "PR-7", "plugin Body 必须经 SafeExecutor"),
    ],
    "hook_attach": [
        ("lca/cognition/", "PR-7", "EventBus / HookMiddleware 收口"),
        ("lca/runtime/", "PR-7", "runtime_loop 走 envelope"),
        ("lca/agent/", "PR-7", "Agent / Team 走 envelope"),
        ("lca/application/", "PR-7", "spawn -> bind_plan 收口"),
    ],
    "control_surface": [
        ("lca/plugins/", "PR-2", "PluginSpec.contributes 声明式控制面"),
        ("bundles/", "PR-2", "禁止重引入 Bundle YAML control"),
        ("profiles/", "PR-2", "禁止重引入 Profile YAML control"),
    ],
    # ADR-0199 P1-14 HPC-L2 + I-HPC-1 审计种类。
    # 经 facade 是默认路径;新增命中应当成为 P1-11 / P1-13 / 后续 PR 修复目标。
    "facade_bypass": [
        ("lca/plugins/transport/", "PR-0199-P1-11", "transport handler 必须经 RuntimeFacade"),
        ("lca/infrastructure/cli/", "PR-0199-P1-13", "CLI runs create 必须经 RuntimeFacade"),
        ("lca/cognition/", "PR-0199", "认知层不应直接 resolve/compile"),
        ("lca/agent/", "PR-0199", "Agent 层不应直接 resolve/compile"),
        ("lca/runtime/", "PR-0199", "runtime 层不应直接 resolve/compile"),
    ],
    "intent_construction_outside_adapters": [
        ("lca/plugins/transport/", "PR-0199-P1-11", "transport 不得构造 RunIntent;走 adapter"),
        ("lca/infrastructure/cli/", "PR-0199-P1-13", "CLI 不得构造 RunIntent;走 adapter"),
        ("lca/cognition/", "PR-0199", "认知层不得构造 RunIntent"),
        ("lca/agent/", "PR-0199", "Agent 层不得构造 RunIntent"),
        ("lca/runtime/", "PR-0199", "runtime 层不得构造 RunIntent"),
    ],
}


def _resolve_owner(audit_kind: str, path: str) -> tuple[str, str]:
    """Pick the longest-prefix match in ``_OWNER_TABLE`` for an audit finding.

    Returns:
        ``(owner_pr, rationale)``. Falls back to ``("PR-99", "未路由 / 待 PR-99 处理")``.
    """
    table = _OWNER_TABLE.get(audit_kind, [])
    best = ("PR-99", "未路由 / 待 PR-99 处理")
    best_len = -1
    for prefix, pr, rationale in table:
        if path.startswith(prefix) and len(prefix) > best_len:
            best = (pr, rationale)
            best_len = len(prefix)
    return best


# ── Finding shape (mirrors lca.harness.diagnostics.audit.Finding) ────


@dataclass(frozen=True)
class Finding:
    """One audit finding.

    The new audit kinds (``facade_bypass`` +
    ``intent_construction_outside_adapters``) produce findings in the
    same shape so the bucketizer stays generic.
    """

    path: str
    line: int
    col: int
    kind: str
    message: str


# ── AST helpers (PR-0199-P1-14 HPC-L2 + I-HPC-1) ────────────────

# Forbidden call symbols for the ``facade_bypass`` audit kind.
# HPC-L2: production path goes through ``RuntimeFacade``; bare references
# to ``resolve_profile`` / ``compile_plan`` outside the runtime facade are
# forbidden by ADR-0199 §11. ``compute_activation_ref`` is intentionally
# not in this set — it is a pure utility exported from ``lca.harness``
# (lca/harness/runtime/activation_ref.py) and is the canonical impl.
_FACADE_BYPASS_FORBIDDEN: frozenset[str] = frozenset({"resolve_profile", "compile_plan"})

# I-HPC-1: ``RunIntent(...)`` constructor must only fire from the L1
# adapters + facade. Exempt paths are checked below.
_INTENT_ADAPTERS_PATH = "lca/application/runtime/adapters/"
_INTENT_FACADE_PATH = "lca/application/runtime/default_facade.py"
_INTENT_CONTRACT_PATH = "lca/contracts/runtime/intent.py"

# Module path whose import of ``RunIntent`` brings the L1 contract symbol
# into scope. Files importing this name may construct the L1 contract;
# files that only define a *local* dataclass named ``RunIntent`` are not
# audited (their ``RunIntent(...)`` call site resolves to the local class).
_INTENT_CONTRACT_IMPORT = "lca.contracts.runtime.intent"


def _iter_python_files(roots: Sequence[Path]) -> list[Path]:
    """Return sorted ``.py`` files under any of ``roots``.

    Skips ``__pycache__`` directories; tests / scripts / vendor / lca_kernel
    are excluded by the caller (see ``_scan_facade_bypass`` /
    ``_scan_intent_construction_outside_adapters``).
    """
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path in seen:
                continue
            seen.add(path)
            out.append(path)
    return sorted(out)


def _safe_parse(path: Path) -> ast.Module | None:
    """Parse a file with ``ast.parse``; return ``None`` on SyntaxError."""
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def _file_imports_intent_contract(tree: ast.Module) -> bool:
    """Return True iff the module imports ``RunIntent`` from
    ``lca.contracts.runtime.intent``.

    Uses ``ast`` rather than ``isinstance`` so the check survives
    ``import as`` rebinding (``from lca.contracts.runtime.intent import
    RunIntent as RI`` still imports the symbol; we accept the alias by
    checking the imported *name* matches).
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != _INTENT_CONTRACT_IMPORT:
            continue
        for alias in node.names:
            if alias.name == "RunIntent":
                return True
    return False


def _is_facade_bypass_exempt(rel_posix: str) -> bool:
    """HPC-L2 exempt paths for the ``facade_bypass`` audit.

    Exempt:
    - ``lca/application/runtime/`` — facade lives here.
    - ``lca/harness/`` — resolve_profile / compile_plan are exported here
      and the harness implementation is the canonical home.
    - ``tests/`` — test code may call them directly.
    - ``scripts/`` — migration scripts.
    - ``vendor/`` — vendored.
    - ``lca_kernel/`` — host package (top-level).
    """
    if rel_posix.startswith("lca/application/runtime/"):
        return True
    if rel_posix.startswith("lca/harness/"):
        return True
    if rel_posix.startswith("tests/"):
        return True
    if rel_posix.startswith("scripts/"):
        return True
    if rel_posix.startswith("vendor/"):
        return True
    return bool(rel_posix.startswith("lca_kernel/"))


def _is_intent_construction_exempt(rel_posix: str) -> bool:
    """I-HPC-1 exempt paths for ``intent_construction_outside_adapters``.

    Exempt:
    - ``lca/application/runtime/`` — adapters + facade are the canonical
      construction sites.
    - ``lca/contracts/runtime/intent.py`` — the class definition itself.
    - ``tests/`` — test code is exempt by contract.
    - ``scripts/`` — migration scripts.
    - ``vendor/`` / ``lca_kernel/`` — out of LCA authoring scope.
    """
    if rel_posix.startswith(_INTENT_ADAPTERS_PATH):
        return True
    if rel_posix == _INTENT_FACADE_PATH:
        return True
    if rel_posix == _INTENT_CONTRACT_PATH:
        return True
    if rel_posix.startswith("tests/"):
        return True
    if rel_posix.startswith("scripts/"):
        return True
    if rel_posix.startswith("vendor/"):
        return True
    return bool(rel_posix.startswith("lca_kernel/"))


def _scan_facade_bypass(repo: Path) -> list[Finding]:
    """HPC-L2 audit: ``resolve_profile`` / ``compile_plan`` outside
    ``lca/application/runtime/`` and ``lca/harness/``.

    AST-based (not grep) so it survives formatting, comments, and string
    occurrences. Skips ``tests/``, ``scripts/``, ``vendor/``, ``lca_kernel/``.
    """
    roots = [repo / "lca"]
    out: list[Finding] = []
    for path in _iter_python_files(roots):
        rel = path.relative_to(repo).as_posix()
        if _is_facade_bypass_exempt(rel):
            continue
        tree = _safe_parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name: str | None = None
            if isinstance(func, ast.Name) and func.id in _FACADE_BYPASS_FORBIDDEN:
                name = func.id
            elif isinstance(func, ast.Attribute) and func.attr in _FACADE_BYPASS_FORBIDDEN:
                name = func.attr
            if name is None:
                continue
            out.append(
                Finding(
                    path=str(path),
                    line=getattr(node, "lineno", 0),
                    col=getattr(node, "col_offset", 0),
                    kind=f"facade_bypass::{name}",
                    message=(
                        f"{name}(...) called outside RuntimeFacade "
                        f"(ADR-0199 §11 HPC-L2). Wrap via "
                        "DefaultRuntimeFacade.resolve_activation."
                    ),
                )
            )
    return out


def _scan_intent_construction_outside_adapters(repo: Path) -> list[Finding]:
    """I-HPC-1 audit: ``RunIntent(...)`` constructed outside
    ``lca/application/runtime/adapters/`` and ``default_facade.py``.

    To avoid false positives on locally-defined ``class RunIntent`` (e.g.
    ``lca/plugins/transport/webserver/handlers/runs/session/intent/intent.py``
    declares its own carrier ``RunIntent``), the scanner only fires when
    the file imports ``RunIntent`` from ``lca.contracts.runtime.intent``.
    """
    roots = [repo / "lca"]
    out: list[Finding] = []
    for path in _iter_python_files(roots):
        rel = path.relative_to(repo).as_posix()
        if _is_intent_construction_exempt(rel):
            continue
        tree = _safe_parse(path)
        if tree is None:
            continue
        if not _file_imports_intent_contract(tree):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_run_intent = (isinstance(func, ast.Name) and func.id == "RunIntent") or (
                isinstance(func, ast.Attribute) and func.attr == "RunIntent"
            )
            if not is_run_intent:
                continue
            out.append(
                Finding(
                    path=str(path),
                    line=getattr(node, "lineno", 0),
                    col=getattr(node, "col_offset", 0),
                    kind="intent_construction_outside_adapters",
                    message=(
                        "RunIntent(...) constructed outside "
                        "lca/application/runtime/adapters/ + default_facade.py "
                        "(ADR-0199 §10 I-HPC-1). Surface adapters must "
                        "translate wire formats to RunIntent."
                    ),
                )
            )
    return out


# ── run audits + bucketize ──────────────────────────────────


@dataclass(frozen=True)
class Violation:
    audit_kind: str
    v_constraint: str  # V1 / V3 / V4 / V5 / HPC-L2 / I-HPC-1
    path: str
    line: int
    col: int
    kind: str
    message: str
    owner_pr: str
    rationale: str


def _make_violation(audit_kind: str, v_constraint: str, f: Finding) -> Violation:
    """Wrap a Finding with the audit kind + owner attribution."""
    rel = str(Path(f.path).relative_to(_REPO)) if Path(f.path).is_absolute() else f.path
    owner_pr, rationale = _resolve_owner(audit_kind, rel)
    return Violation(
        audit_kind=audit_kind,
        v_constraint=v_constraint,
        path=f.path,
        line=f.line,
        col=f.col,
        kind=f.kind,
        message=f.message,
        owner_pr=owner_pr,
        rationale=rationale,
    )


def collect_violations() -> list[Violation]:
    """Run all PR-0 audits + ADR-0199 P1-14 audits and return one entry
    per finding with owner.

    The audit submodules live at ``lca.harness.diagnostics.audit.<name>``;
    the package ``__init__.py`` is bare (auto-created by
    ``split_oversized_directories``) so we import each scan function
    explicitly from its submodule.
    """
    from lca.harness.diagnostics.audit import control_surface as audit_control_surface
    from lca.harness.diagnostics.audit import direct_commands as audit_direct_commands
    from lca.harness.diagnostics.audit import hook_attach as audit_hook_attach
    from lca.harness.diagnostics.audit import state_writers as audit_state_writers

    body_roots = [
        _REPO / "lca" / "cognition" / "body",
        _REPO / "lca" / "plugins" / "body",
    ]
    layer_roots = [
        _REPO / "lca" / "cognition",
        _REPO / "lca" / "runtime",
        _REPO / "lca" / "agent",
    ]
    profile_roots = [_REPO / "lca" / "plugins", _REPO / "bundles", _REPO / "profiles"]

    out: list[Violation] = []

    # V1 control-surface
    findings = audit_control_surface.scan_control_surface(profile_roots)
    for _key, slot_findings in findings.items():
        for f in slot_findings:
            if f.kind != "retired_control_metadata":
                continue
            out.append(_make_violation("control_surface", "V1", f))

    # V3 state-writers (skipping allowlisted reducer)
    findings = audit_state_writers.scan_state_writers(layer_roots)
    for f in findings:
        out.append(_make_violation("state_writers", "V3", f))

    # V4 direct-commands
    findings = audit_direct_commands.scan_direct_commands(body_roots)
    for f in findings:
        out.append(_make_violation("direct_commands", "V4", f))

    # V5 hook-attach
    findings = audit_hook_attach.scan_hook_attach([*layer_roots, _REPO / "lca" / "application"])
    for f in findings:
        out.append(_make_violation("hook_attach", "V5", f))

    # ADR-0199 P1-14 HPC-L2: facade_bypass
    for f in _scan_facade_bypass(_REPO):
        out.append(_make_violation("facade_bypass", "HPC-L2", f))

    # ADR-0199 P1-14 I-HPC-1: intent construction outside adapters
    for f in _scan_intent_construction_outside_adapters(_REPO):
        out.append(_make_violation("intent_construction_outside_adapters", "I-HPC-1", f))

    return out


def _violations_per_owner(violations: Sequence[Violation]) -> dict[str, list[Violation]]:
    bucket: dict[str, list[Violation]] = {}
    for v in violations:
        bucket.setdefault(v.owner_pr, []).append(v)
    return bucket


def _violations_per_kind(violations: Sequence[Violation]) -> dict[str, list[Violation]]:
    bucket: dict[str, list[Violation]] = {}
    for v in violations:
        bucket.setdefault(v.audit_kind, []).append(v)
    return bucket


def _format_human(violations: list[Violation]) -> str:
    if not violations:
        return (
            "✓ all PR-0 + ADR-0199 P1-14 audit baselines at 0 — no historical migration needed.\n"
        )

    by_owner = _violations_per_owner(violations)
    by_kind = _violations_per_kind(violations)
    total = len(violations)
    lines = [f"Historical migration plan: {total} baseline violation(s)"]
    lines.append("  generated by scripts/route_legacy_patterns.py")
    lines.append(
        "  audits: V1 control-surface + V3 state-writers + V4 direct-commands + "
        "V5 hook-attach + HPC-L2 facade_bypass + I-HPC-1 intent_construction_outside_adapters"
    )
    lines.append("")
    for audit_kind in sorted(by_kind):
        items = by_kind[audit_kind]
        lines.append(f"[{audit_kind}] {len(items):>4d} finding(s)")
        for v in items:
            rel = str(Path(v.path).relative_to(_REPO)) if Path(v.path).is_absolute() else v.path
            lines.append(f"          {rel}:{v.line}  [{v.owner_pr}]  {v.message}")
    lines.append("")
    lines.append("By owner PR:")
    for owner_pr in sorted(by_owner):
        items = by_owner[owner_pr]
        rationale = items[0].rationale
        kinds_str = ", ".join(
            f"{k}={n}" for k, n in sorted(Counter(v.audit_kind for v in items).items())
        )
        lines.append(f"[{owner_pr}] {len(items):>4d} finding(s)  ({kinds_str})")
        lines.append(f"          → {rationale}")
    return "\n".join(lines) + "\n"


def _format_markdown(violations: list[Violation]) -> str:
    """Render the markdown table the tracker §"历史迁移路线图"段 consumes."""
    if not violations:
        return "_无违规基线_"
    by_owner = _violations_per_owner(violations)
    lines = ["| Owner PR | 数量 | 违规类型分布 | 路由理由 |", "|---|:-:|---|---|"]
    for owner_pr in sorted(by_owner):
        items = by_owner[owner_pr]
        by_kind: Counter[str] = Counter(v.audit_kind for v in items)
        kinds_str = ", ".join(f"{k}={n}" for k, n in sorted(by_kind.items()))
        rationale = items[0].rationale
        lines.append(f"| **{owner_pr}** | {len(items)} | {kinds_str} | {rationale} |")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route legacy pattern violations to PR owners.")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Emit canonical JSON")
    parser.add_argument("--md", dest="as_md", action="store_true", help="Emit markdown table")
    args = parser.parse_args(argv)

    violations = collect_violations()

    if args.as_json:
        by_kind = _violations_per_kind(violations)
        # Pre-seed every registered audit kind with an empty list so the
        # JSON contract is stable (downstream consumers can always
        # index ``by_kind[<kind>]`` without ``.get`` + None handling).
        for registered_kind in _OWNER_TABLE:
            by_kind.setdefault(registered_kind, [])
        payload = {
            "total": len(violations),
            "by_kind": {
                kind: [
                    {
                        "audit_kind": v.audit_kind,
                        "v_constraint": v.v_constraint,
                        "path": v.path,
                        "line": v.line,
                        "col": v.col,
                        "kind": v.kind,
                        "message": v.message,
                        "owner_pr": v.owner_pr,
                    }
                    for v in items
                ]
                for kind, items in by_kind.items()
            },
            "by_owner": {
                owner: [
                    {
                        "audit_kind": v.audit_kind,
                        "v_constraint": v.v_constraint,
                        "path": v.path,
                        "line": v.line,
                        "col": v.col,
                        "kind": v.kind,
                        "message": v.message,
                    }
                    for v in items
                ]
                for owner, items in _violations_per_owner(violations).items()
            },
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
        return 0

    if args.as_md:
        sys.stdout.write(_format_markdown(violations))
        sys.stdout.write("\n")
        return 0

    sys.stdout.write(_format_human(violations))
    return 0


if __name__ == "__main__":
    sys.exit(main())
