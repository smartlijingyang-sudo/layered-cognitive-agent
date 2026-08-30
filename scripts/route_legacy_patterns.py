#!/usr/bin/env python3
"""Route legacy code patterns to their delivery PR (ADR-0074 历史迁移)。

PR-0 audit 测量网产生 4 个基线：control-surface / state-writers /
direct-commands / hook-attach。本脚本把这些违规按归属文件路由到 ADR-0074
实施矩阵中的 owner PR，输出人可读的迁移路线图，可被：

- tracker §"历史迁移路线图" 段同步使用
- lca-ops status adr-supervision 子命令展示
- 检查脚本（建议）固定基线是否下降

退出码 0 = 总是返回（无 fail 路径；本脚本只生成迁移建议）

用法：
  uv run python scripts/route_legacy_patterns.py              # human
  uv run python scripts/route_legacy_patterns.py --json       # machine
  uv run python scripts/route_legacy_patterns.py --md         # markdown
"""

from __future__ import annotations

import argparse
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
        ("lca/layer1_cognitive/body/", "PR-7", "CommandEnvelope 收口 + Body.execute 5 闸"),
        ("lca/layer1_cognitive/memory/", "PR-3", "MemoryPolicy / CapabilityPlan 中读写"),
        ("lca/layer1_cognitive/brain/", "PR-4", "ModularBrain / Reasoner 写入"),
        ("lca/layer1_cognitive/skill_router/", "PR-4", "SkillRouter 决策写"),
        ("lca/layer1_cognitive/sensors/", "PR-3", "PerceiveHub / Sensor 收敛"),
        ("lca/layer2_runtime/", "PR-4", "runtime_loop；停止决策由 State 群 StopPolicy 提供"),
        ("lca/layer3_agent/", "PR-4", "Team / DecisionGate"),
    ],
    "direct_commands": [
        ("lca/layer1_cognitive/body/", "PR-7", "Body.execute 必经 envelope"),
        ("lca/plugins/body/", "PR-7", "plugin Body 必须经 SafeExecutor"),
    ],
    "hook_attach": [
        ("lca/layer1_cognitive/", "PR-7", "EventBus / HookMiddleware 收口"),
        ("lca/layer2_runtime/", "PR-7", "runtime_loop 走 envelope"),
        ("lca/layer3_agent/", "PR-7", "Agent / Team 走 envelope"),
        ("lca/layer4_app/", "PR-7", "spawn -> bind_plan 收口"),
    ],
    "control_surface": [
        ("lca/plugins/", "PR-2", "PluginSpec.contributes 声明式控制面"),
        ("bundles/", "PR-2", "禁止重引入 Bundle YAML control"),
        ("profiles/", "PR-2", "禁止重引入 Profile YAML control"),
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


# ── run audits + bucketize ──────────────────────────────────


@dataclass(frozen=True)
class Violation:
    audit_kind: str
    v_constraint: str  # V1 / V3 / V4 / V5
    path: str
    line: int
    col: int
    kind: str
    message: str
    owner_pr: str
    rationale: str


def collect_violations() -> list[Violation]:
    """Run all four PR-0 audits and return one entry per finding with owner."""
    from lca.harness.diagnostics import (
        audit_control_surface,
        audit_direct_commands,
        audit_hook_attach,
        audit_state_writers,
    )

    body_roots = [
        _REPO / "lca" / "layer1_cognitive" / "body",
        _REPO / "lca" / "plugins" / "body",
    ]
    layer_roots = [
        _REPO / "lca" / "layer1_cognitive",
        _REPO / "lca" / "layer2_runtime",
        _REPO / "lca" / "layer3_agent",
    ]
    profile_roots = [_REPO / "lca" / "plugins", _REPO / "bundles", _REPO / "profiles"]

    out: list[Violation] = []

    # V1 control-surface
    findings = audit_control_surface.scan_control_surface(profile_roots)
    for _key, slot_findings in findings.items():
        for f in slot_findings:
            if f.kind != "retired_control_metadata":
                continue
            rel = str(Path(f.path).relative_to(_REPO)) if Path(f.path).is_absolute() else f.path
            owner_pr, rationale = _resolve_owner("control_surface", rel)
            out.append(
                Violation(
                    audit_kind="control_surface",
                    v_constraint="V1",
                    path=f.path,
                    line=f.line,
                    col=f.col,
                    kind=f.kind,
                    message=f.message,
                    owner_pr=owner_pr,
                    rationale=rationale,
                )
            )

    # V3 state-writers (skipping allowlisted reducer)
    findings = audit_state_writers.scan_state_writers(layer_roots)
    for f in findings:
        rel = str(Path(f.path).relative_to(_REPO)) if Path(f.path).is_absolute() else f.path
        owner_pr, rationale = _resolve_owner("state_writers", rel)
        out.append(
            Violation(
                audit_kind="state_writers",
                v_constraint="V3",
                path=f.path,
                line=f.line,
                col=f.col,
                kind=f.kind,
                message=f.message,
                owner_pr=owner_pr,
                rationale=rationale,
            )
        )

    # V4 direct-commands
    findings = audit_direct_commands.scan_direct_commands(body_roots)
    for f in findings:
        rel = str(Path(f.path).relative_to(_REPO)) if Path(f.path).is_absolute() else f.path
        owner_pr, rationale = _resolve_owner("direct_commands", rel)
        out.append(
            Violation(
                audit_kind="direct_commands",
                v_constraint="V4",
                path=f.path,
                line=f.line,
                col=f.col,
                kind=f.kind,
                message=f.message,
                owner_pr=owner_pr,
                rationale=rationale,
            )
        )

    # V5 hook-attach
    findings = audit_hook_attach.scan_hook_attach([*layer_roots, _REPO / "lca" / "layer4_app"])
    for f in findings:
        rel = str(Path(f.path).relative_to(_REPO)) if Path(f.path).is_absolute() else f.path
        owner_pr, rationale = _resolve_owner("hook_attach", rel)
        out.append(
            Violation(
                audit_kind="hook_attach",
                v_constraint="V5",
                path=f.path,
                line=f.line,
                col=f.col,
                kind=f.kind,
                message=f.message,
                owner_pr=owner_pr,
                rationale=rationale,
            )
        )

    return out


def _violations_per_owner(violations: Sequence[Violation]) -> dict[str, list[Violation]]:
    bucket: dict[str, list[Violation]] = {}
    for v in violations:
        bucket.setdefault(v.owner_pr, []).append(v)
    return bucket


def _format_human(violations: list[Violation]) -> str:
    if not violations:
        return "✓ all PR-0 audit baselines at 0 — no historical migration needed.\n"

    by_owner = _violations_per_owner(violations)
    total = len(violations)
    lines = [f"Historical migration plan: {total} baseline violation(s)"]
    lines.append("  generated by scripts/route_legacy_patterns.py")
    lines.append(
        "  audits: V1 control-surface + V3 state-writers + V4 direct-commands + V5 hook-attach"
    )
    lines.append("")
    for owner_pr in sorted(by_owner):
        items = by_owner[owner_pr]
        rationale = items[0].rationale
        by_kind: Counter[str] = Counter(v.audit_kind for v in items)
        kinds_str = ", ".join(f"{k}={n}" for k, n in sorted(by_kind.items()))
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
        payload = {
            "total": len(violations),
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
