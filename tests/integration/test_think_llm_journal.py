"""End-to-end regression: a real ``CognitiveAgent.run(...)`` populates the
per-run journal.json with thinking / tool_call / tool_result / native
payload, and the spine ledger carries llm.call.start, llm.call.end, and
step.tool_call.record facts.

Regression anchor for the journal-empty bug introduced by
``2ee56fdc8`` (LlmCallExecutor dropped state / session on the
adapter.complete call, so llm.call.start/end never reached the spine;
LlmCallExecutor never emitted step.tool_call.record so the journal fold
had no tool_call to project). Tasks 1 and 2 fixed those seams; this test
is the closing check.

Reads:

- ``<run_dir>/journal.json`` — folded step tree (ADR-0212).
- ``<run_dir>/<run_id>.spine.jsonl`` — raw spine events.

Pins that all four anchors are populated for a real
``CognitiveAgent.run()`` on the web-standard profile with a scripted LLM
that emits one ``bash(echo hello)`` tool call followed by a final
assistant reply.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    LLMStreamEvent,
    LLMStreamEventType,
    NativeToolCall,
    TokenUsage,
)
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.team.role.team import (
    RoleProfile,
    ToolPermissionManifest,
)
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.journal.spec.spec import AgentSpec


@dataclass
class _ScriptedEcho(LLMAdapter):
    """Emits one bash tool call, then a final assistant reply.

    Mirrors the wire shape of the original ``run_cc39610072bf`` failure
    case: first LLM call declares a ``bash(echo hello)`` tool call,
    second LLM call returns the final assistant reply.
    """

    name: str = "scripted-echo-llm"
    calls: int = 0

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:  # pragma: no cover
        raise AssertionError("think.llm.call drives stream(), not complete()")

    async def stream(self, prompt: str, **kwargs: Any) -> Any:
        del prompt, kwargs
        self.calls += 1
        if self.calls == 1:
            response = LLMResponse(
                text="",
                model=self.name,
                usage=TokenUsage(prompt_tokens=1234, completion_tokens=56),
                tool_calls=[
                    NativeToolCall(
                        call_id="call_echo_1",
                        name="bash",
                        arguments={"command": "echo hello"},
                    ),
                ],
            )
            reasoning = "需要先运行 echo hello,再把它的内容回给用户。"
        else:
            response = LLMResponse(
                text="echo 命令的输出是 hello。",
                model=self.name,
                usage=TokenUsage(prompt_tokens=1300, completion_tokens=24),
            )
            reasoning = "工具已经返回 stdout,直接总结答案。"
        # Reasoning arrives as its own channel, exactly as the provider streams
        # ``reasoning_content`` deltas; the journal folds thinking from it.
        yield LLMStreamEvent(type=LLMStreamEventType.REASONING_TEXT_DELTA, text=reasoning)
        if response.text:
            yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)


def _read_spine_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _bind_run_cursor(ctx: Any, run_id: str, bridge: Any) -> Any:
    """Publish this run's loop cursor, as ``RunSessionBuilder`` does at run setup.

    The cursor carries the step identity behind ``llm.request.header`` and
    ``phase.think.fold``; without it both facts are never produced and the fold
    opens no step.
    """
    from types import SimpleNamespace

    from lca.cognition.body.executor.cursor_record import CursorRecord
    from lca.infrastructure.observability.loop_cursor.persistence.coordinator import (
        NullPersistenceCoordinator,
    )
    from lca.plugins.session.runtime.cursor.port import SessionWritePortAdapter
    from lca_kernel.runtime.observability import ObservabilityRuntime

    runtime = ObservabilityRuntime.from_profile(
        profile=SimpleNamespace(plan_ref="", preset=None),
        ctx=ctx,
        persistence=NullPersistenceCoordinator(),
    )
    cursor = runtime.make_cursor(
        run_id=run_id,
        trace_id=run_id,
        spine=SessionWritePortAdapter(bridge),
    )
    return CursorRecord.bind(cursor)


def _bind_capability_bindings(ctx: Any) -> Any:
    """Publish the per-turn ``BindingsViewBuilder`` on the runtime plane seam.

    Mirrors ``RunExecutionEnvironment`` (the carrier) so the graph reads the
    same typed bindings it would on a live run.
    """
    from lca.contracts.mechanisms.capability.capability import (
        provider_current,
        require_capability,
    )
    from lca.infrastructure.runtime_plane.capability_bindings import (
        BindingsViewBuilder,
        set_capability_bindings,
    )

    return set_capability_bindings(
        BindingsViewBuilder(
            file_store=provider_current(require_capability(ctx, "file_store")),
            search=require_capability(ctx, "search"),
            skill_store=provider_current(require_capability(ctx, "skills")),
            mode="solo",
        )
    )


@pytest.mark.profile_integration
def test_think_llm_journal_populates_journal_json() -> None:
    """A real ``CognitiveAgent.run(...)`` populates ``journal.json`` and
    the spine ledger with the four required anchors:
    thinking, tool_call, tool_result, and the native LLM payload.

    Verifies that LlmCallExecutor (Tasks 1+2) still forwards state and
    session to the adapter (so ``llm.call.start/end`` reach the spine)
    and still emits ``step.tool_call.record`` (so the journal fold has a
    tool_call to project). Reads the journal AFTER the run completes.

    The LLM is scripted, so no provider credential is consulted; an
    ``LLM_API_KEY`` present in the environment must not switch this gate off.
    """
    try:
        from lca.harness.profile.boot.boot import boot_profile
        from lca.plugins.composer.composition.agent_assembly import (
            PlanBoundAgentAssembler,
        )
        from lca.plugins.session.derivers.step_tree.fold_deriver import (
            StepTreeFoldDeriver,
        )
        from lca.plugins.session.runtime.store.store import SessionStore
        from lca.plugins.tools.bash import build_bash_tool
        from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
            RunRegistry,
        )
        from lca.session.lifecycle.bind import (
            bind_run_event_session_from_store,
            unbind_run_event_session,
        )
    except Exception as exc:  # pragma: no cover - import errors are not the test target
        pytest.skip(f"required modules unavailable: {type(exc).__name__}: {exc}")

    run_id = f"run_test_think_llm_journal_{uuid.uuid4().hex[:12]}"

    async def _drive() -> tuple[TaskStatus, Path]:
        ctx = await boot_profile("profiles/web-standard.yaml")
        try:
            store = ctx.inject("session.store")
            if not isinstance(store, SessionStore):
                raise TypeError(f"session.store must be SessionStore, got {type(store).__name__}")
            role = RoleProfile(
                role="Echoer",
                goal="Run bash echo",
                backstory="scripted LLM fixture",
                tool_permission_manifest=ToolPermissionManifest(allowed_tools=["bash"]),
            )
            llm = _ScriptedEcho()
            spec = AgentSpec(profile=role, llm=llm, tools=(build_bash_tool(),), max_steps=5)
            # PlanBoundAgentAssembler injects an internal EventSessionBinder
            # derived from scope. Pre-binding the run Session ourselves lets
            # the spine route events through our writer (the agent's
            # internal binder will see _ACTIVE_SESSION occupied and skip
            # its own bind — the documented cooperative behaviour).
            bound = bind_run_event_session_from_store(store, run_id)
            cursor_token = _bind_run_cursor(ctx, run_id, bound.bridge)
            try:
                agent = PlanBoundAgentAssembler().assemble_agent(spec, scope=ctx)
                # ``concept.tool.fork`` reads its typed ``bindings`` port from the
                # runtime plane seam, which the carrier (RunExecutionEnvironment)
                # publishes per turn. This test drives ``agent.run`` directly, so it
                # publishes the same builder from the same booted capabilities.
                token = _bind_capability_bindings(ctx)
                try:
                    result = await agent.run("请用 bash 工具运行 echo hello 并把结果告诉我。")
                finally:
                    from lca.infrastructure.runtime_plane.capability_bindings import (
                        reset_capability_bindings,
                    )

                    reset_capability_bindings(token)
            finally:
                from lca.cognition.body.executor.cursor_record import CursorRecord

                CursorRecord.bind(cursor_token)
                # Keep ``bound`` in scope: the fold deriver reads the
                # Session via its bridge (already unbound, but the
                # bridge reference is still valid in this process).
                unbind_run_event_session(bound)

            # Resolve the run directory and spine path the same way the
            # builder does (RunRegistry.locator() → filesystem layout).
            registry = RunRegistry()
            locator = registry.locator()
            run_dir = locator.run_dir(run_id)
            spine_path = locator.events_path(run_id)

            # The agent.run() path doesn't call RunTerminalizer, so
            # journal.json is not auto-flushed. Run the fold deriver
            # ourselves from the spine ledger to materialise it.
            spine_events = _read_spine_records(spine_path) if spine_path.exists() else []
            StepTreeFoldDeriver(
                run_id=run_id,
                run_dir=run_dir,
                spine_path=spine_path,
                session=bound.bridge,
                agent_role=role.role,
                strategy_key="solo",
                plan_ref="",
                objective="请用 bash 工具运行 echo hello 并把结果告诉我。",
            ).derive(spine_events)

            return result.status, run_dir
        finally:
            await ctx.dispose()

    try:
        status, run_dir = asyncio.run(_drive())
    except Exception as exc:
        msg = str(exc)
        print(f"\n[think_llm_journal e2e] raised: {type(exc).__name__}: {msg}")
        if "PlanLiftError" in msg or "validate_profile_plans" in msg:
            pytest.skip(
                "web-standard profile cannot boot in this sandbox (pre-existing "
                "plan-validation defect); structural assertion cannot run."
            )
        if "requires a bound Session" in msg:
            pytest.skip(
                f"e2e Session cannot be bound in this sandbox: {type(exc).__name__}: {msg}."
            )
        if "PlanResolution" in msg or "plan-resolution" in msg:
            pytest.skip(
                f"web-standard profile plan-resolution blocked: {type(exc).__name__}: {msg}."
            )
        # No catch-all: anything else this path raises is a real defect in the
        # emit → ledger → fold chain and must fail the gate, not skip it.
        raise

    # ── Result terminal outcome ───────────────────────────────────────
    assert status is TaskStatus.COMPLETED, (
        f"expected terminal outcome = success (TaskStatus.COMPLETED); "
        f"got status={status!r}. The original journal-empty regression "
        f"surfaced as a non-COMPLETED terminal status because the LLM "
        f"call boundary dropped its spine emit and the run never converged."
    )

    # ── Read the journal ──────────────────────────────────────────────
    journal_path = run_dir / "journal.json"
    assert journal_path.exists(), (
        f"journal.json must exist after the run at {journal_path}; "
        f"the StepTreeFoldDeriver writes it during derive()."
    )
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert isinstance(journal, dict)
    assert journal.get("run_id") == run_id

    steps = journal.get("steps")
    assert isinstance(steps, list) and len(steps) >= 1, (
        f"journal must contain >=1 step, got steps={steps!r}"
    )

    # ── thinking: reasoning + prompt_tokens ──────────────────────────
    thinking_steps = [s for s in steps if isinstance(s.get("thinking"), dict) and s["thinking"]]
    assert thinking_steps, "at least one step must have a non-empty thinking block"
    assert any(
        bool(t.get("reasoning"))
        and isinstance(t.get("prompt_tokens"), int)
        and t["prompt_tokens"] > 0
        for s in thinking_steps
        for t in [s["thinking"]]
    ), (
        f"at least one thinking block must have non-empty reasoning and "
        f"prompt_tokens > 0; got thinking={[s['thinking'] for s in thinking_steps]!r}"
    )

    # ── tool_call: name=bash, arguments contain "echo hello" ─────────
    tool_call_steps = [s for s in steps if isinstance(s.get("tool_call"), dict) and s["tool_call"]]
    assert tool_call_steps, "at least one step must have a non-empty tool_call block"
    assert any(
        tc.get("name") == "bash"
        and "echo hello" in json.dumps(tc.get("arguments") or {}, ensure_ascii=False)
        for s in tool_call_steps
        for tc in [s["tool_call"]]
    ), (
        f"at least one tool_call must be name='bash' with arguments "
        f'containing "echo hello"; got tool_calls='
        f"{[s['tool_call'] for s in tool_call_steps]!r}"
    )

    # ── tool_result: stdout_head contains "hello" ────────────────────
    tool_result_steps = [
        s for s in steps if isinstance(s.get("tool_result"), dict) and s["tool_result"]
    ]
    assert tool_result_steps, "at least one step must have a non-empty tool_result block"
    assert any(
        "hello" in (tr.get("stdout_head") or "")
        for s in tool_result_steps
        for tr in [s["tool_result"]]
    ), (
        f"at least one tool_result must have stdout_head containing "
        f'"hello"; got tool_results='
        f"{[s['tool_result'] for s in tool_result_steps]!r}"
    )

    # ── native LLM payload: raw_response_preview OR prompt_preview ──
    # The journal fold stashes the LLM's native text under
    # step.thinking.raw_response_preview (assistant content kept at
    # 600 chars by the fold binding). For the bash-tool-call step the
    # raw_response_preview is empty (assistant content == "" when the
    # response declares tool_calls); the final assistant-reply step
    # populates it. Assert at least one step has raw_response_preview
    # non-empty OR the spine's llm.call.start carries prompt_preview.
    has_native_in_journal = any(
        bool((s.get("thinking") or {}).get("raw_response_preview")) for s in steps
    )

    # ── Read the spine ledger and assert the three anchors ──────────
    spine_path = run_dir / f"{run_id}.spine.jsonl"
    assert spine_path.exists(), f"spine ledger must exist at {spine_path} after the run"
    spine_records = _read_spine_records(spine_path)
    assert spine_records, "spine ledger must not be empty after the run"

    llm_call_starts = [r for r in spine_records if r.get("execution_point") == "llm.call.start"]
    assert llm_call_starts, "at least one spine event with execution_point == 'llm.call.start'"
    # ``llm.call.start`` carries the request side (model + prompt preview);
    # usage arrives on ``llm.call.end``, which is asserted below.
    assert any(
        r.get("payload", {}).get("model") == "scripted-echo-llm"
        and r.get("payload", {}).get("prompt_preview")
        for r in llm_call_starts
    ), (
        f"at least one llm.call.start must carry model='scripted-echo-llm' "
        f"and a non-empty prompt_preview; "
        f"got events={llm_call_starts!r}"
    )

    llm_call_ends = [r for r in spine_records if r.get("execution_point") == "llm.call.end"]
    assert llm_call_ends, "at least one spine event with execution_point == 'llm.call.end'"
    assert any(
        r.get("payload", {}).get("model") == "scripted-echo-llm"
        and r.get("payload", {}).get("outcome") == "success"
        and r.get("payload", {}).get("completion_tokens", 0) > 0
        for r in llm_call_ends
    ), (
        f"at least one llm.call.end must carry model='scripted-echo-llm', "
        f"outcome='success', and completion_tokens > 0; "
        f"got events={llm_call_ends!r}"
    )

    # ── reasoning channel: the native thinking text is a logged fact ───
    # ``llm.stream.token`` with ``channel_kind == "reasoning"`` is what the fold
    # concatenates into ``step.thinking.reasoning``; a non-streaming call
    # boundary loses it, which is how "no model thinking in the journal" hid.
    reasoning_tokens = [
        r
        for r in spine_records
        if r.get("execution_point") == "llm.stream.token"
        and r.get("payload", {}).get("channel_kind") == "reasoning"
        and (r.get("payload", {}).get("text_delta") or "")
    ]
    assert reasoning_tokens, (
        "at least one llm.stream.token with channel_kind='reasoning' and a "
        f"non-empty text_delta; got {len(spine_records)} spine events"
    )

    # ``phase.think.fold`` is cursor-derived and patches the step's thinking
    # model; its absence means the cursor binding at run setup went missing.
    think_folds = [r for r in spine_records if r.get("execution_point") == "phase.think.fold"]
    assert think_folds, "at least one phase.think.fold spine event (cursor-derived)"

    step_tool_call_records = [
        r for r in spine_records if r.get("execution_point") == "step.tool_call.record"
    ]
    assert step_tool_call_records, (
        "at least one spine event with execution_point == 'step.tool_call.record'"
    )
    assert any(
        r.get("payload", {}).get("tool_name") == "bash"
        and r.get("payload", {}).get("invocation_id") == "call_echo_1"
        for r in step_tool_call_records
    ), (
        f"at least one step.tool_call.record must carry tool_name='bash' "
        f"and invocation_id='call_echo_1'; got events="
        f"{step_tool_call_records!r}"
    )

    # Final cross-anchor check: the prompt_preview from llm.call.start
    # is the "native" raw LLM payload that proves the LLM boundary
    # forwarded the state/session correctly.
    if not has_native_in_journal:
        # The journal step's raw_response_preview may be empty for
        # tool-call steps (assistant content was empty). Fall back to
        # the spine's prompt_preview as the canonical "native" LLM
        # payload that the journal must reflect.
        has_native_in_spine = any(
            r.get("payload", {}).get("prompt_preview") for r in llm_call_starts
        )
        assert has_native_in_spine, (
            "raw_response_preview is empty in journal AND no "
            "llm.call.start prompt_preview on the spine — neither the "
            "journal fold nor the spine carries the raw LLM payload."
        )
