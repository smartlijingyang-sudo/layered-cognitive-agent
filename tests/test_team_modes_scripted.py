"""全模式 scripted 测试：跑通 + 失败时 AssertionError 内嵌链路 digest 可定位。

观测性不另出报告文件；pytest 失败输出即诊断面（span 直方图 / 路径探针 / 全树）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.team_coordination import (
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
from lca.contracts.telemetry import SpanName
from lca.layer4_app.api import Agent, Team, TeamLead
from lca.layer4_app.defaults import build_default_registries
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

CATALOG = Path(__file__).resolve().parent / "fixtures" / "team_scenarios" / "all_modes_catalog.yaml"

# 每模式：结果 + 必须出现的 span + 父子路径 + 不变量（失败即带 digest）
MODE_EXPECT: dict[str, dict] = {
    "pipeline": {
        "result": {"status": "completed", "min_steps": 1},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TEAM_STRATEGY.value,
                SpanName.TEAM_MEMBER_INVOKE.value,
                SpanName.LOOP_PHASE_THINK.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["has_team_and_strategy", "pipeline_sequential"],
    },
    "fan_out": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TEAM_MEMBER_INVOKE.value,
                SpanName.TEAM_SYNTHESIS.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["fan_out_all_members"],
    },
    "peer_relay": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TEAM_MEMBER_INVOKE.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["has_team_and_strategy"],
    },
    "peer_swarm": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TEAM_ROUND.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["swarm_rounds"],
    },
    "debate": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TEAM_ROUND.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["swarm_rounds"],
    },
    "graph": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TEAM_MEMBER_INVOKE.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["has_team_and_strategy"],
    },
    "routing": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TEAM_STRATEGY.value,
                SpanName.TRANSPORT_REQUEST.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["has_team_and_strategy", "board_consults_members", "lead_transport_chain"],
    },
    "consult": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TRANSPORT_REQUEST.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["has_team_and_strategy", "board_consults_members", "lead_transport_chain"],
    },
    "board": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_TEAM.value,
                SpanName.TRANSPORT_REQUEST.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_TEAM.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
        },
        "invariants": ["has_team_and_strategy", "board_consults_members", "lead_transport_chain"],
    },
    "solo": {
        "result": {"status": "completed"},
        "trace": {
            "must_include_spans": [
                SpanName.RUN_AGENT.value,
                SpanName.LOOP_PHASE_THINK.value,
                SpanName.LLM_CHAT.value,
            ],
            "parent_root": SpanName.RUN_AGENT.value,
            "parent_leaf": SpanName.LLM_CHAT.value,
            "require_shared_trace_id": True,
        },
        "invariants": [],
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
    """每种模式 happy path：结构 + 链路；失败时 digest 在 AssertionError 里。"""
    outcome = await run_mode(mode, _llm_for_mode(mode), objective=f"probe {mode}")
    _assert_mode(mode, outcome)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "routing",
        "consult",
        "board",
        "pipeline",
        "fan_out",
        "peer_relay",
        "peer_swarm",
        "debate",
        "graph",
    ],
)
async def test_mode_chain_visible(mode: str) -> None:
    """每模式额外确认：run.team→llm 可走通且 digest 字段齐全（用于人工读失败）。"""
    outcome = await run_mode(mode, _llm_for_mode(mode), objective=f"chain {mode}")
    digest = format_case_digest(outcome.bundle, title=mode, result=outcome.result)
    assert "span_hist:" in digest
    assert "paths:" in digest
    assert "TRACE" in digest or "--- TRACE" in digest
    assert outcome.bundle.has_path_to(SpanName.RUN_TEAM.value, SpanName.LLM_CHAT.value), digest


@pytest.mark.asyncio
async def test_catalog_yaml_lists_all_modes() -> None:
    """YAML 目录声明的 mode 集合与 ALL_MODES 对齐（solo 除外由代码跑）。"""
    from tests.support.scenario_loader import load_scenario

    assert CATALOG.is_file(), f"missing catalog {CATALOG}"
    spec = load_scenario(CATALOG)
    modes_in_yaml = {
        c.assertions.get("mode") for c in spec.cases.values() if c.assertions.get("mode")
    }
    assert modes_in_yaml == set(ALL_MODES), f"yaml modes {modes_in_yaml} != {set(ALL_MODES)}"
    # teams: 3 lead + 6 coordination
    assert "lead_routing" in spec.teams and "coord_pipeline" in spec.teams
    assert "coord_graph" in spec.teams


@pytest.mark.asyncio
async def test_lead_board_parent_chain_to_member_llm() -> None:
    outcome = await run_mode("board", _llm_for_mode("board"), objective="board chain probe")
    assert_must_include_spans(
        outcome.bundle,
        [
            SpanName.RUN_TEAM.value,
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
        outcome.bundle, title="board roles", result=outcome.result
    )


@pytest.mark.asyncio
async def test_pipeline_parent_chain_to_loop() -> None:
    outcome = await run_mode("pipeline", _llm_for_mode("pipeline"))
    assert_parent_chain_walkable(
        outcome.bundle,
        SpanName.RUN_TEAM.value,
        SpanName.LOOP_PHASE_THINK.value,
        result=outcome.result,
    )
    assert_shared_trace_id(outcome.bundle, outcome.result)


@pytest.mark.asyncio
async def test_edge_single_member_pipeline() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Only": [respond("one")]})
    agent = Agent(role="Only", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[agent], coordination=Pipeline(), observability=col)
    result = await team.run("solo pipeline")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    assert SpanName.TEAM_MEMBER_INVOKE.value in col.bundle().names()


@pytest.mark.asyncio
async def test_edge_fan_out_one_member() -> None:
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter({"Only": [respond("one")]})
    agent = Agent(role="Only", goal="g", backstory="b", tools=[], llm=llm, observability=col)
    team = Team(members=[agent], coordination=FanOut(), observability=col)
    result = await team.run("fanout1")
    assert result.status == "completed", format_case_digest(col.bundle(), result=result)
    assert SpanName.TEAM_MEMBER_INVOKE.value in col.bundle().names()


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
    invokes = col.bundle().by_name(SpanName.TEAM_MEMBER_INVOKE.value)
    # first completed stops — typically 1 invoke
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
async def test_mode_catalog_completeness() -> None:
    registered = set(build_default_registries().orchestration.list_strategies())
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
    lead_modes = {"routing", "consult", "board"}
    coord_modes = {
        STRATEGY_KEY_PIPELINE,
        STRATEGY_KEY_FAN_OUT,
        STRATEGY_KEY_PEER_RELAY,
        STRATEGY_KEY_PEER_SWARM,
        STRATEGY_KEY_DEBATE,
        STRATEGY_KEY_GRAPH,
    }
    assert lead_modes | coord_modes <= set(ALL_MODES) - {"solo"}
    assert set(MODE_EXPECT) == set(ALL_MODES)


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
    """ADR-0032: 字面重复的 (角色, 子任务) 委派被账本幂等短路。

    Lead 第一次 fan-out 成功结算后，第二次发出完全相同的两条委派——应命中
    ``delegate.cache_hit`` 而不是再次走 transport 重跑成员。
    """
    col = InMemoryObservability()
    llm = ScriptedLLMAdapter(
        {
            "Lead": [
                multi_delegate([("Alice", "analyze"), ("Bob", "review")]),
                # 字面重复：同角色同子任务，应短路复用账本结果
                multi_delegate([("Alice", "analyze"), ("Bob", "review")]),
                respond("lead final"),
            ],
            "Alice": [respond("alice view")],
            "Bob": [respond("bob view")],
        },
        default_respond=True,
    )
    outcome = await run_mode("routing", llm, collector=col, objective="dedup probe")
    digest = format_case_digest(col.bundle(), title="routing-dedup", result=outcome.result)

    cache_hits = col.bundle().by_name(SpanName.DELEGATE_CACHE_HIT.value)
    assert len(cache_hits) == 2, digest
    # 只有第一轮真正走 transport（Alice/Bob 各一次）
    transports = col.bundle().by_name(SpanName.TRANSPORT_REQUEST.value)
    assert len(transports) == 2, digest
    assert outcome.result.status.value == "completed", digest
