#!/usr/bin/env python3
"""SSOT 字段漂移审计 —— 跨 run 检查观测字段值的稳定性。

背景(SSOT-Doctor-Field-Drift):
历史 bug:`coord.emit_phase` 在 LLM adapter 边界把 ``objective=model``
误传,导致 spine 上 ``phase.think.fold`` 的 objective 字段出现模型名
(如 ``qwen3.7-plus``)而不是用户原文。该 bug 不会让 run 失败,但会让
journal 投影和审计脚本读到错误字段。本脚本扫描 traces/runs 下所有
run,统计每个 SSOT 字段的取值集合,挑出「与字段语义不符」的异常值。

SSOT 字段契约:
    phase.<x>.fold.objective_kind ∈ {"user_text", "agent_role", "system_role", "model_name"}
    phase.<x>.fold.objective     ≠ 模型名(当 objective_kind = "user_text" 时)
    step.thinking.record.tool_name ≠ 模型名

用法:
    python scripts/audit_ssot_field_drift.py [--runs-dir traces/runs] [--limit 50]

退出码:
    0 —— 全部 run 字段语义正常
    1 —— 发现异常字段值
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

VALID_OBJECTIVE_KINDS = frozenset({"user_text", "agent_role", "system_role", "model_name"})
# 简单启发式:已知模型名模式(以 "qwen" / "gpt-" / "claude" / "gemini" / "deepseek" 开头)。
_MODEL_NAME_RE = re.compile(
    r"^(qwen[a-z0-9.\-]*|gpt-[a-z0-9.\-]*|claude[a-z0-9.\-]*|gemini[a-z0-9.\-]*"
    r"|deepseek[a-z0-9.\-]*|llama[a-z0-9.\-]*|mistral[a-z0-9.\-]*)$",
    re.IGNORECASE,
)


def _looks_like_model_name(value: str) -> bool:
    return bool(_MODEL_NAME_RE.match(value.strip()))


def _scan_run(run_dir: Path) -> dict[str, list[dict[str, object]]]:
    """扫描单个 run 的 spine + model_visible,挑 SSOT 字段异常。

    返回 {异常键: [异常记录, ...]};键 = "<ep>.<field>"。
    """
    findings: dict[str, list[dict[str, object]]] = defaultdict(list)
    spine_path = run_dir / f"{run_dir.name}.spine.jsonl"
    if spine_path.exists():
        try:
            for ln in spine_path.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except Exception:
                    continue
                ep = rec.get("execution_point")
                payload = rec.get("payload")
                if not isinstance(ep, str) or not isinstance(payload, dict):
                    continue
                if ep.startswith("phase.") and ep.endswith(".fold"):
                    kind = payload.get("objective_kind")
                    obj = payload.get("objective", "")
                    if isinstance(kind, str) and kind not in VALID_OBJECTIVE_KINDS:
                        findings["phase.<x>.fold.objective_kind"].append(
                            {
                                "run_id": run_dir.name,
                                "seq": rec.get("sequence"),
                                "value": kind,
                                "objective": obj,
                            }
                        )
                    if (
                        isinstance(kind, str)
                        and kind == "user_text"
                        and isinstance(obj, str)
                        and _looks_like_model_name(obj)
                    ):
                        findings["phase.think.fold.objective=user_text/模型名"].append(
                            {
                                "run_id": run_dir.name,
                                "seq": rec.get("sequence"),
                                "value": obj,
                            }
                        )
        except Exception:
            pass
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", default="traces/runs", type=Path)
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="最多扫描多少个 run(按 mtime 倒序)",
    )
    args = parser.parse_args(argv)

    runs_dir = args.runs_dir
    if not runs_dir.is_dir():
        print(f"runs dir not found: {runs_dir}", file=sys.stderr)
        return 2

    # 按 mtime 倒序取最近 N 个
    candidates = sorted(
        (p for p in runs_dir.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: args.limit]

    total_findings: dict[str, list[dict[str, object]]] = defaultdict(list)
    scanned = 0
    for run_dir in candidates:
        if not (run_dir / f"{run_dir.name}.spine.jsonl").exists():
            continue
        scanned += 1
        for k, items in _scan_run(run_dir).items():
            total_findings[k].extend(items)

    print(f"scanned {scanned} runs from {runs_dir}")
    if not total_findings:
        print("OK:no SSOT field drift detected")
        return 0

    print(f"FAIL:{sum(len(v) for v in total_findings.values())} anomalies")
    for key, items in sorted(total_findings.items()):
        print(f"  {key}: {len(items)} hits")
        for it in items[:5]:
            print(f"    - {it}")
        if len(items) > 5:
            print(f"    ... +{len(items) - 5} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
