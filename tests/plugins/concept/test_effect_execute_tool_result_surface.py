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
    """Effect gateway seam returning a canned Observation."""

    def __init__(self, output: Any) -> None:
        self._output = output

    async def execute(self, envelope: Any, policy: Any) -> Any:
        return self._output


class _Runtime:
    """Duck-typed ``_NodeRuntimeView`` exposing only what the node reads."""

    def __init__(self, *, writer: Any, gateway: Any, state: Any) -> None:
        self.writer = writer
        self.effect_gateway = gateway
        self.state = state


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


def _envelope() -> Any:
    from lca.contracts.protocols.act.command.envelope import (
        CapabilityGrant,
        mint_envelope,
    )

    decision = _decision()
    return mint_envelope(
        plan_ref="act.subgraph",
        scope_ref="act.envelope",
        decision=decision,
        provider="effect.body",
        grant=CapabilityGrant(capability="body.act", scope="run", effect_class="tools"),
        idempotency_key="act.subgraph:act.envelope:decision_test",
        metadata={
            "effect_class": "tools",
            "operation": "body.act",
            "state": None,
            "decision": decision,
        },
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
