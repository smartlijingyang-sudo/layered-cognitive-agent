"""Tests for Run Workspace plane (ADR-0051)."""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates.artifact_respond_injector import (
    ArtifactRespondInjector,
)
from lca.cognition.brain.decision_gates.office_works_sealer import OfficeWorksSealer
from lca.cognition.brain.decision_gates.terminal_respond import TerminalRespondGate
from lca.cognition.brain.decision_gates.tool_loop_breaker import ToolLoopBreakerGate
from lca.contracts.models.core.budget import TOOL_LOOP_BREAK_THRESHOLD
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.state import AgentState, Budget
from lca.infrastructure.text.safe_boundary import sanitize_stream_text
from lca.infrastructure.workspace.artifact_ledger import (
    ArtifactLedger,
    artifact_closure_text,
    artifact_handoff_block,
    rewrite_artifact_markdown,
)
from lca.infrastructure.workspace.scope import effective_agent_wall_clock, run_workspace_scope
from lca.plugins.journal.artifact_closure_provider import DefaultArtifactClosure


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
        closure = artifact_closure_text(snap)
        assert "report.pdf" in closure
        assert "](/files/file_abc)" in closure
        assert "application/pdf" not in closure
        assert "/mnt/data/outputs/report.pdf" in artifact_handoff_block(snap)

    def test_record_harvest_skips_office_mutations_and_keeps_close(self) -> None:
        ledger = ArtifactLedger()
        ledger.record_harvest(
            [{"name": "deck.pptx", "url": "/files/file_empty", "sizeBytes": 8000}],
            tool_name="run_command",
            command="officecli create /mnt/data/outputs/deck.pptx --json",
        )
        assert ledger.snapshot().artifacts == ()
        ledger.record_harvest(
            [{"name": "deck.pptx", "url": "/files/file_v1", "sizeBytes": 9000}],
            tool_name="run_command",
            command="officecli add /mnt/data/outputs/deck.pptx / --type slide --json",
        )
        assert ledger.snapshot().artifacts == ()
        ledger.record_harvest(
            [{"name": "deck.pptx", "url": "/files/file_v2", "sizeBytes": 11000}],
            tool_name="run_command",
            command="officecli close /mnt/data/outputs/deck.pptx --json",
        )
        arts = ledger.snapshot().artifacts
        assert len(arts) == 1
        assert arts[0].url == "/files/file_v2"
        assert "application/" not in artifact_closure_text(ledger.snapshot())

    def test_same_name_keeps_latest_url(self) -> None:
        ledger = ArtifactLedger()
        ledger.record_file(
            name="deck.pptx",
            mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            url="/files/file_empty",
            size_bytes=8000,
        )
        ledger.record_file(
            name="deck.pptx",
            mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            url="/files/file_flushed",
            size_bytes=48000,
        )
        arts = ledger.snapshot().artifacts
        assert len(arts) == 1
        assert arts[0].url == "/files/file_flushed"
        assert arts[0].size_bytes == 48000

    def test_rewrites_relative_markdown_images(self) -> None:
        ledger = ArtifactLedger()
        ledger.record_file(name="01_绩效总分排名.png", mime_type="image/png", url="/files/file_aaa")
        text = "见图：![绩效总分排名](01_绩效总分排名.png)"
        out = rewrite_artifact_markdown(text, ledger.snapshot())
        assert out == "见图：![绩效总分排名](/files/file_aaa)"


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
            tool_calls=[ToolCall(call_id="c1", tool_name="web_search", arguments={"query": "x"})],
        )
        with run_workspace_scope("run_t", wall_clock_seconds=60):
            out = await gate.enforce(state, decision)
        assert out.action_type == "respond"
        assert out.response_text

    async def test_last_step_still_runs_a_producer(self) -> None:
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
            tool_calls=[ToolCall(call_id="c1", tool_name="executeCode", arguments={"code": "1"})],
        )
        with run_workspace_scope("run_t", wall_clock_seconds=60):
            out = await gate.enforce(state, decision)
        assert out.action_type == "use_tool"
        assert out.tool_calls[0].tool_name == "executeCode"


