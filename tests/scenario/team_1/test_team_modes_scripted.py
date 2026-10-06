"""Team mode scripted 测试（ADR-0052）：team 模式跑通 + trace/journal 断言。

个体协作策略（pipeline/debate/fan_out 等）的测试走 edge case 测试和
tests/fixtures/team_scenarios/*.yaml + tests/support/scenario_loader.py。

ADR-0037 迁移中：run.team/run.agent/delegation/llm.chat 等 span 已退役，
edge case 测试改断 journal 事件（TeamRunStarted/Finished、AgentRunStarted/Finished、
DelegationIssued），断言前必须用 bound_session 绑定 publish Session
（否则 record() 静默跳过）。transport.request/response 等机制平面 span 仍在。
"""

from __future__ import annotations

__keep_llm_key__ = True  # scripted/booted runs need a dummy credential for the reasoner fail-loud gate (see tests/conftest.py)

import pytest

from lca.application.api.api import Agent, Team, TeamLead, ensure_default_ctx
from lca.contracts.atoms.telemetry.telemetry import SpanName
from lca.contracts.models.observability.journal.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DelegationIssued,
    TeamRunFinished,
    TeamRunStarted,
)
from lca.contracts.models.team.team.coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_GRAPH,
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
    FanOut,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from tests.harness.collector import InMemoryObservability
from tests.harness.modes import ALL_MODES, scripted_llm_for_mode
from tests.harness.report import format_case_digest
from tests.harness.runner import run_mode
from tests.harness.scripted_llm import ScriptedLLMAdapter, respond
from tests.support.session_gate_helpers import bound_session
from tests.support.strategy_registry import build_strategy_registry


@pytest.fixture(autouse=True, scope="module")
async def _boot_default_ctx_for_module() -> None:
    """Team/Agent construction needs a warm default plugin ctx (ADR-0062 PR-4)."""
    await ensure_default_ctx()


def _llm_for_mode(mode: str) -> ScriptedLLMAdapter:
    return scripted_llm_for_mode(mode)


def _journal_event_types(col: InMemoryObservability) -> list[type]:
    """Journal-as-Truth (ADR-0037): span 拓扑已退役，断言走 journal 事件类型。"""
    return [type(stamped.event) for stamped in col.store.events]


def _journal_order(col: InMemoryObservability) -> list[str]:
    """Journal-as-Truth (ADR-0037): 链路断言走 journal 事件发射顺序。"""
    return [type(stamped.event).__name__ for stamped in col.store.events]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ALL_MODES)
async def test_mode_happy_path_scripted(mode: str) -> None:
    """team 模式 happy path：结构 + 链路；失败时 digest 在 AssertionError 里。

    ADR-0037 迁移：run.team/delegation/llm.chat 等语义 span 已退役，
    改断 journal 事件（2026-10-07 probe 实证：board 探针发射
    TeamRunStarted(mandate=board, lead_role=Lead, members=(Alice, Bob))
    → AgentRunStarted(Lead) → AgentRunFinished → TeamRunFinished）。
    """
    llm = _llm_for_mode(mode)
    with bound_session(f"mode-{mode}-happy"):
        outcome = await run_mode(mode, llm, objective=f"probe {mode}")
    assert outcome.result.status == "completed", format_case_digest(
        outcome.bundle, title=mode, result=outcome.result
    )
    types = _journal_event_types(outcome.collector)
    assert TeamRunStarted in types and TeamRunFinished in types, types
    assert AgentRunStarted in types and AgentRunFinished in types, types
    started = [
        e.event for e in outcome.collector.store.events if isinstance(e.event, TeamRunStarted)
    ]
    assert len(started) == 1, types  # team_root：单容器开闭
    card = started[0]
    assert card.mandate == "board" and card.lead_role == "Lead", card
    assert set(card.members) == {"Alice", "Bob"}, card  # board 收口名单
    order = _journal_order(outcome.collector)
    assert order.index("TeamRunStarted") < order.index("AgentRunStarted"), order
    assert order.index("AgentRunFinished") < order.index("TeamRunFinished"), order
    # board 首轮短路仍以一次 Lead LLM turn 收口（见 tests/harness/modes.py 注释）
    assert len(llm.calls) >= 1, "scripted LLM adapter was never invoked"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ALL_MODES)
