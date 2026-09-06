"""RepeatToolCallGate — identical tool+args advisory warnings (DSH repeat-tool-reminder)."""

from __future__ import annotations

import json

from lca.cognition.brain.decision_gates.chained.chained import record_gate_decided
from lca.cognition.brain.decision_gates.loop.fingerprint import tool_call_fingerprint
from lca.cognition.brain.guard.loop_policy import LoopGuardPolicyView, StaticLoopGuardPolicy
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.policy.loop_policy import DEFAULT_LOOP_POLICY, LoopPolicyThresholds
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import DecisionGate
from lca.contracts.protocols.think.loop_guard import LoopGuardPolicy
from lca.infrastructure.session.context.turn_control_reader import (
    consecutive_identical_tool_calls,
    last_observation_success,
)

_GENTLE_REMINDER = (
    "你正在用完全相同的参数重复调用同一工具。请先分析上一次结果，"
    "若任务未完成，请换方法或换参数，不要原样重试。"
)

_FACT_KIND = "repeat_tool_call"


def _preview_arguments(arguments: dict[str, object], *, limit: int) -> str:
    try:
        text = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = repr(arguments)
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _detailed_reminder(
    tool_name: str,
    count: int,
    arguments: dict[str, object],
    *,
    preview_chars: int,
    failed: bool,
) -> str:
    args_preview = _preview_arguments(arguments, limit=preview_chars)
    failed_note = "，且最近调用失败" if failed else ""
    return (
        f"检测到重复工具调用{failed_note}：\n"
        f"- tool: {tool_name}\n"
        f"- consecutive_calls: {count}\n"
        f"- arguments: {args_preview}\n"
        "重复调用未产生新进展。请勿再用相同参数调用该工具；"
        "检查最新结果并选择不同行动、不同参数，或在证据已足够时收口。"
    )


class RepeatToolCallGate(DecisionGate):
    """Warn (not block) on consecutive identical tool+args calls."""

    def __init__(
        self,
        *,
        policy: LoopGuardPolicy | None = None,
        thresholds: LoopPolicyThresholds = DEFAULT_LOOP_POLICY,
        repeat_thresholds: tuple[int, ...] = (3, 5, 8),
        arguments_preview_chars: int = 500,
    ) -> None:
        if policy is not None:
            self._thresholds = policy.thresholds
            self._repeat_thresholds = policy.repeat_thresholds
            self._preview_chars = policy.arguments_preview_chars
        else:
            self._thresholds = thresholds
            self._repeat_thresholds = repeat_thresholds
            self._preview_chars = arguments_preview_chars

    async def enforce(self, state: AgentState, decision: Decision) -> Decision:
        if decision.action_type != ActionType.USE_TOOL or not decision.tool_calls:
            return decision

        tool_call = decision.tool_calls[0]
        fingerprint = tool_call_fingerprint(tool_call)
        consecutive = consecutive_identical_tool_calls(state, fingerprint)
        first_threshold = self._repeat_thresholds[0]
        warn_threshold = self._thresholds.repeat_warn
        trigger_at = max(first_threshold, warn_threshold)
        if consecutive < trigger_at:
            return decision

        last_success = last_observation_success(state)
        failed = bool(last_success is False)
        detailed_threshold = (
            self._repeat_thresholds[1] if len(self._repeat_thresholds) > 1 else trigger_at
        )
        if consecutive >= detailed_threshold:
            message = _detailed_reminder(
                tool_call.tool_name,
                consecutive,
                tool_call.arguments,
                preview_chars=self._preview_chars,
                failed=failed,
            )
        else:
            message = _GENTLE_REMINDER

        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
                tool_name=tool_call.tool_name,
                policy_fact=PolicyFact(
                    kind=_FACT_KIND,
                    message=message,
                    source="repeat_tool_call",
                    extra={"consecutive_calls": consecutive, "fingerprint": fingerprint},
                ),
            ),
        )
        return decision


__all__ = ["RepeatToolCallGate"]
