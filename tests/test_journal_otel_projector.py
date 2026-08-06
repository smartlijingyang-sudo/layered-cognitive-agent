"""OtelProjector 拓扑守卫（ADR-0037 Stage 1）。

核心断言：**父子关系由关联骨架显式生成**——成员 run.agent 挂在
delegation span 下（而非 0 秒 transport 化石），delegation span 的生命周期
完整包住成员执行；瞬时事实是 run span 上的 event，不是孤儿 0 秒 span。
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DelegationCompleted,
    DelegationIssued,
    DelegationMechanism,
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    StepCompleted,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolInvoked,
)
from lca.layer0_infra.observability import OtelProjector, SpanView
from lca.layer0_infra.observability.view import view_of

_BASE_TS = 1_000_000.0


def _make_projector() -> tuple[OtelProjector, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "lca-test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return OtelProjector(provider.get_tracer("lca-test")), exporter


def _views(exporter: InMemorySpanExporter) -> dict[str, SpanView]:
    """name → SpanView（重名时保留后结束者，测试内用属性二次定位）。"""
    return {v.name: v for v in map(view_of, exporter.get_finished_spans())}


def _all_views(exporter: InMemorySpanExporter) -> list[SpanView]:
    return list(map(view_of, exporter.get_finished_spans()))


def _stamped(seq: int, ts: float, scope: RunScope, event: object) -> StampedEvent:
    return StampedEvent(seq=seq, ts=ts, scope=scope, event=event)  # type: ignore[arg-type]


def _board_run(projector: OtelProjector) -> None:
    """剧本：board 协作 —— lead 咨询 2 名成员（并行）后收口。"""
    team_scope = RunScope(trace_id="t1", run_id="team-run")
    lead_scope = RunScope(
        trace_id="t1", run_id="lead-run", parent_run_id="team-run", agent_role="客户成功总监"
    )
    seq = 0

    def emit(ts: float, scope: RunScope, event: object) -> None:
        nonlocal seq
        seq += 1
        projector.on_event(_stamped(seq, ts, scope, event))

    emit(
        _BASE_TS,
        team_scope,
        TeamRunStarted(team_id="team-lead", strategy_key="lead", objective="目标"),
    )
    emit(_BASE_TS + 0.1, lead_scope, AgentRunStarted(agent_role="客户成功总监", objective="目标"))
    emit(_BASE_TS + 2.0, lead_scope, LlmCallCompleted(model="qwen-plus", latency_ms=1800))
    # 并行委派两名成员
    emit(
        _BASE_TS + 2.1,
        lead_scope,
        DelegationIssued(
            delegation_id="dlg-arch",
            caller_role="客户成功总监",
            callee_role="解决方案架构师",
            subtask_preview="架构意见",
            mechanism=DelegationMechanism.DELEGATE,
            parallel_group="consult-1",
        ),
    )
    emit(
        _BASE_TS + 2.1,
        lead_scope,
        DelegationIssued(
            delegation_id="dlg-biz",
            caller_role="客户成功总监",
            callee_role="商务经理",
            subtask_preview="商务方案",
            mechanism=DelegationMechanism.DELEGATE,
            parallel_group="consult-1",
        ),
    )
    # 架构师执行（成员 scope：parent=lead run，delegation=dlg-arch）
    arch_scope = RunScope(
        trace_id="t1",
        run_id="arch-run",
        parent_run_id="lead-run",
        delegation_id="dlg-arch",
        agent_role="解决方案架构师",
    )
    emit(
        _BASE_TS + 2.2,
        arch_scope,
        AgentRunStarted(agent_role="解决方案架构师", objective="架构意见"),
    )
    emit(_BASE_TS + 21.0, arch_scope, LlmCallCompleted(model="qwen-plus", latency_ms=18800))
    emit(_BASE_TS + 21.1, arch_scope, AgentRunFinished(status="completed", steps=1))
    emit(
        _BASE_TS + 21.1,
        lead_scope,
        DelegationCompleted(delegation_id="dlg-arch", status="completed"),
    )
    # 商务经理执行（含一次工具调用）
    biz_scope = RunScope(
        trace_id="t1",
        run_id="biz-run",
        parent_run_id="lead-run",
        delegation_id="dlg-biz",
        agent_role="商务经理",
    )
    emit(_BASE_TS + 2.2, biz_scope, AgentRunStarted(agent_role="商务经理", objective="商务方案"))
    emit(_BASE_TS + 4.8, biz_scope, LlmCallCompleted(model="qwen-plus", latency_ms=2500))
    emit(
        _BASE_TS + 5.0,
        biz_scope,
        ToolInvoked(
            tool_name="calculator",
            arguments_preview="2400000 * 0.2",
            result_preview="480000",
            latency_ms=1,
        ),
    )
    emit(_BASE_TS + 21.0, biz_scope, LlmCallCompleted(model="qwen-plus", latency_ms=14500))
    emit(_BASE_TS + 21.2, biz_scope, AgentRunFinished(status="completed", steps=3))
    emit(
        _BASE_TS + 21.2,
        lead_scope,
        DelegationCompleted(delegation_id="dlg-biz", status="completed"),
    )
    # lead 收口
    emit(_BASE_TS + 21.3, lead_scope, SynthesisCompleted(method="lead.board", candidate_count=2))
    emit(_BASE_TS + 45.6, lead_scope, LlmCallCompleted(model="qwen-plus", latency_ms=24300))
    emit(_BASE_TS + 45.7, lead_scope, AgentRunFinished(status="completed", steps=2))
    emit(
        _BASE_TS + 45.8,
        team_scope,
        TeamRunFinished(status="completed", steps=6, output_preview="续约挽留作战计划终版"),
    )


# ── 拓扑：显式父子，化石不可能 ───────────────────────────


def test_member_run_parents_its_delegation_span() -> None:
    projector, exporter = _make_projector()
    _board_run(projector)
    views = _all_views(exporter)

    by_role = {v.attributes.get("agent_role"): v for v in views if v.name == "run.agent"}
    delegation_spans = [v for v in views if v.name == "delegation"]
    team_root = next(v for v in views if v.name == "run.team")
    lead = by_role["客户成功总监"]
    arch = by_role["解决方案架构师"]
    dlg_arch = next(
        d for d in delegation_spans if d.attributes.get("callee_role") == "解决方案架构师"
    )

    assert team_root.parent_span_id is None
    assert lead.parent_span_id == team_root.span_id
    assert dlg_arch.parent_span_id == lead.span_id
    # 核心不变量：成员 run.agent 挂在 delegation span 下，而非 0 秒 transport 化石
    assert arch.parent_span_id == dlg_arch.span_id


def test_delegation_span_wraps_member_execution() -> None:
    projector, exporter = _make_projector()
    _board_run(projector)
    views = _all_views(exporter)

    arch = next(
        v
        for v in views
        if v.name == "run.agent" and v.attributes.get("agent_role") == "解决方案架构师"
    )
    dlg_arch = next(
        v
        for v in views
        if v.name == "delegation" and v.attributes.get("callee_role") == "解决方案架构师"
    )
    # delegation 生命周期完整包住成员执行（issue → completed）
    assert dlg_arch.duration_ms >= arch.duration_ms > 0


def test_resource_spans_parent_their_run() -> None:
    projector, exporter = _make_projector()
    _board_run(projector)
    views = _all_views(exporter)

    arch = next(
        v
        for v in views
        if v.name == "run.agent" and v.attributes.get("agent_role") == "解决方案架构师"
    )
    biz = next(
        v for v in views if v.name == "run.agent" and v.attributes.get("agent_role") == "商务经理"
    )
    llm_views = [v for v in views if v.name == "llm.chat"]
    tool_views = [v for v in views if v.name == "tool.execute"]

    assert len(llm_views) == 5
    assert len(tool_views) == 1
    for llm in llm_views:
        assert llm.parent_span_id in (arch.span_id, biz.span_id, _lead_span_id(views))
    assert tool_views[0].parent_span_id == biz.span_id


def _lead_span_id(views: list[SpanView]) -> str:
    return next(
        v.span_id
        for v in views
        if v.name == "run.agent" and v.attributes.get("agent_role") == "客户成功总监"
    )


def test_generation_explicit_timing_matches_latency() -> None:
    projector, exporter = _make_projector()
    _board_run(projector)
    views = _all_views(exporter)
    llm_views = sorted((v for v in views if v.name == "llm.chat"), key=lambda v: v.duration_ms)
    durations = [v.duration_ms for v in llm_views]
    # 五次 LLM：1.8s(lead think) / 2.5s / 14.5s(biz) / 18.8s(arch) / 24.3s(收口)
    assert durations == [1800, 2500, 14500, 18800, 24300]


def test_no_orphan_or_fossil_spans() -> None:
    projector, exporter = _make_projector()
    _board_run(projector)
    views = _all_views(exporter)
    ids = {v.span_id for v in views}
    # 无孤儿：除根之外每个 span 的父都在集合内
    for view in views:
        if view.parent_span_id is not None:
            assert view.parent_span_id in ids, f"孤儿 span: {view.name}"
    # span 总数 = 1 team + 3 agent + 2 delegation + 5 llm + 1 tool + 1 synthesis = 13
    assert len(views) == 13
    # 无 0 时长容器化石
    for view in views:
        if view.name in ("delegation", "run.agent", "run.team"):
            assert view.duration_ms > 0


# ── 瞬时事实：run span 上的 event，非孤儿 span ──────────


def test_synthesis_projects_as_event_observation() -> None:
    """ADR-0037：瞬时事实投影为 EVENT 观测（挂在所属 run span 下）。"""
    projector, exporter = _make_projector()
    _board_run(projector)
    views = _all_views(exporter)
    lead = next(
        v
        for v in views
        if v.name == "run.agent" and v.attributes.get("agent_role") == "客户成功总监"
    )
    synthesis = [
        v for v in views if v.name == "team.synthesis" and v.parent_span_id == lead.span_id
    ]
    assert len(synthesis) == 1
    assert synthesis[0].attributes.get("candidate_count") == 2
    assert synthesis[0].attributes.get("langfuse.observation.type") == "event"


def test_step_completed_stays_journal_only() -> None:
    """step.completed 是生命周期噪音：不进 OTel/Langfuse，只在 journal。"""
    projector, exporter = _make_projector()
    _board_run(projector)
    scope = RunScope(trace_id="t", run_id="lead-run", parent_run_id="team-run", agent_role="Lead")
    projector.on_event(_stamped(99, _BASE_TS + 2, scope, StepCompleted(step=0, status="working")))
    views = _all_views(exporter)
    assert all(v.name != "step.completed" for v in views)


# ── Langfuse 约定属性 ───────────────────────────────────


def test_langfuse_conventions_stamped() -> None:
    projector, exporter = _make_projector()
    _board_run(projector)
    views = _all_views(exporter)
    team_root = next(v for v in views if v.name == "run.team")
    assert team_root.attributes["session.id"] == "team-lead"
    # OTel 属性回读把 list 归一为 tuple
    assert list(team_root.attributes["langfuse.trace.tags"]) == ["lca", "lead"]
    assert team_root.attributes["langfuse.observation.output"]  # 收口输出落到根

    lead = next(
        v
        for v in views
        if v.name == "run.agent" and v.attributes.get("agent_role") == "客户成功总监"
    )
    assert lead.attributes["langfuse.observation.type"] == "agent"
    assert lead.attributes["langfuse.observation.metadata.agent_role"] == "客户成功总监"

    generations = [v for v in views if v.name == "llm.chat"]
    assert all(g.attributes["langfuse.observation.type"] == "generation" for g in generations)
    tools = [v for v in views if v.name == "tool.execute"]
    assert all(t.attributes["langfuse.observation.type"] == "tool" for t in tools)


# ── 生命周期兜底 ─────────────────────────────────────────


def test_close_ends_leaked_containers() -> None:
    projector, exporter = _make_projector()
    scope = RunScope(trace_id="t", run_id="r")
    projector.on_event(_stamped(1, _BASE_TS, scope, TeamRunStarted(team_id="leak")))
    projector.close()
    views = _all_views(exporter)
    assert len(views) == 1  # 泄漏容器被兜底收尾而非丢失


def test_completed_without_started_is_safe() -> None:
    projector, exporter = _make_projector()
    scope = RunScope(trace_id="t", run_id="r")
    projector.on_event(_stamped(1, _BASE_TS, scope, DelegationCompleted(delegation_id="ghost")))
    projector.on_event(_stamped(2, _BASE_TS, scope, AgentRunFinished(status="completed")))
    assert _all_views(exporter) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
