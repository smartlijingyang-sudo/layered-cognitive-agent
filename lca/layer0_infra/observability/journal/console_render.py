"""journal → console 渲染纯函数（场景卡 / 叙事行 / Run Card，ADR-0037）。

与 ``console_projector``（状态聚合 + 分派）分离：本模块全部是无副作用的
str 生成，可直接单测、可被 replay 复用。Run Card 是人类视图的终态形态——
验收标准：未参与者读卡片即可复述 run 做了什么、谁卡住了、花了多少。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.lifecycle import TaskStatus

_CARD_WIDTH = 62


def hr(left: str) -> str:
    """卡片上边框（标题左对齐）。"""
    return f"╭─ {left} " + "─" * max(_CARD_WIDTH - len(left) - 4, 4)


def _card_line(text: str) -> str:
    return f"│ {text}"


def card_bottom() -> str:
    return "╰" + "─" * (_CARD_WIDTH - 1)


def render_scenario_card(info: dict[str, Any]) -> str:
    """run 入口场景卡（team 或 solo）。"""
    scope = info.get("scope", "agent")
    title = info.get("team_id") or info.get("agent_role") or "run"
    lines = [hr("run plan"), _card_line(f"{title} · {info.get('strategy_key', '')}".rstrip(" ·"))]
    if info.get("mandate"):
        lines.append(_card_line(f"mandate: {info['mandate']}"))
    if info.get("lead_role"):
        lines.append(_card_line(f"lead: {info['lead_role']}"))
    if info.get("members"):
        lines.append(_card_line(f"members: {', '.join(info['members'])}"))
    if scope == "agent" and info.get("from_role"):
        lines.append(_card_line(f"from: {info['from_role']}"))
    if info.get("plan_steps"):
        lines.append(_card_line(f"plan: {info['plan_steps']}"))
    if info.get("objective_preview"):
        lines.append(_card_line(f"task: {info['objective_preview']}"))
    lines.append(card_bottom())
    return "\n".join(lines)


def render_run_card(trace: dict[str, Any]) -> str:
    """Run Card：终态汇总（状态/时长/成员贡献/token）。

    洞察由 TraceInspector 按需派生，不再内联渲染到 Run Card。
    """
    identity = trace.get("team_id") or trace.get("title") or "run"
    strategy = trace.get("strategy_key", "")
    status = trace.get("status", "")
    duration_s = trace.get("duration_s", 0.0)
    header = f"{identity}" + (f" · {strategy}" if strategy else "")
    lines = [
        hr("run card"),
        _card_line(f"{header} · {status} · {duration_s:.1f}s · {trace.get('steps', 0)} steps"),
    ]
    for run in trace.get("runs", []):
        lines.append(_card_line(_render_run_line(run)))
    llm = trace.get("llm_calls", 0)
    if llm:
        lines.append(
            _card_line(
                f"llm {llm} calls · tokens {trace.get('tokens_in', 0)} in"
                f" / {trace.get('tokens_out', 0)} out"
            )
        )
    tools = trace.get("tool_calls", 0)
    if tools:
        lines.append(_card_line(f"tool {tools} calls"))
    if trace.get("error"):
        lines.append(_card_line(f"error: {trace['error']}"))
    lines.append(card_bottom())
    return "\n".join(lines)


def _render_run_line(run: dict[str, Any]) -> str:
    mark = "✓" if run.get("status") == TaskStatus.COMPLETED else "✗"
    bits = [f"{run.get('role', '?')} {mark}"]
    if run.get("llm_calls"):
        bits.append(f"{run['llm_calls']} llm")
    if run.get("tool_calls"):
        bits.append(f"{run['tool_calls']} tool")
    if run.get("steps"):
        bits.append(f"{run['steps']} steps")
    if run.get("duration_s") is not None:
        bits.append(f"{run['duration_s']:.1f}s")
    if run.get("synthesis_candidates"):
        bits.append(f"synthesis({run['synthesis_candidates']})")
    if run.get("error"):
        bits.append("error")
    return " · ".join(bits)


def section_header(role: str) -> str:
    return f"\n── {role} ──"
