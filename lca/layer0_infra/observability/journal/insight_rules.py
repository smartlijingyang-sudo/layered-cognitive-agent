"""Insight 规则 —— 纯函数层：聚合摘要 → 洞察发现（ADR-0037）。

每条规则是 ``summary → list[Insight]`` 的纯函数，可脱离运行时单测；
``insight_engine`` 负责聚合 journal 事件成 summary 并在 run 收尾触发规则。
规则注册表数据驱动（新增规则 = 一个函数 + 注册一行，无分支改动）。

Insight 以三元组 ``(kind, summary, detail)`` 表达：
- ``kind``：稳定标识（供过滤/评分）；
- ``summary``：一句话结论（进 Run Card）；
- ``detail``：定位细节（角色/参数/数值）。
"""

from __future__ import annotations

from typing import Any

# ── insight kind（稳定词表）─────────────────────────────
INSIGHT_REDUNDANT_TOOL = "redundant_tool_call"
INSIGHT_CRITICAL_PATH = "critical_path"
INSIGHT_LOOP = "loop_warning"
INSIGHT_COST = "cost_summary"

# ── 阈值（命名常量，禁止魔数）──────────────────────────
_REDUNDANT_MIN_COUNT = 2
"""同 (run, tool, args) 达到该次数即判为冗余调用。"""

_LOOP_REPEAT_THRESHOLD = 3
"""单 run 内同一 action_type 连续出现达到该次数即判为疑似循环。"""

_LOOP_STEP_RATIO = 0.8
"""步数逼近预算的比例阈值（相对于观测到的最大步数上限）。"""

_TOP_SLOWEST = 3
"""cost_summary 附带的最慢调用数。"""

Insight = tuple[str, str, str]


def detect_redundant_tool_calls(summary: dict[str, Any]) -> list[Insight]:
    """同 run 内 (tool_name, arguments) 重复 → 冗余调用（可直接省掉的往返）。"""
    counts: dict[tuple[str, str, str], int] = {}
    for call in summary.get("tool_calls", []):
        key = (call["run_id"], call["tool_name"], call["arguments"])
        counts[key] = counts.get(key, 0) + 1
    out: list[Insight] = []
    for (run_id, tool_name, arguments), count in counts.items():
        if count >= _REDUNDANT_MIN_COUNT:
            role = summary.get("runs", {}).get(run_id, {}).get("role", run_id)
            out.append(
                (
                    INSIGHT_REDUNDANT_TOOL,
                    f"{role} 重复调用 {tool_name} ×{count}",
                    f"arguments={arguments}",
                )
            )
    return out


def detect_loop(summary: dict[str, Any]) -> list[Insight]:
    """单 run 内同一 action 连续重复 → 疑似循环（步数空转）。"""
    out: list[Insight] = []
    for run_id, actions in summary.get("actions", {}).items():
        run_count = 0
        prev = None
        for action in actions:
            run_count = run_count + 1 if action == prev else 1
            prev = action
            if run_count >= _LOOP_REPEAT_THRESHOLD:
                role = summary.get("runs", {}).get(run_id, {}).get("role", run_id)
                out.append(
                    (
                        INSIGHT_LOOP,
                        f"{role} 疑似循环：{action} 连续 {run_count} 次",
                        f"run_id={run_id}",
                    )
                )
                break
    return out


def detect_critical_path(summary: dict[str, Any]) -> list[Insight]:
    """耗时最长的 run = 关键路径（优化它收益最大）。"""
    runs = summary.get("runs", {})
    slowest_run = None
    slowest_ms = 0
    for run_id, info in runs.items():
        duration_ms = int((info.get("end_ts", 0) - info.get("start_ts", 0)) * 1000)
        if duration_ms > slowest_ms:
            slowest_ms = duration_ms
            slowest_run = (run_id, info)
    if slowest_run is None or slowest_ms <= 0:
        return []
    run_id, info = slowest_run
    return [
        (
            INSIGHT_CRITICAL_PATH,
            f"关键路径：{info.get('role', run_id)} 耗时 {slowest_ms}ms",
            f"steps={info.get('steps', 0)}",
        )
    ]


def summarize_cost(summary: dict[str, Any]) -> list[Insight]:
    """LLM 调用次数 / token 汇总（按 model），附最慢 top-N。"""
    calls = summary.get("llm_calls", [])
    if not calls:
        return []
    total_in = sum(c.get("prompt_tokens", 0) for c in calls)
    total_out = sum(c.get("completion_tokens", 0) for c in calls)
    models = {c.get("model", "?") for c in calls}
    slowest = sorted(calls, key=lambda c: c.get("latency_ms", 0), reverse=True)[:_TOP_SLOWEST]
    slowest_desc = ", ".join(f"{c.get('model', '?')} {c.get('latency_ms', 0)}ms" for c in slowest)
    return [
        (
            INSIGHT_COST,
            f"LLM {len(calls)} 次调用 · tokens {total_in} in / {total_out} out",
            f"models={', '.join(sorted(models))} · slowest: {slowest_desc}",
        )
    ]


#: 规则注册表（数据驱动；新增规则追加一行即可）
INSIGHT_RULES: tuple[Any, ...] = (
    detect_redundant_tool_calls,
    detect_loop,
    detect_critical_path,
    summarize_cost,
)


def run_all_rules(summary: dict[str, Any]) -> list[Insight]:
    out: list[Insight] = []
    for rule in INSIGHT_RULES:
        out.extend(rule(summary))
    return out
