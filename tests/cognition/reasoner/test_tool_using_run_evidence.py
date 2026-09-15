"""DoD#4 evidence: tool-using path with ForkedTools + journaled tool EPs.

eng/retire-v1-reasoner-sandbox Conditional Keep — proves a real (non-prose)
tool-using path without a live LLM:

1. ``concept.tool.fork`` / ToolsService fork surfaces sandbox APIs
   (``runCommand`` / ``executeCode``) as ``ForkedTools``.
2. ``PromptReasoner.complete_turn`` consumes those tools; mock LLM returns
   a tool call (no empty-tools fallback).
3. ``SimpleSafeExecutor`` executes the sandbox tool; FactGateway commits
   tool catalog receipts + ``phase.tool.call.*`` spine EPs.
4. Doctor on the resulting closed journal reports ``broken_hop is None``.
"""

from __future__ import annotations

from typing import Any, ClassVar
from unittest.mock import patch

import pytest

from lca.cognition.body.executor.safe_executor import SimpleSafeExecutor
from lca.cognition.brain.reasoner.reasoner import PromptReasoner
from lca.contracts.models.cognition.boundary import BindingsView, ForkedTools
from lca.contracts.models.cognition.reasoner_turn import ReasonerTurnRender
from lca.contracts.models.core.conversation.llm import LLMResponse, NativeToolCall
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.observability import (
    JournalMetadata,
    JournalStep,
    ReflectTrace,
    StepContext,
    append_step,
    close_document,
    empty_document,
)
from lca.contracts.harness.memory.events import ToolInvokedCommitted, ToolStartedCommitted
from lca.contracts.models.observability.journal.step import ToolCallRecord, ToolResult
from lca.contracts.models.team.role.team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.contracts.protocols import LLMAdapter, Tool
from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeInput
from lca.infrastructure.capability.tools.tools import ToolsService
from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.observability.journal.step.projector import JournalDocumentWriter
from lca.infrastructure.sandbox.runtime.scope import bind_sandbox_runtime, unbind_sandbox_runtime
from lca.infrastructure.tools.run.attachment_scope import run_attachment_scope
from lca.infrastructure.tools.run.finalizer import run_id_scope
from lca.infrastructure.tools.sandbox.runtime_tools import (
    SANDBOX_EXECUTE_TOOL_NAME,
    SandboxExecuteTool,
)
from lca.nodes.concept.tool_fork.dispatch.dispatch import ToolForkDispatchExecutor
from lca.plugins.transport.webserver.doctor.doctor import diagnose_step_tree
from tests.support.inline_sandbox import InlineSandbox


class _NamedTool:
    """Minimal Tool duck with a sandbox API name for fork fail-loud checks."""

    description: ClassVar[str] = "evidence stub"
    parameters: ClassVar[dict[str, object]] = {"type": "object"}
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, name: str) -> None:
        self.name = name

    async def execute(self, args: dict[str, Any] | None = None) -> object:
        del args
        return None

    def validate(self, args: dict[str, Any] | None = None) -> str | None:
        del args
        return None


def _render() -> ReasonerTurnRender:
    return ReasonerTurnRender(
        prompt="run sandbox code",
        trace=None,
        section_count=0,
        manifest=None,
        activated_skill_ids=(),
        section_outputs=None,
        total_chars=None,
        variant=None,
    )


def _state() -> AgentState:
    return AgentState(trace_id="tool-using-evidence", task="sandbox", budget=Budget())


