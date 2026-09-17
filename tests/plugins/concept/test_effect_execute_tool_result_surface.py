"""Regression: ``effect.execute`` must persist ``surface/tool_result``.

Root cause (run_5857095cb3e9, "What's the weather like in Beijing?"):
the model called the ``search`` tool 20 times before answering. It was
not being stubborn — it literally could not see any tool result.

The think side (``llm.call``) appends ``surface/assistant_message`` to
the Session, so ``derive_messages()`` grows one
``role=assistant tool_calls=[...]`` row per round. The act side never
appended the matching ``role=tool`` row:

  - the declarative path is ``effect.execute`` →
    ``RegistryEffectDispatcher`` → handler → ``SafeExecutor``;
  - ``SafeExecutor`` calls ``commit_body_tool_execute_end(...)`` without
    a ``session`` argument, so that function's
    ``if session is None: return None`` guard makes it a silent no-op;
  - ``effect.execute`` only put an ``EffectReceipt`` on the in-memory
    port registry and never touched the journal.

So the model saw its own tool calls unanswered and rationally retried.

These tests pin the contract that closes the loop: the side-effect
boundary node owns the model-visible append, mirroring ``llm.call``.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.atoms.enums.enums import ActionType, ContentType
from lca.contracts.harness.act.effect_receipt import EffectOutcome
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    ToolCall,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.concept.effect.execute import EffectExecuteExecutor


class _FakeWriter:
    """Records ``append_tool_result`` calls the way RunSessionWriter would."""

    def __init__(self) -> None:
        self.tool_results: list[dict[str, Any]] = []

    def append_tool_result(self, **kwargs: Any) -> None:
        self.tool_results.append(kwargs)


class _FakeGateway:
    """Effect gateway seam returning a canned Observation.

    Signature matches ``EffectDispatcher.execute(envelope, policy, *,
    decision=..., state=...)`` (ADR-0235 / PR-5): a narrower stub makes
    the node's own ``except Exception`` swallow a TypeError and the test
    passes while nothing is appended.
    """

    def __init__(self, output: Any) -> None:
        self._output = output

    async def execute(self, envelope: Any, policy: Any, **kwargs: Any) -> Any:
        return self._output


class _RaisingGateway:
    """Gateway seam that fails the dispatch outright."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(self, envelope: Any, policy: Any, **kwargs: Any) -> Any:
        raise self._exc