@pytest.mark.asyncio
class TestOfficeWorksSealer:
    async def test_respond_without_runtime_is_noop(self) -> None:
        gate = OfficeWorksSealer()
        state = AgentState(trace_id="t", task="x", budget=Budget(max_steps=5), step=3)
        decision = Decision(
            decision_id="d",
            action_type="respond",
            rationale="",
            confidence=1.0,
            response_text="done",
        )
        with run_workspace_scope("run_seal", wall_clock_seconds=60):
            out = await gate.enforce(state, decision)
        assert out.action_type == "respond"
        assert out.response_text == "done"


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
        assert "sandbox_execute" in (out.response_text or "")
        assert err in (out.response_text or "")
        assert "任务已完成" not in (out.response_text or "")

    async def test_blocks_identical_successful_calls_without_progress(self) -> None:
        gate = ToolLoopBreakerGate()
        state = AgentState(trace_id="t", task="x", budget=Budget(max_steps=10), step=3)
        for number in range(TOOL_LOOP_BREAK_THRESHOLD):
            state.history.append(
                Turn(
                    decision=Decision(
                        decision_id=f"d{number}",
                        action_type="use_tool",
                        rationale="poll",
                        confidence=0.9,
                        tool_calls=[
                            ToolCall(
                                call_id=f"c{number}",
                                tool_name="tool_search",
                                arguments={"query": "same query"},
                            )
                        ],
                    ),
                    observation=Observation(
                        observation_id=f"o{number}",
                        success=True,
                        payload={"results": []},
                    ),
                )
            )

        out = await gate.enforce(
            state,
            Decision(
                decision_id="next",
                action_type="use_tool",
                rationale="poll again",
                confidence=0.9,
                tool_calls=[
                    ToolCall(
                        call_id="next-call",
                        tool_name="tool_search",
                        arguments={"query": "same query"},
                    )
                ],
            ),
        )

        assert out.action_type == "respond"
        assert "相同参数连续返回相同结果" in (out.response_text or "")

    async def test_allows_equivalent_calls_when_observations_show_progress(self) -> None:
        gate = ToolLoopBreakerGate()
        state = AgentState(trace_id="t", task="x", budget=Budget(max_steps=10), step=3)
        for number in range(TOOL_LOOP_BREAK_THRESHOLD):
            state.history.append(
                Turn(
                    decision=Decision(
                        decision_id=f"d{number}",
                        action_type="use_tool",
                        rationale="poll",
                        confidence=0.9,
                        tool_calls=[
                            ToolCall(
                                call_id=f"c{number}",
                                tool_name="job_status",
                                arguments={"job_id": "job-1"},
                            )
                        ],
                    ),
                    observation=Observation(
                        observation_id=f"o{number}",
                        success=True,
                        payload={"status": ["queued", "running", "complete"][number]},
                    ),
                )
            )

        decision = Decision(
            decision_id="next",
            action_type="use_tool",
            rationale="read final status",
            confidence=0.9,
            tool_calls=[
                ToolCall(
                    call_id="next-call",
                    tool_name="job_status",
                    arguments={"job_id": "job-1"},
                )
            ],
        )

        assert await gate.enforce(state, decision) is decision


class TestArtifactClosure:
    def test_synthesize_from_workspace(self) -> None:
        with run_workspace_scope("run_c", wall_clock_seconds=60):
            from lca.infrastructure.workspace import get_run_workspace

            workspace = get_run_workspace()
            assert workspace is not None
            workspace.artifacts.record_file(name="a.pdf", mime_type="application/pdf")
            text = DefaultArtifactClosure().synthesize()
            assert text is not None
            assert "a.pdf" in text


@pytest.mark.asyncio
class TestArtifactRespondInjector:
    async def test_rewrites_relative_images_and_appends_links(self) -> None:
        from lca.cognition.brain.context_manifest import build_manifest_from_items
        from lca.contracts.models.core.perceive_state import PerceiveState

        gate = ArtifactRespondInjector()
        with run_workspace_scope("run_inj", wall_clock_seconds=60) as workspace:
            workspace.artifacts.record_file(
                name="01_绩效总分排名.png",
                mime_type="image/png",
                url="/files/file_aaa",
                size_bytes=1000,
            )
            state = AgentState(trace_id="t", task="x", budget=Budget(max_steps=5))
            # v3 PR6.D.4: gate reads from the typed manifest slot.
            # Populate from the workspace ledger.
            snap = workspace.artifacts.snapshot()
            from lca.contracts.models.core.perception import ContextItem

            manifest = build_manifest_from_items(
                items=[
                    ContextItem(
                        kind="workspace_artifacts",
                        payload=[
                            {
                                "name": a.name,
                                "url": a.url,
                                "mime": a.mime_type,
                                "size": a.size_bytes,
                            }
                            for a in snap.artifacts
                        ],
                        provenance="workspace_artifacts_sensor",
                    )
                ]
            )
            view = PerceiveState.from_agent_state(state)
            view.current_manifest = manifest
            view.commit(state)
            out = await gate.enforce(
                state,
                Decision(
                    decision_id="d",
                    action_type="respond",
                    rationale="",
                    confidence=1.0,
                    response_text="![绩效总分排名](01_绩效总分排名.png)",
                ),
            )
        text = out.response_text or ""
        assert "![绩效总分排名](/files/file_aaa)" in text
        assert "[📥 01_绩效总分排名.png](/files/file_aaa)" in text

    async def test_keeps_ledger_urls_and_drops_unknown_ones(self) -> None:
        from lca.cognition.brain.context_manifest import build_manifest_from_items
        from lca.contracts.models.core.perceive_state import PerceiveState

        gate = ArtifactRespondInjector()
        with run_workspace_scope("run_inj2", wall_clock_seconds=60) as workspace:
            workspace.artifacts.record_file(
                name="ok.png",
                mime_type="image/png",
                url="/files/file_aaa",
            )
            state = AgentState(trace_id="t", task="x", budget=Budget(max_steps=5))
            snap = workspace.artifacts.snapshot()
            from lca.contracts.models.core.perception import ContextItem

            manifest = build_manifest_from_items(
                items=[
                    ContextItem(
                        kind="workspace_artifacts",
                        payload=[
                            {
                                "name": a.name,
                                "url": a.url,
                                "mime": a.mime_type,
                                "size": a.size_bytes,
                            }
                            for a in snap.artifacts
                        ],
                        provenance="workspace_artifacts_sensor",
                    )
                ]
            )
            view = PerceiveState.from_agent_state(state)
            view.current_manifest = manifest
            view.commit(state)
            out = await gate.enforce(
                state,
                Decision(
                    decision_id="d",
                    action_type="respond",
                    rationale="",
                    confidence=1.0,
                    response_text="keep [ok](/files/file_aaa) drop [bad](/files/file_bbb)",
                ),
            )
        text = out.response_text or ""
        assert "/files/file_aaa" in text
        assert "/files/file_bbb" not in text