@pytest.mark.asyncio
async def test_tool_using_path_fork_reasoner_sandbox_journal_broken_hop_none(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real seam chain: fork → complete_turn(tool call) → sandbox exec → doctor."""

    # ── 1) Fork: sandbox bindings must surface runCommand / executeCode ──
    tools_svc = ToolsService()
    tools_svc.register_factory(
        "g2a",
        lambda _b: [
            _NamedTool(name="runCommand"),
            _NamedTool(name="executeCode"),
        ],
    )

    class _Runtime:
        tools = tools_svc

    class _Ctx:
        runtime = _Runtime()

    bindings = BindingsView(sandbox=object())
    fork_out = await ToolForkDispatchExecutor().node_execute(
        _Ctx(),  # type: ignore[arg-type]
        NodeInput(port_values={"bindings": bindings}),
    )
    forked = fork_out.port_values["forked_tools"]
    assert isinstance(forked, ForkedTools)
    names = {getattr(t, "name", "") for t in forked.items}
    assert "runCommand" in names and "executeCode" in names

    # ── 2) Reasoner: mock LLM returns a tool call; ForkedTools required ──
    reasoner = PromptReasoner(llm=object())  # type: ignore[arg-type]
    captured: dict[str, object] = {}

    async def _fake_execute(
        llm_adapter: LLMAdapter,
        tools: list[Tool],
        prompt: str,
        **kwargs: object,
    ) -> LLMResponse:
        del llm_adapter, prompt, kwargs
        captured["tool_names"] = [t.name for t in tools]
        return LLMResponse(
            text="",
            model="scripted",
            tool_calls=[
                NativeToolCall(
                    call_id="call_evidence",
                    name="sandbox_execute",
                    arguments={"code": 'print("evidence-ok")'},
                )
            ],
        )

    monkeypatch.setattr(
        "lca.cognition.brain.reasoner.reasoner.execute_llm_turn",
        _fake_execute,
    )
    response = await reasoner.complete_turn(_state(), _render(), tools=forked)
    assert response.tool_calls, "mock LLM must return a tool call"
    assert response.tool_calls[0].name == "sandbox_execute"
    assert captured["tool_names"] == ["runCommand", "executeCode"]

    # ── 3) Sandbox tool execute; capture FactGateway tool EP commits ──
    store = LocalFileStore(tmp_path / "store")
    sandbox = InlineSandbox()
    run_id = "run_tool_using_evidence"
    catalog_events: list[object] = []
    spine_eps: list[str] = []

    def _capture_catalog(event: object, **kwargs: object) -> object:
        del kwargs
        catalog_events.append(event)
        return None

    def _capture_ep(ep: str, payload: object, **kwargs: object) -> object:
        del payload, kwargs
        spine_eps.append(ep)
        return None

    with run_attachment_scope([]):
        await bind_sandbox_runtime(run_id, sandbox, store, ())
    try:
        tool = SandboxExecuteTool(sandbox=sandbox, store=store)
        executor = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=[SANDBOX_EXECUTE_TOOL_NAME])
        )
        with (
            patch(
                "lca.loop.commit.tool_journal.append_catalog_bound",
                side_effect=_capture_catalog,
            ),
            patch(
                "lca.loop.commit.tool_journal.publish_ep_bound",
                side_effect=_capture_ep,
            ),
            run_id_scope(run_id),
        ):
            obs = await executor.execute(
                tool,
                {"code": 'print("evidence-ok")'},
                RetryPolicy(max_retries=0),
                CacheConfig(enabled=False),
                invocation_id="call_evidence",
            )
        assert obs.success, getattr(obs, "error", None)

        started = [e for e in catalog_events if isinstance(e, ToolStartedCommitted)]
        invoked = [e for e in catalog_events if isinstance(e, ToolInvokedCommitted)]
        assert len(started) == 1, f"ToolStartedCommitted missing; got {catalog_events!r}"
        assert len(invoked) == 1, f"ToolInvokedCommitted missing; got {catalog_events!r}"
        assert started[0].tool_name == SANDBOX_EXECUTE_TOOL_NAME
        assert invoked[0].ok is True
        assert invoked[0].invocation_id == started[0].invocation_id == "call_evidence"
        assert "phase.tool.call.start" in spine_eps
        assert "phase.tool.call.end" in spine_eps
        assert "step.tool_call.record" in spine_eps
        invocation_id = started[0].invocation_id
    finally:
        await unbind_sandbox_runtime(run_id)

    # ── 4) Doctor: closed journal with that tool step → broken_hop=None ──
    meta = JournalMetadata(
        agent_role="助手",
        strategy_key="solo",
        plan_ref="PlanInterpreter+BundleGraphSpec",
        objective="tool-using evidence",
    )
    doc = empty_document(
        run_id=run_id,
        trace_id="tool-using-evidence",
        metadata=meta,
        started_at=0.0,
    )
    step = JournalStep(
        step_id="step_001",
        step_index=1,
        phase="act",
        entered_at=0.0,
        exited_at=1.0,
        duration_ms=1000,
        context_before=StepContext(objective="tool-using evidence"),
        tool_call=ToolCallRecord(
            invocation_id=invocation_id,
            name=SANDBOX_EXECUTE_TOOL_NAME,
            arguments={"code": 'print("evidence-ok")'},
        ),
        tool_result=ToolResult(
            ok=True,
            latency_ms=10,
            delta_summary="evidence-ok",
            error=None,
        ),
        reflect=ReflectTrace(summary="sandbox tool succeeded"),
        outcome="ok",
        error=None,
    )
    doc = append_step(doc, step)
    doc = close_document(doc, outcome="completed", closed_at=2.0)
    journal_path = tmp_path / "journal.json"
    JournalDocumentWriter(journal_path).write(doc)

    report = diagnose_step_tree(journal_path)
    assert report.broken_hop is None, (
        f"DoD#4 requires broken_hop=None; got {report.broken_hop!r}: {report.summary}"
    )
    assert report.hops["H7"].ok is True
