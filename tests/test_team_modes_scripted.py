"""Team mode scripted 测试（ADR-0052）：team 模式跑通 + trace 断言。

个体协作策略（pipeline/debate/fan_out 等）的测试走 edge case 测试和
tests/fixtures/team_scenarios/*.yaml + tests/support/scenario_loader.py。
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.telemetry import SpanName
from lca.contracts.models.team.team_coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_GRAPH,
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
    FanOut,
    LeadMandate,
    PeerRelay,
    PeerSwarm,
    Pipeline,
)
from lca.layer4_app.api import Agent, Team, TeamLead, ensure_default_ctx
from tests.harness.collector import InMemoryObservability
from tests.harness.modes import ALL_MODES, scripted_llm_for_mode
from tests.harness.report import format_case_digest
from tests.harness.runner import run_mode
from tests.harness.scripted_llm import ScriptedLLMAdapter, multi_delegate, respond
from tests.harness.trace_assert import (
    assert_must_include_spans,
    assert_parent_chain_walkable,
    assert_shared_trace_id,
    assert_trace_expect,
)
from tests.support.strategy_registry import build_strategy_registry


@pytest.fixture(autouse=True)
async def _boot_default_ctx_for_module() -> None:
    """Team/Agent construction needs a warm default plugin ctx (ADR-0062 PR-4)."""
    await ensure_default_ctx()

# team 模式（board 治理探针）的期望
MODE_EXPECT: dict[str, dict] = {
    "team": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.DELEGATION.value,
                SpanName.TRANSPORT_REQUEST.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["team_root", "board_consults_members", "lead_transport_chain"],
    },
}


def _llm_for_mode(mode: str) -> ScriptedLLMAdapter:
    return scripted_llm_for_mode(mode)


def _assert_mode(mode: str, outcome) -> None:
    assert_trace_expect(
        outcome.bundle,
        outcome.result,
        MODE_EXPECT[mode],
        case=f"mode={mode}",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ALL_MODES)
async def test_mode_happy_path_scripted(mode: str) -> None:
    """team 模式 happy path：结构 + 链路；失败时 digest 在 AssertionError 里。"""
    outcome = await run_mode(mode, _llm_for_mode(mode), objective=f"probe {mode}")
    _assert_mode(mode, outcome)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ALL_MODES)
async def test_mode_chain_visible(mode: str) -> None:
    """team 模式额外确认：run.team→llm 可走通且 digest 字段齐全。"""
    outcome = await run_mode(mode, _llm_for_mode(mode), objective=f"chain {mode}")
    digest = format_case_digest(outcome.bundle, title=mode, result=outcome.result)
    assert "span_hist:" in digest
    assert "paths:" in digest
    assert "TRACE" in digest or "--- TRACE" in digest
    assert outcome.bundle.has_path_to(SpanName.RUN_TEAM.value, SpanName.LLM_CHAT.value), digest


@pytest.mark.asyncio
async def test_team_parent_chain_to_member_llm() -> None:
    outcome = await run_mode("team", _llm_for_mode("team"), objective="team chain probe")
    assert_must_include_spans(
        outcome.bundle,
        [
            SpanName.RUN_TEAM.value,
            SpanName.DELEGATION.value,
            SpanName.TRANSPORT_REQUEST.value,
            SpanName.TRANSPORT_RESPONSE.value,
            SpanName.RUN_AGENT.value,
            SpanName.LLM_CHAT.value,
        ],
        result=outcome.result,
    )
    assert_parent_chain_walkable(
        outcome.bundle,
        SpanName.RUN_TEAM.value,
        SpanName.TRANSPORT_REQUEST.value,
        result=outcome.result,
    )
    assert_parent_chain_walkable(
        outcome.bundle,
        SpanName.RUN_TEAM.value,
        SpanName.LLM_CHAT.value,
        result=outcome.result,
    )
    assert_shared_trace_id(outcome.bundle, outcome.result)
    roles = {
        s.attributes.get("agent_role")
        for s in outcome.bundle.by_name(SpanName.RUN_AGENT.value)
        if s.attributes.get("agent_role")
    }
    assert "Lead" in roles and len(roles) >= 2, format_case_digest(
        outcome.bundle, title="team roles", result=outcome.result
    )


# ── Edge case tests（直接构造 team，不依赖 mode catalog） ─────────────


@pytest.mark.asyncio
async def test_edge_single_member_pipeline() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Only": [respond("one")]})
    agent = Agent(role="Only", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[agent], coordination=Pipeline(), observability=col)
    result = await team.run("solo pipeline")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    assert SpanName.DELEGATION.value in col.bundle().names()


@pytest.mark.asyncio
async def test_edge_fan_out_one_member() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Only": [respond("one")]})
    agent = Agent(role="Only", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[agent], coordination=FanOut(), observability=col)
    result = await team.run("fanout1")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    assert SpanName.DELEGATION.value in col.bundle().names()


@pytest.mark.asyncio
async def test_edge_peer_relay_first_wins() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter(
        {"Alice": [respond("done by alice")], "Bob": [respond("should not matter")]}
    )
    a = Agent(role="Alice", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    b = Agent(role="Bob", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[a, b], coordination=PeerRelay(), observability=col)
    result = await team.run("relay")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    invokes = col.bundle().by_name(SpanName.DELEGATION.value)
    assert len(invokes) >= 1, format_case_digest(col.bundle(), result=result)


@pytest.mark.asyncio
async def test_edge_swarm_max_rounds_one() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Alice": [respond("a1"), respond("a2")], "Bob": [respond("b1")]})
    a = Agent(role="Alice", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    b = Agent(role="Bob", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[a, b], coordination=PeerSwarm(max_rounds=1), observability=col)
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
    result = await agent.run("budget edge")
    assert result is not None
    assert SpanName.RUN_AGENT.value in col.bundle().names(), format_case_digest(
        col.bundle(), result=result
    )


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
async def test_llm_chat_span_emitted() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Solo": [respond("hi")]})
    agent = Agent(role="Solo", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    await agent.run("hello")
    names = col.bundle().names()
    assert SpanName.LLM_CHAT.value in names and SpanName.LOOP_PHASE_THINK.value in names, (
        format_case_digest(col.bundle())
    )


@pytest.mark.asyncio
async def test_routing_duplicate_delegation_is_idempotent() -> None:
    """字面重复的 (角色, 子任务) 委派被回报记录幂等短路。"""
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter(
        {
            "Lead": [
                multi_delegate([("Alice", "analyze"), ("Bob", "review")]),
                multi_delegate([("Alice", "analyze"), ("Bob", "review")]),
                respond("lead final"),
            ],
            "Alice": [respond("alice view")],
            "Bob": [respond("bob view")],
        },
        default_respond=True,
    )

    def _a(role: str, steps: int = 5) -> Agent:
        return Agent(
            role=role,
            goal="g",
            backstory="b",
            tools=[],
            llm=llm,
            max_steps=steps,
            observability=col,
        )

    team = Team(
        members=[_a("Alice"), _a("Bob")],
        lead=TeamLead(_a("Lead", steps=15), LeadMandate.ROUTING),
        observability=col,
    )
    result = await team.run("dedup probe")
    digest = format_case_digest(col.bundle(), title="routing-dedup", result=result)

    cache_hits = col.bundle().by_name(SpanName.DELEGATE_CACHE_HIT.value)
    assert len(cache_hits) == 2, digest
    transports = col.bundle().by_name(SpanName.TRANSPORT_REQUEST.value)
    assert len(transports) == 2, digest
    assert result.status.value == "completed", digest