async def test_mode_chain_visible(mode: str) -> None:
    """team 模式额外确认：team 容器 → agent run → LLM 链路可走通且 digest 字段齐全。

    ADR-0037 迁移：span_hist/paths 等 span 拓扑断言退役；链路改断
    journal 发射顺序 + scripted adapter 的真实调用记录。
    """
    llm = _llm_for_mode(mode)
    with bound_session(f"mode-{mode}-chain"):
        outcome = await run_mode(mode, llm, objective=f"chain {mode}")
    digest = format_case_digest(outcome.bundle, title=mode, result=outcome.result)
    assert f"=== {mode} ===" in digest
    assert "result.status=" in digest
    assert "TRACE" in digest
    order = _journal_order(outcome.collector)
    assert order.index("TeamRunStarted") < order.index("AgentRunStarted"), digest
    assert order.index("AgentRunStarted") < order.index("TeamRunFinished"), digest
    assert len(llm.calls) >= 1, digest  # 链路末端：LLM 真实被调用


@pytest.mark.asyncio
async def test_team_parent_chain_to_member_llm() -> None:
    """Lead 链路：team 容器 → Lead agent run → LLM 调用。

    ADR-0037 迁移：旧断言要 run.team→transport→run.agent(成员)→llm.chat 的
    span 父子链；board 探针当前只发射 Lead 的 agent run（成员经 board 流程
    内联收口，见 modes.py 注释与 2026-10-07 probe 实证），journal 链路为
    TeamRunStarted → AgentRunStarted(Lead) → AgentRunFinished → TeamRunFinished。
    """
    llm = _llm_for_mode("team")
    with bound_session("team-chain-probe"):
        outcome = await run_mode("team", llm, objective="team chain probe")
    events = outcome.collector.store.events
    started = [e.event for e in events if isinstance(e.event, TeamRunStarted)]
    assert len(started) == 1 and started[0].lead_role == "Lead", _journal_event_types(
        outcome.collector
    )
    agent_starts = [e.event for e in events if isinstance(e.event, AgentRunStarted)]
    roles = {e.agent_role for e in agent_starts}
    assert roles == {"Lead"}, roles
    order = [type(e.event).__name__ for e in events]
    assert order.index("TeamRunStarted") < order.index("AgentRunStarted"), order
    assert order.index("AgentRunFinished") < order.index("TeamRunFinished"), order
    assert len(llm.calls) >= 1, "scripted LLM adapter was never invoked"


# ── Edge case tests（直接构造 team，不依赖 mode catalog） ─────────────


@pytest.mark.asyncio
async def test_edge_single_member_pipeline() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Only": [respond("one")]})
    agent = Agent(role="Only", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[agent], coordination=Pipeline(), observability=col)
    # ADR-0037: run.team/delegation span 退役 → 断言 journal 事件；record() 需 bound publish Session。
    with bound_session("team-pipeline-edge"):
        result = await team.run("solo pipeline")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    types = _journal_event_types(col)
    assert TeamRunStarted in types and TeamRunFinished in types, types
    assert DelegationIssued in types, types


@pytest.mark.asyncio
async def test_edge_fan_out_one_member() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Only": [respond("one")]})
    agent = Agent(role="Only", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[agent], coordination=FanOut(), observability=col)
    with bound_session("team-fanout-edge"):
        result = await team.run("fanout1")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    types = _journal_event_types(col)
    assert TeamRunStarted in types and TeamRunFinished in types, types
    assert DelegationIssued in types, types