class _StubTool:
    """Minimal ``Tool`` for the batch executor's registry lookup."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.description = name
        self.parameters: dict[str, Any] = {}
        self.is_idempotent = True


class _StubRegistry:
    def __init__(self, *names: str) -> None:
        self._tools = {name: _StubTool(name) for name in names}

    def get(self, name: str) -> Any:
        return self._tools.get(name)


class _StubSafeExecutor:
    """Returns a deterministic per-call Observation, echoing its arguments."""

    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.invocation_ids: list[str] = []

    async def execute(
        self,
        tool: Any,
        args: Any,
        retry_policy: Any,
        cache_config: Any,
        invocation_id: str = "",
    ) -> Observation:
        self.invocation_ids.append(invocation_id)
        if self._fail:
            return Observation(
                observation_id=f"obs_{invocation_id}",
                success=False,
                payload=None,
                error="sandbox timed out after 33s",
                tool_call_id=invocation_id,
            )
        return Observation(
            observation_id=f"obs_{invocation_id}",
            success=True,
            payload=f"{tool.name}:{args.get('skill_id', args)}",
            tool_call_id=invocation_id,
        )


class _Runtime:
    """Duck-typed ``_NodeRuntimeView`` exposing only what the node reads."""

    def __init__(self, *, writer: Any, gateway: Any, state: Any) -> None:
        self.writer = writer
        self.effect_gateway = gateway
        self.state = state

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def _decision() -> Decision:
    return Decision(
        decision_id="decision_test",
        action_type=ActionType.USE_TOOL,
        rationale="need weather",
        confidence=1.0,
        tool_calls=[
            ToolCall(
                call_id="toolu_real_call_id",
                tool_name="search",
                arguments={"query": "Beijing weather"},
            )
        ],
    )


def _mint(decision: Decision, call_index: int = 0) -> Any:
    """Mint one envelope the way ``act.envelope`` does, call id included."""
    from lca.contracts.protocols.act.command.envelope import (
        CapabilityGrant,
        mint_envelope,
    )

    return mint_envelope(
        plan_ref="act.subgraph",
        scope_ref="act.envelope",
        decision=decision,
        provider="effect.body",
        grant=CapabilityGrant(capability="body.act", scope="run", effect_class="tools"),
        idempotency_key=f"act.subgraph:act.envelope:{decision.decision_id}:{call_index}",
        metadata={
            "effect_class": "tools",
            "operation": "body.act",
            "state": None,
            "decision": decision,
            "tool_call_index": call_index,
            "tool_call_id": decision.tool_calls[call_index].call_id,
        },
    )


def _envelope() -> Any:
    return _mint(_decision())


def _multi_call_decision() -> Decision:
    """The shape ``run_71456ce99914`` actually produced: two calls in one turn."""
    return Decision(
        decision_id="decision_multi",
        action_type=ActionType.USE_TOOL,
        rationale="activate both skills",
        confidence=1.0,
        tool_calls=[
            ToolCall(
                call_id="toolu_office",
                tool_name="activate_skill",
                arguments={"skill_id": "officecli"},
            ),
            ToolCall(
                call_id="toolu_pdf",
                tool_name="activate_skill",
                arguments={"skill_id": "anthropics-skills-pdf"},
            ),
        ],
    )


def _ctx(writer: Any, gateway: Any) -> NodeContext:
    return NodeContext(
        runtime=_Runtime(writer=writer, gateway=gateway, state=None),
        budget={},
        metadata={"plan_ref": "act.subgraph", "node_id": "effect.execute"},
    )


@pytest.mark.asyncio
async def test_effect_execute_appends_tool_result_surface() -> None:
    """A successful tool call must produce a ``surface/tool_result`` row.

    Without this append the model never sees the result and retries the
    same tool call indefinitely.
    """
    obs = Observation(
        observation_id="obs_1",
        success=True,
        payload="Beijing: 22C sunny",
        content_type=ContentType.TEXT,
        tool_call_id="toolu_real_call_id",
    )
    writer = _FakeWriter()
    gateway = _FakeGateway({"result": obs, "invocation_id": "act.subgraph:inv"})

    output = await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": _envelope()}),
    )

    assert writer.tool_results, (
        "effect.execute must append surface/tool_result — the model "
        "cannot see tool output unless the side-effect boundary writes it"
    )
    assert output.port_values["receipts"][0].outcome is EffectOutcome.SUCCEEDED


@pytest.mark.asyncio
async def test_appended_call_id_matches_assistant_tool_call_id() -> None:
    """The appended ``call_id`` must be the OpenAI ``call_id``, not the idempotency key.

    ``derive_messages`` orphan-drops any ``role=tool`` row whose
    ``tool_call_id`` was not declared by a preceding
    ``assistant.tool_calls[].id`` (the id written by ``llm.call``). The
    envelope's ``idempotency_key`` is ``plan:node:decision_id`` and does
    NOT match, so using it would re-break the loop even after the append.
    """
    obs = Observation(
        observation_id="obs_1",
        success=True,
        payload="ok",
        content_type=ContentType.TEXT,
        tool_call_id="toolu_real_call_id",
    )
    writer = _FakeWriter()
    gateway = _FakeGateway({"result": obs, "invocation_id": "inv"})

    await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": _envelope()}),
    )

    row = writer.tool_results[0]
    assert row["call_id"] == "toolu_real_call_id"
    assert row["call_id"] != "act.subgraph:act.envelope:decision_test"


@pytest.mark.asyncio
async def test_appended_content_is_clean_payload_not_repr() -> None:
    """Model-visible content must be the payload text, never ``repr(Observation)``.

    ``EffectReceipt.output_ref`` is ``str(result)`` — a Python repr. That
    is fine as an operator-facing audit pointer but garbage as model
    context, so the surface row must carry the payload instead.
    """
    obs = Observation(
        observation_id="obs_1",
        success=True,
        payload={"text": "Beijing 22C"},
        content_type=ContentType.STRUCTURED,
        tool_call_id="toolu_real_call_id",
    )
    writer = _FakeWriter()
    gateway = _FakeGateway({"result": obs, "invocation_id": "inv"})

    await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": _envelope()}),
    )

    content = writer.tool_results[0]["content"]
    assert "Observation(" not in content
    assert "Beijing 22C" in content


@pytest.mark.asyncio
async def test_failed_tool_still_appends_so_model_sees_error() -> None:
    """A failed Observation must still surface — a silent failure re-opens the retry loop."""
    obs = Observation(
        observation_id="obs_1",
        success=False,
        payload=None,
        content_type=ContentType.TEXT,
        error="upstream timeout",
        tool_call_id="toolu_real_call_id",
    )
    writer = _FakeWriter()
    gateway = _FakeGateway({"result": obs, "invocation_id": "inv"})

    await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": _envelope()}),
    )

    assert writer.tool_results
    row = writer.tool_results[0]
    assert row["error"] is not None
    assert "upstream timeout" in str(row["error"])


@pytest.mark.asyncio
async def test_unbound_writer_does_not_crash_execution() -> None:
    """No writer in runtime must not break the side effect itself.

    Older kernels and unit harnesses run ``effect.execute`` without a
    session-bound writer. The append is best-effort; the receipt is
    still produced so the graph keeps its control-flow contract.
    """
    obs = Observation(
        observation_id="obs_1",
        success=True,
        payload="ok",
        content_type=ContentType.TEXT,
        tool_call_id="toolu_real_call_id",
    )
    gateway = _FakeGateway({"result": obs, "invocation_id": "inv"})

    output = await EffectExecuteExecutor().node_execute(
        _ctx(None, gateway),
        NodeInput(port_values={"envelope": _envelope()}),
    )

    assert output.port_values["receipts"][0].outcome is EffectOutcome.SUCCEEDED


# ── Multi-call turns (run_71456ce99914) ──────────────────────────
#
# One model turn declared 2 ``activate_skill`` calls. Both executed and
# both results were recorded in the step ledger, yet neither reached the
# next request: ``_tool_call_id`` only resolved an id when the decision
# declared exactly one call, and the caller logged a warning and skipped
# the append. The model re-issued the identical pair, then guessed the
# attachment path and got ``file_not_found``.
#
# These tests drive the shipped seams end to end — the real
# ``ActEnvelopeExecutor`` mints the envelopes, the real
# ``ToolBatchExecutor`` produces the aggregate Observation, and the real
# ``EffectExecuteExecutor`` surfaces it. Production dispatches only
# ``envelopes[0]`` per act visit while the batch executes every declared
# call, so that is the shape under test.


async def _mint_via_node(decision: Decision) -> tuple[Any, ...]:
    from lca.nodes.act.envelope.envelope import ActEnvelopeExecutor

    out = await ActEnvelopeExecutor().node_execute(
        NodeContext(
            runtime=_Runtime(writer=None, gateway=None, state=None),
            budget={},
            metadata={"plan_ref": "act.subgraph", "node_id": "act.envelope"},
        ),
        NodeInput(port_values={"decision": decision, "state": None}),
    )
    return tuple(out.port_values["envelopes"])


async def _batch_aggregate(decision: Decision, *, fail: bool = False) -> Observation:
    from lca.cognition.body.tools.tool_batch_executor import ToolBatchExecutor

    executor = ToolBatchExecutor(_StubRegistry("activate_skill"), _StubSafeExecutor(fail=fail))
    return await executor.execute(decision.tool_calls)


@pytest.mark.asyncio
async def test_multi_call_turn_answers_every_declared_call_id() -> None:
    """N declared calls ⇒ N ``surface/tool_result`` rows, each with its own id."""
    decision = _multi_call_decision()
    envelopes = await _mint_via_node(decision)
    assert [e.metadata["tool_call_id"] for e in envelopes] == ["toolu_office", "toolu_pdf"]

    aggregate = await _batch_aggregate(decision)
    writer = _FakeWriter()
    gateway = _FakeGateway({"result": aggregate, "invocation_id": "inv"})

    await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": envelopes[0], "decision": decision, "state": None}),
    )

    assert [row["call_id"] for row in writer.tool_results] == ["toolu_office", "toolu_pdf"]
    by_id = {row["call_id"]: row["content"] for row in writer.tool_results}
    assert "officecli" in by_id["toolu_office"]
    assert "anthropics-skills-pdf" in by_id["toolu_pdf"]
    assert all(row["error"] is None for row in writer.tool_results)


@pytest.mark.asyncio
async def test_failed_batch_surfaces_the_classified_error_per_call() -> None:
    """A timed-out batch must hand the model the error text, per call.

    ``run_71456ce99914`` appended two zero-length ``role=tool`` rows for
    two ~33 s sandbox timeouts: an empty result is indistinguishable from
    an unanswered call, so the model kept guessing file paths.
    """
    decision = _multi_call_decision()
    aggregate = await _batch_aggregate(decision, fail=True)
    writer = _FakeWriter()
    gateway = _FakeGateway({"result": aggregate, "invocation_id": "inv"})

    await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": _mint(decision), "decision": decision, "state": None}),
    )

    assert [row["call_id"] for row in writer.tool_results] == ["toolu_office", "toolu_pdf"]
    for row in writer.tool_results:
        assert row["error"]["message"] == "sandbox timed out after 33s"


@pytest.mark.asyncio
async def test_dispatch_failure_still_answers_the_declared_call() -> None:
    """A gateway that raised owes the model an error row, not silence."""
    writer = _FakeWriter()
    gateway = _RaisingGateway(RuntimeError("未注册工具: activate_skill"))

    output = await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": _envelope()}),
    )

    assert output.port_values["receipts"][0].outcome is EffectOutcome.FAILED
    assert len(writer.tool_results) == 1
    row = writer.tool_results[0]
    assert row["call_id"] == "toolu_real_call_id"
    assert "未注册工具" in str(row["error"])


@pytest.mark.asyncio
async def test_unattributable_result_fails_loud() -> None:
    """No resolvable call id is a contract violation, not a warning to skip.

    Log-and-continue is what made the dropped results invisible for a
    whole run; the node must raise instead.
    """
    from lca.contracts.protocols.act.command.envelope import (
        CapabilityGrant,
        mint_envelope,
    )
    from lca.nodes.concept.effect.execute import ToolResultAttributionError

    decision = _decision()
    bare = mint_envelope(
        plan_ref="act.subgraph",
        scope_ref="act.envelope",
        decision=decision,
        provider="effect.body",
        grant=CapabilityGrant(capability="body.act", scope="run", effect_class="tools"),
        idempotency_key="act.subgraph:act.envelope:decision_test",
        metadata={"effect_class": "tools", "operation": "body.act", "decision": decision},
    )
    obs = Observation(
        observation_id="obs_1",
        success=True,
        payload="ok",
        content_type=ContentType.TEXT,
        tool_call_id=None,
    )
    writer = _FakeWriter()
    gateway = _FakeGateway({"result": obs, "invocation_id": "inv"})

    with pytest.raises(ToolResultAttributionError):
        await EffectExecuteExecutor().node_execute(
            _ctx(writer, gateway),
            NodeInput(port_values={"envelope": bare}),
        )
    assert writer.tool_results == []
