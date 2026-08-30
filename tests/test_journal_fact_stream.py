"""FactStreamProjector tests —— 每个事件类型渲染覆盖。"""

from __future__ import annotations

import io

from lca.contracts.models.observability.journal import (
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    AttachmentStagingCompleted,
    AttachmentStagingFailed,
    AttachmentStagingStarted,
    CastingCompleted,
    CastingFailed,
    CastingStarted,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    DelegationMechanism,
    JournalEvent,
    LlmCallCompleted,
    LlmCallStarted,
    ReasoningCompleted,
    ReasoningDelta,
    RunActivity,
    RunScope,
    SandboxOutputDelta,
    StampedEvent,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolCallStreaming,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.infrastructure.observability.journal.fact_stream_projector import (
    FactStreamProjector,
)


def _stamped(seq: int, event: JournalEvent, *, role: str = "tester") -> StampedEvent:
    return StampedEvent(seq=seq, ts=1000.0 + seq, scope=RunScope(agent_role=role), event=event)


def _render(
    event: JournalEvent, *, verbose: bool = False, show_deltas: bool = False, role: str = "tester"
) -> str:
    buf = io.StringIO()
    projector = FactStreamProjector(stream=buf, verbose=verbose, show_deltas=show_deltas)
    projector.on_event(_stamped(1, event, role=role))
    return buf.getvalue()


# ── 容器事件 ───────────────────────────────────────────


def test_team_started_renders_scenario_card() -> None:
    event = TeamRunStarted(
        team_id="team-1",
        strategy_key="Pipeline",
        mandate="board",
        lead_role="lead",
        members=("worker-a", "worker-b"),
        objective_preview="do the thing",
        plan_steps="step 1",
    )
    output = _render(event)
    assert "TeamRun" in output
    assert "team-1" in output
    assert "Pipeline" in output
    assert "board" in output
    assert "worker-a" in output
    assert "do the thing" in output


def test_team_finished_renders_status() -> None:
    event = TeamRunFinished(status="completed", steps=5)
    output = _render(event)
    assert "TeamRun" in output
    assert "completed" in output
    assert "5 steps" in output


def test_agent_started_renders_role() -> None:
    event = AgentRunStarted(agent_role="engineer", objective_preview="fix bug")
    output = _render(event)
    assert "AgentRun" in output
    assert "engineer" in output
    assert "fix bug" in output


def test_agent_finished_with_error() -> None:
    event = AgentRunFinished(status="error", steps=2, error="boom")
    output = _render(event)
    assert "AgentRun" in output
    assert "error" in output
    assert "boom" in output


# ── 协作事件 ───────────────────────────────────────────


def test_delegation_issued_shows_subtask() -> None:
    event = DelegationIssued(
        delegation_id="d1",
        caller_role="lead",
        callee_role="worker",
        subtask_preview="implement feature",
        mechanism=DelegationMechanism.HANDOFF,
    )
    output = _render(event)
    assert "delegation" in output
    assert "worker" in output
    assert "handoff" in output
    assert "implement feature" in output


def test_delegation_completed_shows_status() -> None:
    event = DelegationCompleted(delegation_id="d1", ok=True, status="done")
    output = _render(event)
    assert "delegation" in output
    assert "ok" in output
    assert "done" in output


def test_delegation_cache_hit() -> None:
    event = DelegationCacheHit(callee_role="worker", subtask_preview="cached task", step=3)
    output = _render(event)
    assert "cache hit" in output
    assert "worker" in output


def test_synthesis_completed() -> None:
    event = SynthesisCompleted(method="merge", candidate_count=3)
    output = _render(event)
    assert "synthesis" in output
    assert "merge" in output
    assert "3 candidates" in output


# ── 认知事实 ───────────────────────────────────────────


def test_decision_renders_action_type() -> None:
    event = DecisionMade(step=2, action_type="use_tool", tool_name="bash", confidence=0.95)
    output = _render(event)
    assert "decision" in output
    assert "Step 2" in output
    assert "use_tool" in output
    assert "bash" in output
    assert "0.95" in output


def test_step_completed() -> None:
    event = StepCompleted(step=3, status="completed", action_type="respond")
    output = _render(event)
    assert "step 3" in output
    assert "completed" in output
    assert "respond" in output


def test_action_degraded() -> None:
    event = ActionDegraded(original_action_type="write_file", degraded_to="respond", step=1)
    output = _render(event)
    assert "degraded" in output
    assert "write_file" in output
    assert "respond" in output


# ── 资源事实：LLM ─────────────────────────────────────


def test_llm_started() -> None:
    event = LlmCallStarted(step=1, model="gpt-4")
    output = _render(event)
    assert "llm.start" in output
    assert "gpt-4" in output


def test_llm_completed_shows_tokens() -> None:
    event = LlmCallCompleted(
        model="claude-3",
        ok=True,
        latency_ms=1200,
        prompt_tokens=100,
        completion_tokens=50,
        stream=True,
    )
    output = _render(event)
    assert "llm.done" in output
    assert "claude-3" in output
    assert "1200ms" in output
    assert "100" in output
    assert "50" in output
    assert "stream" in output


def test_llm_completed_verbose_shows_previews() -> None:
    event = LlmCallCompleted(
        model="gpt-4",
        ok=True,
        latency_ms=500,
        prompt_preview="fix this code",
        response_preview="here is the fix",
    )
    output = _render(event, verbose=True)
    assert "prompt: fix this code" in output
    assert "response: here is the fix" in output


def test_llm_completed_default_hides_previews() -> None:
    event = LlmCallCompleted(
        model="gpt-4",
        ok=True,
        latency_ms=500,
        prompt_preview="secret prompt",
        response_preview="secret response",
    )
    output = _render(event, verbose=False)
    assert "secret prompt" not in output
    assert "secret response" not in output


# ── 资源事实：工具 ────────────────────────────────────


def test_tool_started_shows_arguments() -> None:
    """ADR-0101 PR-2:tool 事件不再有 arguments_preview 字段;projector
    只看 tool_name + invocation_id,args 内容由 arguments_ref 走 evidence 平面。"""
    event = ToolStarted(tool_name="bash", invocation_id="inv1")
    output = _render(event)
    assert "tool.start" in output
    assert "bash" in output
    assert "inv1" in output


def test_tool_invoked_shows_latency() -> None:
    event = ToolInvoked(tool_name="bash", ok=True, latency_ms=300)
    output = _render(event)
    assert "tool.done" in output
    assert "bash" in output
    assert "300ms" in output
    assert "ok" in output


def test_tool_denied_shows_reason() -> None:
    event = ToolDenied(tool_name="rm", reason="destructive command")
    output = _render(event)
    assert "tool.denied" in output
    assert "rm" in output
    assert "destructive command" in output


def test_tool_streaming() -> None:
    """ADR-0101 PR-2:ToolCallStreaming 不再带 arguments_preview;projector
    只看 tool_name + tool_call_id。"""
    event = ToolCallStreaming(tool_name="bash", tool_call_id="tc1")
    output = _render(event)
    assert "tool.streaming" in output
    assert "bash" in output


# ── 增量事件 ───────────────────────────────────────────


def test_text_delta_hidden_by_default() -> None:
    event = StepTextDelta(step=1, text_delta="hello", seq=1, channel="decision")
    output = _render(event)
    assert output == ""


def test_text_delta_shown_with_deltas() -> None:
    event = StepTextDelta(step=1, text_delta="hello world", seq=1, channel="decision")
    output = _render(event, show_deltas=True)
    assert "text.delta" in output
    assert "hello world" in output


def test_reasoning_delta_hidden_by_default() -> None:
    event = ReasoningDelta(step=1, text_delta="thinking...", seq=1)
    output = _render(event)
    assert output == ""


def test_reasoning_delta_shown_with_deltas() -> None:
    event = ReasoningDelta(step=1, text_delta="let me think", seq=2)
    output = _render(event, show_deltas=True)
    assert "reasoning.delta" in output
    assert "let me think" in output


def test_reasoning_completed_always_shown() -> None:
    event = ReasoningCompleted(step=1, duration_ms=500, content_preview="deep thought")
    output = _render(event)
    assert "reasoning.done" in output
    assert "500ms" in output


def test_reasoning_completed_verbose_shows_preview() -> None:
    event = ReasoningCompleted(step=1, duration_ms=500, content_preview="deep thought")
    output = _render(event, verbose=True)
    assert "deep thought" in output


def test_sandbox_delta_hidden_by_default() -> None:
    event = SandboxOutputDelta(
        invocation_id="inv1", stream="stdout", text_delta="output line", seq=1
    )
    output = _render(event)
    assert output == ""


def test_sandbox_delta_shown_with_deltas() -> None:
    event = SandboxOutputDelta(
        invocation_id="inv1", stream="stderr", text_delta="error line", seq=1
    )
    output = _render(event, show_deltas=True)
    assert "sandbox.delta" in output
    assert "stderr" in output


# ── 选角 ───────────────────────────────────────────────


def test_casting_started() -> None:
    event = CastingStarted(objective_preview="build app")
    output = _render(event)
    assert "casting started" in output
    assert "build app" in output


def test_casting_completed() -> None:
    event = CastingCompleted(
        governance_kind="board",
        lead_role="pm",
        selected_roles=("eng", "qa"),
    )
    output = _render(event)
    assert "casting done" in output
    assert "board" in output
    assert "pm" in output
    assert "eng" in output


def test_casting_failed() -> None:
    event = CastingFailed(error="no matching roles")
    output = _render(event)
    assert "casting FAILED" in output
    assert "no matching roles" in output


# ── 活动心跳 ───────────────────────────────────────────


def test_activity_renders_phase() -> None:
    event = RunActivity(phase="llm_wait", step=2, detail="waiting for response")
    output = _render(event)
    assert "activity" in output
    assert "llm_wait" in output
    assert "waiting for response" in output


# ── 附件暂存 ───────────────────────────────────────────


def test_attachment_staging_started() -> None:
    event = AttachmentStagingStarted(plane_id="p1", file_count=3, total_bytes=1024, run_id="r1")
    output = _render(event)
    assert "attach.start" in output
    assert "p1" in output


def test_attachment_staging_completed() -> None:
    event = AttachmentStagingCompleted(
        plane_id="p1", file_count=3, total_bytes=1024, duration_ms=50
    )
    output = _render(event)
    assert "attach.done" in output


def test_attachment_staging_failed() -> None:
    event = AttachmentStagingFailed(plane_id="p1", error="timeout", failed_paths=("/a", "/b"))
    output = _render(event)
    assert "attach.FAIL" in output
    assert "timeout" in output


# ── Section header ─────────────────────────────────────


def test_section_header_on_role_change() -> None:
    buf = io.StringIO()
    projector = FactStreamProjector(stream=buf)
    projector.on_event(
        _stamped(1, StepCompleted(step=1, status="ok", action_type="think"), role="alice")
    )
    projector.on_event(
        _stamped(2, StepCompleted(step=2, status="ok", action_type="act"), role="alice")
    )
    projector.on_event(
        _stamped(3, StepCompleted(step=3, status="ok", action_type="act"), role="bob")
    )
    output = buf.getvalue()
    assert "── alice ──" in output
    assert "── bob ──" in output
    # alice only appears once as section header
    assert output.count("── alice ──") == 1


# ── 结构化特性：Step 分组 / 相对计时 / Token 累计 ────────


def test_step_group_header_appears_on_step_change() -> None:
    buf = io.StringIO()
    projector = FactStreamProjector(stream=buf)
    projector.on_event(_stamped(1, StepCompleted(step=1, status="ok", action_type="think")))
    projector.on_event(_stamped(2, StepCompleted(step=1, status="ok", action_type="act")))
    projector.on_event(_stamped(3, StepCompleted(step=2, status="ok", action_type="think")))
    output = buf.getvalue()
    assert "┌─ Step 1" in output
    assert "┌─ Step 2" in output
    # Step 1 header appears only once
    assert output.count("┌─ Step 1") == 1


def test_relative_timing_delta_shown() -> None:
    """Events show Δms relative to previous event."""

    def _stamped_ts(seq: int, ts: float, event: JournalEvent) -> StampedEvent:
        return StampedEvent(seq=seq, ts=ts, scope=RunScope(agent_role="tester"), event=event)

    buf = io.StringIO()
    projector = FactStreamProjector(stream=buf)
    projector.on_event(
        _stamped_ts(1, 1000.0, StepCompleted(step=1, status="ok", action_type="think"))
    )
    projector.on_event(
        _stamped_ts(2, 1000.5, StepCompleted(step=1, status="ok", action_type="act"))
    )
    projector.on_event(
        _stamped_ts(3, 1002.0, StepCompleted(step=1, status="ok", action_type="respond"))
    )
    output = buf.getvalue()
    assert "+0ms" in output  # first event has no delta
    assert "+500ms" in output  # 0.5s = 500ms
    assert "+1.5s" in output  # 1.5s


def test_token_cumulative_after_multiple_llm_calls() -> None:
    buf = io.StringIO()
    projector = FactStreamProjector(stream=buf)
    projector.on_event(
        _stamped(
            1, LlmCallCompleted(model="gpt-4", ok=True, prompt_tokens=100, completion_tokens=50)
        )
    )
    projector.on_event(
        _stamped(
            2, LlmCallCompleted(model="gpt-4", ok=True, prompt_tokens=200, completion_tokens=80)
        )
    )
    output = buf.getvalue()
    # Second call should show cumulative
    assert "cumulative:" in output
    assert "300 in → 130 out" in output


def test_team_finished_shows_resource_summary() -> None:
    buf = io.StringIO()
    projector = FactStreamProjector(stream=buf)
    projector.on_event(_stamped(1, TeamRunStarted(team_id="t1", strategy_key="Pipeline")))
    projector.on_event(
        _stamped(
            2, LlmCallCompleted(model="gpt-4", ok=True, prompt_tokens=500, completion_tokens=200)
        )
    )
    projector.on_event(_stamped(3, ToolStarted(tool_name="bash")))
    projector.on_event(_stamped(4, ToolInvoked(tool_name="bash", ok=True, latency_ms=100)))
    projector.on_event(_stamped(5, TeamRunFinished(status="completed", steps=3)))
    output = buf.getvalue()
    assert "LLM: 1 calls" in output
    assert "500 in → 200 out" in output
    assert "Tools: 1 calls" in output


def test_team_run_card_format() -> None:
    event = TeamRunStarted(
        team_id="team-alpha",
        strategy_key="Pipeline",
        mandate="board",
        lead_role="pm",
        members=("eng", "qa"),
        objective_preview="build feature X",
    )
    output = _render(event)
    assert "═══" in output
    assert "TeamRun · team-alpha" in output
    assert "strategy: Pipeline" in output
    assert "mandate: board" in output
    assert "lead: pm" in output
    assert "members: eng, qa" in output
    assert "task: build feature X" in output


def test_tool_nesting_indentation() -> None:
    """Tool events are indented deeper than step-level events."""
    buf = io.StringIO()
    projector = FactStreamProjector(stream=buf)
    projector.on_event(_stamped(1, DecisionMade(step=1, action_type="use_tool", tool_name="bash")))
    projector.on_event(_stamped(2, ToolStarted(tool_name="bash", invocation_id="i")))
    projector.on_event(
        _stamped(3, ToolInvoked(tool_name="bash", invocation_id="i", ok=True, latency_ms=100))
    )
    output = buf.getvalue()
    lines = output.split("\n")
    # Decision is at "  │" level (2 spaces + │)
    decision_line = next(line for line in lines if "decision" in line)
    # Tool is at "  │   " level (2 spaces + │ + 3 spaces)
    tool_line = next(line for line in lines if "tool.start" in line)
    # Tool line should be more indented than decision line
    assert tool_line.index("tool.start") > decision_line.index("decision")


def test_tool_error_counted_in_summary() -> None:
    buf = io.StringIO()
    projector = FactStreamProjector(stream=buf)
    projector.on_event(_stamped(1, TeamRunStarted(team_id="t1", strategy_key="Solo")))
    projector.on_event(_stamped(2, ToolStarted(tool_name="bash")))
    projector.on_event(_stamped(3, ToolInvoked(tool_name="bash", ok=False, error="timeout")))
    projector.on_event(_stamped(4, TeamRunFinished(status="completed", steps=1)))
    output = buf.getvalue()
    assert "1 errors" in output


def test_format_duration() -> None:
    from lca.infrastructure.observability.journal.fact_stream_projector import _format_duration

    assert _format_duration(0) == "+0ms"
    assert _format_duration(0.5) == "+0ms"
    assert _format_duration(42) == "+42ms"
    assert _format_duration(999) == "+999ms"
    assert _format_duration(1000) == "+1.0s"
    assert _format_duration(1500) == "+1.5s"
    assert _format_duration(59999) == "+60.0s"
    assert _format_duration(60000) == "+1m0s"
    assert _format_duration(90000) == "+1m30s"