@pytest.mark.asyncio
async def test_edge_peer_relay_first_wins() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter(
        {"Alice": [respond("done by alice")], "Bob": [respond("should not matter")]}
    )
    a = Agent(role="Alice", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    b = Agent(role="Bob", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[a, b], coordination=PeerRelay(), observability=col)
    with bound_session("team-relay-edge"):
        result = await team.run("relay")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    issued = [t for t in _journal_event_types(col) if t is DelegationIssued]
    assert len(issued) >= 1, _journal_event_types(col)


@pytest.mark.asyncio
async def test_edge_swarm_max_rounds_one() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Alice": [respond("a1"), respond("a2")], "Bob": [respond("b1")]})
    a = Agent(role="Alice", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    b = Agent(role="Bob", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[a, b], coordination=PeerSwarm(max_rounds=1), observability=col)
    # D3 裁决(todo-38/todo-50):run 路径 record() 需要 bound publish Session。
    with bound_session("team-swarm-edge"):
        result = await team.run("swarm1")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    rounds = col.bundle().by_name(SpanName.TEAM_ROUND.value)
    assert len(rounds) == 1 and rounds[0].attributes.get("max_rounds") == 1, format_case_digest(
        col.bundle(), result=result
    )


@pytest.mark.asyncio
async def test_edge_budget_exhaustion() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Solo": [respond("x")]})
    agent = Agent(
        role="Solo",
        goal="g",
        backstory="b",
        tools=[],
        llm=llm,
        max_steps=0,
        observability=col,
    )
    with bound_session("agent-budget-edge"):
        result = await agent.run("budget edge")
    assert result is not None
    # ADR-0037: run.agent span 退役 → 断言 journal；预算耗尽仍应先发射 RunStarted。
    types = _journal_event_types(col)
    assert AgentRunStarted in types, types


@pytest.mark.asyncio
async def test_edge_illegal_team_construction() -> None:
    llm = ScriptedLLMAdapter(default_respond=True)
    a = Agent(role="A", goal="g", backstory="b", tools=[], llm=llm)
    with pytest.raises(ValueError, match="exactly one"):
        Team(members=[a])  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="exactly one"):
        Team(members=[a], lead=TeamLead.routing(a), coordination=Pipeline())


@pytest.mark.asyncio
async def test_orchestration_registry_completeness() -> None:
    """L3 编排策略注册表完整 —— 九词治理表（ADR-0030）不受 gateway 模式简化影响。"""
    registered = set(build_strategy_registry().names())
    expected = {
        STRATEGY_KEY_LEAD,
        STRATEGY_KEY_PIPELINE,
        STRATEGY_KEY_FAN_OUT,
        STRATEGY_KEY_PEER_RELAY,
        STRATEGY_KEY_PEER_SWARM,
        STRATEGY_KEY_DEBATE,
        STRATEGY_KEY_GRAPH,
    }
    assert registered == expected


@pytest.mark.asyncio
async def test_llm_adapter_invoked() -> None:
    """ADR-0037 迁移：llm.chat/loop.phase.think span 已退役。

    原断言意图是"agent 跑起来确实调了 LLM"——现在用更直接的证据：
    scripted adapter 的调用记录 + agent run 的 journal 起止事件。
    """
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Solo": [respond("hi")]})
    agent = Agent(role="Solo", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    with bound_session("agent-llm-edge"):
        await agent.run("hello")
    assert len(llm.calls) >= 1, "scripted LLM adapter was never invoked"
    types = _journal_event_types(col)
    assert AgentRunStarted in types and AgentRunFinished in types, types


def test_routing_duplicate_delegation_is_idempotent() -> None:
    """字面重复的 (角色, 子任务) 委派被回报记录幂等短路。

    ADR-0037 迁移：delegate.cache_hit span 已退役（4b9d4f135），改判为 journal
    DelegationCacheHit 事件（todo-69 接线，quality 05:09 落地 e98a29595）。

    场景级说明（2026-10-07 probe 实证）：当前 runtime 下 Team.run(ROUTING)
    经单次默认 responder 调用即收口（journal 仅 5 容器事件、零 DelegationIssued），
    Lead 的委派脚本从未被消费 —— 端到端场景触发不了幂等短路，强行断言
    journal 会是空心绿。因此本测试在 cached_delegation_observation 接缝处
    钉住契约：同一 (target_role, subtask) 命中两次 → 两次返回缓存 Observation，
    journal 恰两次 DelegationCacheHit（字段 callee_role/subtask_preview/step）。
    """
    from datetime import UTC, datetime

    from lca.contracts.models.core.execution.decision import DelegationSpec, Observation
    from lca.contracts.models.core.state.state import AgentState, Budget
    from lca.contracts.models.team.delegation.delegation import DelegationResult
    from lca.contracts.models.team.team.awareness import TeamAwareness
    from lca.infrastructure.delegation.cache import cached_delegation_observation

    awareness = TeamAwareness(
        results=[
            DelegationResult(
                result_id="res-dedup",
                target_role="Alice",
                subtask="analyze",
                output="alice view",
                success=True,
                error=None,
                task_id="task-dedup",
                step=1,
                returned_at=datetime.now(UTC),
            )
        ]
    )
    state = AgentState(
        trace_id="trace-dedup",
        task="dedup",
        budget=Budget(),
        team_awareness=awareness,
        step=3,
    )
    spec = DelegationSpec(subtask="analyze", target_role="Alice")

    with bound_session("routing-dedup") as sess:
        obs1 = cached_delegation_observation(spec, state)
        obs2 = cached_delegation_observation(spec, state)
        events = sess.snapshot_events()

    assert isinstance(obs1, Observation) and isinstance(obs2, Observation)
    hits = [e for e in events if e.type == "DelegationCacheHit"]
    assert len(hits) == 2, [e.type for e in events]
    for hit in hits:
        assert hit.payload["callee_role"] == "Alice", hit.payload
        assert hit.payload["subtask_preview"] == "analyze", hit.payload
        assert hit.payload["step"] == 3, hit.payload
