#!/usr/bin/env python3
"""ADR-0183 事件总线迁移状态审计 —— 只读,不改任何文件。

打印各不变量当前落地状态:
- I-FW-SSOT-1:``events.jsonl`` legacy 残留计数(目标 0)
- I-FW-SSOT-2:``RunStatus`` / ``JournalRunStatus`` 双类计数(目标 1)
- ``EventMechanism`` 迁移进度计数(基线参考)
- PR-5:``_build_event_record`` 旧入口残留(目标 0)+ ``build_record`` 新入口
- EventBus 骨架模块 / Pipeline 装载点 / 鉴权矩阵 yaml 存在性

12 PR 落地态见 docs/adr/0183 §5.2 与 docs/notes/implemented/runbook/2026-09-03-event-bus-pr-matrix.md §B.1。
PR 全部合入但部分 grep 仍未归零(详见附录 B §B.2 验收行)。

风格参考 ``scripts/audit_adr_health.py``:纯标准库,人类可读表格 + ``--json``。
用法::

    python scripts/event_bus_status.py [--json]

退出码恒为 0;状态列是迁移进度提示,不是门禁。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCAN_SUFFIXES = {".py", ".yaml", ".yml"}
_SKIP_DIRS = {"__pycache__", ".git", "node_modules", ".venv"}


@dataclass
class CheckResult:
    """单项审计结果。"""

    id: str
    invariant: str
    observed: int | bool
    expected: str
    status: str  # ok / pending / info / missing
    hits: list[str] = field(default_factory=list)


def _iter_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix not in _SCAN_SUFFIXES:
                continue
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
    return files


def count_matches(pattern: str, roots: list[Path]) -> tuple[int, list[str]]:
    """等价 ``rg -c <pattern> <roots>`` 的行计数(按文件聚合)。"""
    rx = re.compile(pattern)
    total = 0
    hits: list[str] = []
    for path in _iter_files(roots):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n = sum(1 for line in text.splitlines() if rx.search(line))
        if n:
            total += n
            hits.append(f"{path.relative_to(_ROOT)}:{n}")
    return total, hits


def check_ssot1_legacy() -> CheckResult:
    total, hits = count_matches(r"events\.jsonl", [_ROOT / "lca", _ROOT / "lca_kernel"])
    return CheckResult(
        id="ssot1-events-jsonl-legacy",
        invariant="I-FW-SSOT-1 事实链单写 <run_id>.spine.jsonl",
        observed=total,
        expected="0(legacy events.jsonl 全清)",
        status="ok" if total == 0 else "pending",
        hits=hits,
    )


def check_ssot2_run_status() -> CheckResult:
    total, hits = count_matches(r"class RunStatus\b|class JournalRunStatus\b", [_ROOT / "lca"])
    return CheckResult(
        id="ssot2-run-status-classes",
        invariant="I-FW-SSOT-2 run 状态单类",
        observed=total,
        expected="1(双类合一)",
        status="ok" if total == 1 else "pending",
        hits=hits,
    )


def check_mechanism_migration() -> CheckResult:
    total, hits = count_matches(r"EventMechanism", [_ROOT / "lca", _ROOT / "lca_kernel"])
    return CheckResult(
        id="eventmechanism-migration",
        invariant="ADR-0183 迁移进度(旧机制引用基线)",
        observed=total,
        expected="info(随 PR 递减;kernel events/mechanism.py 删除前 >0)",
        status="info",
        hits=hits,
    )


def check_pr5_old_builder() -> CheckResult:
    total, hits = count_matches(r"_build_event_record", [_ROOT / "lca"])
    return CheckResult(
        id="pr5-old-build-record",
        invariant="PR-5 旧 _build_event_record 入口清零",
        observed=total,
        expected="0(吸收进 build_record)",
        status="ok" if total == 0 else "pending",
        hits=hits,
    )


def check_pr5_new_entry() -> CheckResult:
    total, hits = count_matches(r"\bbuild_record\b", [_ROOT / "lca_kernel" / "events"])
    return CheckResult(
        id="pr5-new-build-record",
        invariant="PR-5 统一 record 构造入口存在",
        observed=total,
        expected=">0(spine_runtime.build_record)",
        status="ok" if total > 0 else "missing",
        hits=hits,
    )


def check_modules() -> CheckResult:
    required = [
        _ROOT / "lca_kernel" / "events" / "bus.py",
        _ROOT / "lca_kernel" / "events" / "hooks.py",
        _ROOT / "lca_kernel" / "events" / "pipeline.py",
        _ROOT / "lca_kernel" / "events" / "reader.py",
        _ROOT / "lca_kernel" / "events" / "spine_runtime.py",
        _ROOT / "lca_kernel" / "events" / "sinks" / "spine_sink.py",
    ]
    missing = [str(p.relative_to(_ROOT)) for p in required if not p.exists()]
    return CheckResult(
        id="eventbus-skeleton-modules",
        invariant="EventBus 骨架模块齐备",
        observed=not missing,
        expected="6 模块全在",
        status="ok" if not missing else "missing",
        hits=missing,
    )


def check_pipeline_mount() -> CheckResult:
    total, hits = count_matches(r"register_pipeline", [_ROOT / "lca", _ROOT / "lca_kernel"])
    config_yamls = sorted(
        str(p.relative_to(_ROOT))
        for p in (_ROOT / "lca_kernel" / "events" / "config").rglob("*.yaml")
    )
    return CheckResult(
        id="pipeline-mount-points",
        invariant="Pipeline 装载点(register_pipeline 调用 + 鉴权矩阵 yaml)",
        observed=total,
        expected=f"info(定义在 bus.py;yaml={len(config_yamls)} 个)",
        status="ok" if total > 0 and config_yamls else "pending",
        hits=[*hits, *config_yamls],
    )


_ALL_CHECKS = (
    check_ssot1_legacy,
    check_ssot2_run_status,
    check_mechanism_migration,
    check_pr5_old_builder,
    check_pr5_new_entry,
    check_modules,
    check_pipeline_mount,
)


def run_checks() -> list[CheckResult]:
    return [check() for check in _ALL_CHECKS]


def render_table(results: list[CheckResult]) -> str:
    lines = [
        "ADR-0183 事件总线迁移状态",
        "",
        f"{'CHECK':<30} {'STATUS':<8} {'OBSERVED':<9} EXPECTED",
        f"{'-' * 30} {'-' * 8} {'-' * 9} {'-' * 40}",
    ]
    for r in results:
        observed = str(r.observed)
        lines.append(f"{r.id:<30} {r.status:<8} {observed:<9} {r.expected}")
        for hit in r.hits[:8]:
            lines.append(f"    {hit}")
        if len(r.hits) > 8:
            lines.append(f"    … 余 {len(r.hits) - 8} 项")
    lines += [
        "",
        "目标态:events.jsonl legacy = 0;RunStatus 类 = 1;_build_event_record = 0。",
        "本脚本只读;状态为迁移进度提示,不是门禁。12 PR 落地态由 commit hash 见 docs/adr/0183 §5.2 与附录 B §B.1。",
    ]
    return "\n".join(lines)


def render_json(results: list[CheckResult]) -> str:
    return json.dumps(
        [
            {
                "id": r.id,
                "invariant": r.invariant,
                "observed": r.observed,
                "expected": r.expected,
                "status": r.status,
                "hits": r.hits,
            }
            for r in results
        ],
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADR-0183 事件总线迁移状态审计(只读)")
    parser.add_argument("--json", action="store_true", help="输出 JSON(给 agent 消费)")
    args = parser.parse_args(argv)
    results = run_checks()
    print(render_json(results) if args.json else render_table(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
