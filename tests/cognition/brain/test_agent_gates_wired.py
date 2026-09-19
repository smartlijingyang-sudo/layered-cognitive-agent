"""PR-5: the composed Brain must expose the profile-selected agent gates.

``SimpleBrainFactory`` accepts an ``agent_gate_factory`` so the assembled
``ModularBrain`` carries a non-null ``agent_gates`` chain — the same chain
``concept.decision.enforce`` reads from ``runtime.brain.agent_gates``.
Profiles without an assembled gate chain keep ``agent_gates=None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.cognition.brain.decision_gates.chained.chained import ChainedDecisionGate
from lca.cognition.brain.decision_gates.tool.loop_breaker import ToolLoopBreakerGate
from lca.cognition.brain.pipeline.default_factory import SimpleBrainFactory
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    ToolCall,
    Turn,
)
from lca.contracts.models.core.policy.loop_policy import LoopPolicyThresholds
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest


@dataclass
class _Reasoner:
    llm: Any
    selector: Any = None
    template_provider: Any = None
    section_registry: Any = None


class _ThinkPipeline:
    async def decide(self, **kwargs: Any) -> Any:
        raise NotImplementedError


class _ReflectionPipeline:
    async def reflect(self, **kwargs: Any) -> Any:
        raise NotImplementedError


def _profile() -> RoleProfile:
    return RoleProfile(
        role="助手",
        goal="帮助用户完成日常任务",
        backstory="我是 LobeHub 助手.",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _factory(
    agent_gate_factory: Any = None,
) -> SimpleBrainFactory:
    return SimpleBrainFactory(
        agent_gate_factory=agent_gate_factory,
        classifier=object(),  # type: ignore[arg-type]
        critic_factory=lambda: object(),
        reasoner_cls=_Reasoner,  # type: ignore[arg-type]
        think_pipeline=_ThinkPipeline(),  # type: ignore[arg-type]
        reflection_pipeline=_ReflectionPipeline(),  # type: ignore[arg-type]
    )


def _build_brain(agent_gate_factory: Any = None) -> Any:
    return _factory(agent_gate_factory)(
        object(),
        _profile(),
        object(),
        tools=[],
        template_provider=None,
    )


def test_brain_exposes_agent_gates() -> None:
    chain = ChainedDecisionGate(ToolLoopBreakerGate())
    brain = _build_brain(agent_gate_factory=lambda: chain)

    assert brain.agent_gates is chain


def test_brain_without_agent_gate_factory_keeps_agent_gates_none() -> None:
    brain = _build_brain()

    assert brain.agent_gates is None


def _state_with_stalled_turns() -> AgentState:
    """Three identical successful ``readFile`` turns, newest first semantics."""
    state = AgentState(
        trace_id="trace-stalled",
        task="test-task",
        budget=Budget(max_steps=100),
    )
    turns: list[Turn] = []
    for i in range(3):
        decision = Decision(
            decision_id=f"dec-{i}",
            action_type=ActionType.USE_TOOL,
            rationale="read",
            confidence=0.9,
            tool_calls=[
                ToolCall(
                    call_id=f"call-{i}",
                    tool_name="readFile",
                    arguments={"path": "data.txt"},
                )
            ],
        )
        observation = Observation(
            observation_id=f"obs-{i}",
            success=True,
            payload={"content": "same"},
        )
        turns.append(Turn(decision=decision, observation=observation))
    state.control_turns = turns
    return state


def _stalled_candidate() -> Decision:
    return Decision(
        decision_id="dec-candidate",
        action_type=ActionType.USE_TOOL,
        rationale="read",
        confidence=0.9,
        tool_calls=[
            ToolCall(
                call_id="call-candidate",
                tool_name="readFile",
                arguments={"path": "data.txt"},
            )
        ],
    )


@pytest.mark.asyncio
async def test_stalled_success_breaks_loop() -> None:
    chain = ChainedDecisionGate(
        ToolLoopBreakerGate(thresholds=LoopPolicyThresholds(break_stalled=3))
    )
    state = _state_with_stalled_turns()

    out = await chain.enforce(state, _stalled_candidate())

    assert out.action_type == ActionType.RESPOND
    assert out.degraded_from == ActionType.USE_TOOL
    assert "相同参数" in out.response_text
