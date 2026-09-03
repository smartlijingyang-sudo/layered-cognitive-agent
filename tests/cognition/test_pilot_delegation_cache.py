"""ADR-0179 试点：delegation_cache 业务方迁移回归测试。

覆盖：
- sender 未 boot 时 cached_delegation_observation 不抛异常、返回正常 Observation；
- sender 已 boot 时业务方一行 publish() 走 v2 协议（消费者收到 typed payload）。
"""

from __future__ import annotations

from lca.cognition.body.delegation_cache import cached_delegation_observation
from lca.contracts.atoms.ids import new_id
from lca.contracts.event_v2 import (
    DelegationCacheHit,
    Event,
    EventCategory,
    EventRef,
)
from lca.contracts.models.core.decision import DelegationSpec, Observation
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.delegation import DelegationResult
from lca.plugins.events.consumer_registry import ConsumerRegistry
from lca.plugins.events.router import EventRouterImpl
from lca.plugins.events.sender import EventSenderImpl, set_active_sender


class _CaptureConsumer:
    def __init__(self) -> None:
        self.events: list[tuple[Event, EventRef]] = []

    @property
    def categories(self):
        return frozenset({EventCategory.TEAM_DELEGATION})

    def on_event(self, event, ref):
        self.events.append((event, ref))


def _state_with_hit_result(
    state: AgentState, role: str = "analyst", subtask: str = "汇总"
) -> AgentState:
    """构造一个 team_awareness 已有命中结果的 state。"""
    from datetime import datetime, timezone

    from lca.contracts.models.team.team_awareness import TeamAwareness

    awareness = TeamAwareness(
        results=(
            DelegationResult(
                result_id=new_id("res"),
                target_role=role,
                subtask=subtask,
                output="done",
                success=True,
                error=None,
                task_id=new_id("task"),
                step=0,
                returned_at=datetime.now(tz=timezone.utc),
            ),
        )
    )
    from dataclasses import replace

    return replace(state, team_awareness=awareness, step=3)


def _state() -> AgentState:
    # AgentState 是 dataclass（不是 pydantic），用 dataclasses.replace 构造。
    return AgentState(trace_id="t-1", task="汇总", budget=Budget())


def test_cached_delegation_observation_silent_when_sender_not_installed() -> None:
    """sender 未 boot：业务方调 cached_delegation_observation 走 v2 协议，静默 no-op。"""
    set_active_sender(None)
    state = _state_with_hit_result(_state())
    spec = DelegationSpec(target_role="analyst", subtask="汇总")
    observation = cached_delegation_observation(spec, state)
    assert isinstance(observation, Observation)
    assert observation.success is True


def test_cached_delegation_observation_returns_none_when_no_hit() -> None:
    """无命中：不发事件，返回 None。"""
    set_active_sender(None)
    state = _state()
    spec = DelegationSpec(target_role="analyst", subtask="汇总")
    observation = cached_delegation_observation(spec, state)
    assert observation is None


def test_business_caller_one_line_publish() -> None:
    """业务方 1 行 publish(pydantic payload) → 消费者收到 typed Event。"""
    reg = ConsumerRegistry()
    capture = _CaptureConsumer()
    reg.register(capture)
    sender = EventSenderImpl(EventRouterImpl(reg), dual_write_legacy=False)
    set_active_sender(sender)
    try:
        state = _state_with_hit_result(_state())
        spec = DelegationSpec(target_role="analyst", subtask="汇总")
        cached_delegation_observation(spec, state)
    finally:
        set_active_sender(None)

    assert len(capture.events) == 1
    event, _ref = capture.events[0]
    assert event.category is EventCategory.TEAM_DELEGATION
    assert isinstance(event.payload, DelegationCacheHit)
    assert event.payload.callee_role == "analyst"
    assert event.payload.subtask_preview == "汇总"
    assert event.payload.step == 3
