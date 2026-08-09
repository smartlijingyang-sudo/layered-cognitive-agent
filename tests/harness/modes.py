"""Shared Team-mode catalog for tests and the run_team_mode CLI (ADR-0052).

Solo/Team 分治后，harness 只保留 "team" 场景 —— solo 是裸模型，不需要
确定性探针。个体协作策略（pipeline/debate/fan_out 等）的测试走
tests/fixtures/team_scenarios/*.yaml + tests/support/scenario_loader.py。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from tests.harness.scripted_llm import ScriptedLLMAdapter, multi_delegate, respond


@dataclass(frozen=True)
class ModeScenario:
    """Human-facing scenario card for a team mode probe."""

    key: str
    title: str
    blurb: str
    cast: tuple[str, ...]
    plan_steps: tuple[str, ...]
    default_objective: str


# key 集合须与 gateway.mode_catalog 一致（见 test_refactor_guards）
_SCENARIOS: dict[str, ModeScenario] = {
    "team": ModeScenario(
        key="team",
        title="Team · 自动组队",
        blurb="Lead 组织全员意见后统一收口（board 治理，确定性探针）。",
        cast=("Lead（主导 · mandate=board）", "Alice（成员）", "Bob（成员）"),
        plan_steps=(
            "1. Lead 发起 board 流程",
            "2. 全员（Alice、Bob）给出意见",
            "3. Lead 综合收口输出决议",
        ),
        default_objective=(
            "董事会场景：是否把客服机器人切换到新模型？"
            "请 Alice 给「支持」理由一句，Bob 给「风险」一句；"
            "Lead 综合后给出最终决议（通过/否决）和一句总结。禁止反问。"
        ),
    ),
}


ALL_MODES: Final[tuple[str, ...]] = tuple(_SCENARIOS.keys())


def get_scenario(mode: str) -> ModeScenario:
    if mode not in _SCENARIOS:
        raise KeyError(f"unknown mode {mode!r}")
    return _SCENARIOS[mode]


def default_objective(mode: str) -> str:
    return get_scenario(mode).default_objective


def format_scenario_card(
    mode: str,
    *,
    track: str,
    objective: str | None = None,
    max_rounds: int | None = None,
) -> str:
    """Banner printed before a run — what scenario, who, planned steps."""
    del max_rounds  # team 模式无 max_rounds 概念
    sc = get_scenario(mode)
    obj = objective if objective is not None else sc.default_objective
    lines = [
        "╔" + "═" * 58 + "╗",
        f"║ 场景  {sc.title:<50} ║",
        f"║ 模式  {mode:<12}  track={track:<10}              ║",
        "╟" + "─" * 58 + "╢",
        f"║ 说明  {sc.blurb}",
        "║ 角色",
    ]
    for c in sc.cast:
        lines.append(f"║   · {c}")
    lines.append("║ 计划步骤（预期）")
    for step in sc.plan_steps:
        lines.append(f"║   {step}")
    lines.append("╟" + "─" * 58 + "╢")
    lines.append("║ 任务目标")
    wrapped = _wrap_text(obj, width=54)
    for w in wrapped:
        lines.append(f"║   {w}")
    lines.append("╚" + "═" * 58 + "╝")
    return "\n".join(lines)


def _wrap_text(text: str, *, width: int) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return [""]
    rows: list[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur = f"{cur} {w}"
        else:
            rows.append(cur)
            cur = w
    rows.append(cur)
    return rows


def scripted_llm_for_mode(mode: str) -> ScriptedLLMAdapter:
    """Deterministic LLM scripts matching tests/harness/runner role names."""
    if mode == "solo":
        return ScriptedLLMAdapter({"助手": [respond("solo done")]}, default_respond=True)
    if mode == "team":
        return ScriptedLLMAdapter(
            {
                "Lead": [
                    multi_delegate([("Alice", "analyze"), ("Bob", "review")]),
                    respond("lead final"),
                ],
                "Alice": [respond("alice view")],
                "Bob": [respond("bob view")],
            },
            default_respond=True,
        )
    raise KeyError(f"unknown mode {mode!r} — only 'solo' and 'team' are supported (ADR-0052)")
