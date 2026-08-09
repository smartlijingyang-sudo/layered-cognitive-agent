"""Tests for Run Workspace plane (ADR-0051)."""

from __future__ import annotations

import pytest

from lca.contracts.models.core.budget import TOOL_LOOP_BREAK_THRESHOLD
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state import AgentState, Budget
from lca.layer0_infra.text.safe_boundary import sanitize_stream_text
from lca.layer0_infra.workspace.artifact_ledger import (
    ArtifactLedger,
    artifact_closure_text,
    artifact_handoff_block,
)
from lca.layer0_infra.workspace.scope import effective_agent_wall_clock, run_workspace_scope
from lca.layer1_cognitive.brain.decision_gates.terminal_respond import TerminalRespondGate
from lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate
from lca.layer2_runtime.completion.artifact_closure import synthesize_artifact_closure


class TestSafeBoundary:
    def test_sanitize_surrogates(self) -> None:
        text = "ok\ud800bad"
        cleaned = sanitize_stream_text(text)
        assert "\ud800" not in cleaned
        cleaned.encode("utf-8")


class TestArtifactLedger:
    def test_closure_and_handoff(self) -> None:
        ledger = ArtifactLedger()
        ledger.record_file(
            name="report.pdf",
            mime_type="application/pdf",
            url="/files/file_abc",
            size_bytes=92160,
            guest_path="/mnt/data/outputs/report.pdf",
        )
        snap = ledger.snapshot()
        assert "report.pdf" in artifact_closure_text(snap)
        assert "/mnt/data/outputs/report.pdf" in artifact_handoff_block(snap)


class TestRunWorkspaceScope:
    def test_effective_wall_inherits_deadline(self) -> None:
        with run_workspace_scope("run_test", wall_clock_seconds=600):
            wall = effective_agent_wall_clock(300)
            assert wall is not None
            assert 0 < wall <= 600


@pytest.mark.asyncio
class TestTerminalRespondGate:
    async def test_forces_respond_on_last_step(self) -> None:
        gate = TerminalRespondGate()
        state = AgentState(
            trace_id="t",
            task="x",
            budget=Budget(max_steps=5),
            step=4,
        )
        decision = Decision(
            decision_id="d1",
            action_type="use_tool",
            rationale="test",
            confidence=0.9,
            tool_calls=[
                ToolCall(call_id="c1", tool_name="sandbox_execute", arguments={"code": "1"})
            ],
        )
        with run_workspace_scope("run_t", wall_clock_seconds=60):
            out = await gate.enforce(state, decision)
        assert out.action_type == "respond"
        assert out.response_text


@pytest.mark.asyncio
class TestToolLoopBreakerGate:
    async def test_blocks_after_repeated_failures(self) -> None:
        gate = ToolLoopBreakerGate()
        state = AgentState(trace_id="t", task="x", budget=Budget(max_steps=10), step=3)
        err = "ModuleNotFoundError: olefile"
        for _ in range(TOOL_LOOP_BREAK_THRESHOLD):
            state.history.append(
                Turn(
                    decision=Decision(
                        decision_id="d",
                        action_type="use_tool",
                        rationale="test",
                        confidence=0.9,
                        tool_calls=[
                            ToolCall(call_id="c0", tool_name="sandbox_execute", arguments={})
                        ],
                    ),
                    observation=Observation(
                        observation_id="o", success=False, payload=None, error=err
                    ),
                )
            )
        decision = Decision(
            decision_id="d2",
            action_type="use_tool",
            rationale="test",
            confidence=0.9,
            tool_calls=[ToolCall(call_id="c2", tool_name="sandbox_execute", arguments={})],
        )
        out = await gate.enforce(state, decision)
        assert out.action_type == "respond"


class TestArtifactClosure:
    def test_synthesize_from_workspace(self) -> None:
        with run_workspace_scope("run_c", wall_clock_seconds=60):
            from lca.layer0_infra.workspace import get_run_workspace

            workspace = get_run_workspace()
            assert workspace is not None
            workspace.artifacts.record_file(name="a.pdf", mime_type="application/pdf")
            text = synthesize_artifact_closure()
            assert text is not None
            assert "a.pdf" in text
