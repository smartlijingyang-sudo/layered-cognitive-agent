"""ADR-0248 gated 模式全流程测试（真实 runtime loop 驱动）。

通过 ``CognitiveRuntime.run`` 以 ``vocal_mode="gated"`` 跑完一个完整 Run，
用 mock driver 模拟模型行为：
1. 普通内省文本经 GatedVocalGate 截流，绝不进入可见气泡；
2. 模型调用 send_message 投递正式结果；
3. Settle 硬闸在交付后正常收敛（run 返回 COMPLETED）；
4. InitiativeHook 在提供 transcript_features 时真实触发并写入
   ``Result.extra["initiative_offer"]``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.run.context import RunContext
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeLifecycleEvent,
)
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool import SendMessageTool
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.runtime.loop.runtime_loop import CognitiveRuntime
from lca.session.append import Session


@dataclass
class _RecordingSubscriber:
    events: list[RuntimeLifecycleEvent] = field(default_factory=list)

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        self.events.append(event)


class _GatedMockDriver:
    """模拟模型行为：gated 模式先内省截流再调 send_message；direct 直通。"""

    def __init__(
        self,
        captured_states: list[AgentState],
        gate: GatedVocalGate | None,
    ) -> None:
        self.captured_states = captured_states
        self.gate = gate

    async def run(self, state: AgentState) -> Result:
        self.captured_states.append(state)
        output = "直接回答"
        if self.gate is not None:
            # 1. 模型普通文本 → 截流进 scratchpad，用户不可见
            self.gate.handle_text_chunk("Internal scratchpad: 正在计算配置差异...")
            # 2. 唯一声道投递正式气泡
            SendMessageTool(self.gate).execute(type="text", content="已完成配置排查。")
            output = "已完成配置排查。"
        return Result(
            trace_id=state.trace_id,
            status=TaskStatus.COMPLETED,
            final_state_ref=state.trace_id,
            total_steps=1,
            budget_used=Budget(),
            output=output,
        )


class _Bindings:
    """CognitiveRuntime 的最小 bindings 桩：捕获 vocal_gate 供 driver 使用。"""

    def __init__(self, captured_states: list[AgentState]) -> None:
        self.lifecycle_publisher = _RecordingSubscriber()
        self.capabilities: dict[str, Any] = {}
        self.captured_states = captured_states
        self.reducer = MagicMock()
        self._gate: GatedVocalGate | None = None

    def plan_ref(self) -> str:
        return "plan://gated-flow"

    def require_executable_plan(self) -> None:
        pass

    def with_writer(self, writer: Any) -> _Bindings:
        self.capabilities["writer"] = writer
        return self

    def with_vocal_gate(self, vocal_gate: Any) -> _Bindings:
        self.capabilities["vocal_gate"] = vocal_gate
        self._gate = cast("GatedVocalGate", vocal_gate)
        return self

    def new_driver(self) -> _GatedMockDriver:
        return _GatedMockDriver(self.captured_states, self._gate)

    def new_state(
        self,
        *,
        trace_id: str,
        task: str,
        budget: Budget,
        agent_role: str,
        from_role: str,
        team_awareness: Any,
    ) -> AgentState:
        return AgentState(
            trace_id=trace_id,
            task=task,
            budget=budget,
            agent_role=agent_role,
            from_role=from_role,
            team_awareness=team_awareness,
        )


@pytest.mark.asyncio
async def test_gated_run_flow_intercepts_delivers_and_fires_initiative() -> None:
    session = Session("test-gated-flow")
    set_publish_session(cast("Any", session))

    captured_states: list[AgentState] = []
    bindings = _Bindings(captured_states)
    runtime = CognitiveRuntime(cast("Any", bindings))

    ctx = RunContext(
        trace_id="trace-gated-flow",
        session_id="s1",
        extra={
            "vocal_mode": "gated",
            "transcript_features": {"manual_action_counts": {"fetch_weather": 3}},
        },
    )

    try:
        result = await runtime.run(task="帮我排查环境配置", ctx=ctx)
    finally:
        reset_publish_session(None)

    # 1. Run 正常收敛（Settle 硬闸通过）
    assert result.status == TaskStatus.COMPLETED

    # 2. 门控声带已注入并工作：内省文本不进气泡，只有 send_message 交付
    gate = bindings.capabilities["vocal_gate"]
    assert isinstance(gate, GatedVocalGate)
    visible = gate.get_visible_outputs()
    assert [v["content"] for v in visible] == ["已完成配置排查。"]
    assert "Internal scratchpad" not in [v["content"] for v in visible]

    # 3. InitiativeHook 真实触发，offer 写入 Result.extra
    offer = result.extra.get("initiative_offer")
    assert offer is not None
    assert offer["signal"] == "repeated_manual"
    assert "例程" in offer["nudge_message"]


@pytest.mark.asyncio
async def test_direct_mode_flow_keeps_classic_passthrough() -> None:
    """direct（默认）模式零退化：不注入门控，run 照常完成。"""
    session = Session("test-direct-flow")
    set_publish_session(cast("Any", session))

    captured_states: list[AgentState] = []
    bindings = _Bindings(captured_states)
    runtime = CognitiveRuntime(cast("Any", bindings))

    ctx = RunContext(trace_id="trace-direct-flow", session_id="s2")

    try:
        result = await runtime.run(task="直接回答", ctx=ctx)
    finally:
        reset_publish_session(None)

    assert result.status == TaskStatus.COMPLETED
    assert "vocal_gate" not in bindings.capabilities
    assert "initiative_offer" not in result.extra


@pytest.mark.asyncio
async def test_profile_runtime_to_gated_run_full_chain() -> None:
    """profile.json.runtime → RunContext.extra → gated run 全链路。

    用 ``run_context_for_session`` 模拟 web carrier 读取 assistant
    ``profile_runtime={"vocal_mode": "gated"}``，再驱动真实 runtime loop，
    验证配置通道到门控行为整条链路生效。
    """
    from dataclasses import dataclass as _dataclass
    from dataclasses import field as _field

    from lca.plugins.transport.webserver.carrier.runs.lifecycle.run_context_factory import (
        run_context_for_session,
    )

    @_dataclass
    class _AgentStub:
        agent_id: str = "agt_gated_profile"
        name: str = "Gated Assistant"

    @_dataclass
    class _SessionStub:
        agent: _AgentStub = _field(default_factory=_AgentStub)
        prior_turns: tuple[Any, ...] = ()

    session = Session("test-profile-gated-chain")
    set_publish_session(cast("Any", session))

    captured_states: list[AgentState] = []
    bindings = _Bindings(captured_states)
    runtime = CognitiveRuntime(cast("Any", bindings))

    ctx = run_context_for_session(
        _SessionStub(),  # type: ignore[arg-type]
        profile_runtime={"vocal_mode": "gated"},
    )

    try:
        result = await runtime.run(task="按配置走 Grok 模式", ctx=ctx)
    finally:
        reset_publish_session(None)

    assert result.status == TaskStatus.COMPLETED
    assert ctx.extra["vocal_mode"] == "gated"
    gate = bindings.capabilities["vocal_gate"]
    assert isinstance(gate, GatedVocalGate)
    assert [v["content"] for v in gate.get_visible_outputs()] == ["已完成配置排查。"]


@pytest.mark.asyncio
async def test_runtime_loop_reuses_carrier_gate_instance() -> None:
    """runtime loop 复用 carrier 在 bindings 中发布的 gate，不新建实例。

    确保 body 的 send_message 投递与 settle 结算使用同一门控对象。
    """
    from lca.infrastructure.runtime_plane.capability_bindings import (
        BindingsViewBuilder,
        reset_capability_bindings,
        set_capability_bindings,
    )
    from lca.infrastructure.vocal.gate import GatedVocalGate

    session = Session("test-gate-reuse")
    set_publish_session(cast("Any", session))

    captured_states: list[AgentState] = []
    bindings = _Bindings(captured_states)
    runtime = CognitiveRuntime(cast("Any", bindings))

    shared_gate = GatedVocalGate("op_shared")
    token = set_capability_bindings(BindingsViewBuilder(vocal_mode="gated", vocal_gate=shared_gate))
    ctx = RunContext(trace_id="trace-gate-reuse", session_id="s3")

    try:
        result = await runtime.run(task="共享 gate 测试", ctx=ctx)
    finally:
        reset_capability_bindings(token)
        reset_publish_session(None)

    assert result.status == TaskStatus.COMPLETED
    used_gate = bindings.capabilities.get("vocal_gate")
    assert used_gate is shared_gate
    assert [v["content"] for v in shared_gate.get_visible_outputs()] == ["已完成配置排查。"]
