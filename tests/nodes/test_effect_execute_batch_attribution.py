"""Tests for effect.execute batch attribution completeness (INV-PARALLEL-02).

Ensures that when Cognition declares multiple tool calls in a Decision,
EVERY declared call_id is answered in Session with a surface/tool_result row,
even if:
1. Dispatch raises an exception (gateway crash, sandbox timeout, etc.)
2. Batch observation extra is partially missing
3. Batch observation is un-aggregated
"""

from typing import Any

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.harness.act.effect_receipt import EffectOutcome
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    ToolCall,
)
from lca.contracts.protocols.act.command.envelope import (
    BudgetReservation,
    CapabilityGrant,
    ToolsEnvelopeMeta,
    mint_envelope,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.concept.effect.execute import EffectExecuteExecutor


class _FakeWriter:
    def __init__(self) -> None:
        self.tool_results: list[dict[str, Any]] = []

    def append_tool_result(self, **kwargs: Any) -> None:
        self.tool_results.append(kwargs)


class _RaisingGateway:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def execute(self, envelope: Any, policy: Any, **kwargs: Any) -> Any:
        raise self._exc


class _FakeGateway:
    def __init__(self, output: Any) -> None:
        self._output = output

    async def execute(self, envelope: Any, policy: Any, **kwargs: Any) -> Any:
        return self._output


class _Runtime:
    def __init__(self, writer: Any, gateway: Any) -> None:
        self.writer = writer
        self.effect_gateway = gateway
        self.state = None


def _ctx(writer: Any, gateway: Any) -> NodeContext:
    return NodeContext(
        runtime=_Runtime(writer, gateway),
        budget={},
        metadata={"plan_ref": "act.subgraph", "node_id": "effect.execute"},
    )


def _multi_call_decision() -> Decision:
    return Decision(
        decision_id="decision_multi_batch",
        action_type=ActionType.USE_TOOL,
        rationale="parallel role card search",
        confidence=1.0,
        tool_calls=[
            ToolCall(call_id="call_news", tool_name="list_role_cards", arguments={"query": "news"}),
            ToolCall(
                call_id="call_jour", tool_name="list_role_cards", arguments={"query": "journalist"}
            ),
            ToolCall(
                call_id="call_rese", tool_name="list_role_cards", arguments={"query": "research"}
            ),
        ],
    )


def _envelope_for_call(decision: Decision, call_index: int = 0) -> Any:
    tc = decision.tool_calls[call_index]
    return mint_envelope(
        plan_ref="act.subgraph",
        scope_ref="act.envelope",
        decision=decision,
        provider="effect.body",
        grant=CapabilityGrant(capability="body.act", scope="run", effect_class="tools"),
        budget_reservation=BudgetReservation(tool_calls=1),
        idempotency_key=f"dec:{tc.call_id}",
        metadata=ToolsEnvelopeMeta(
            effect_class="tools",
            operation="body.act",
            tool_call_id=tc.call_id,
            tool_call_index=call_index,
            decision_ref=decision.decision_id,
        ).to_metadata(),
    )


@pytest.mark.asyncio
async def test_effect_execute_multi_call_raising_gateway_answers_all_calls() -> None:
    """INV-PARALLEL-02: When gateway fails for a multi-call decision, ALL declared
    call_ids must receive error tool_result rows in Session.
    """
    decision = _multi_call_decision()
    envelope = _envelope_for_call(decision, 0)
    writer = _FakeWriter()
    gateway = _RaisingGateway(RuntimeError("Sandbox connection failed"))

    output = await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": envelope, "decision": decision, "state": None}),
    )

    assert output.port_values["receipts"][0].outcome is EffectOutcome.FAILED
    assert len(writer.tool_results) == 3, f"Expected 3 results, got {len(writer.tool_results)}"
    recorded_ids = [row["call_id"] for row in writer.tool_results]
    assert recorded_ids == ["call_news", "call_jour", "call_rese"]
    for row in writer.tool_results:
        assert "Sandbox connection failed" in str(row["error"])


@pytest.mark.asyncio
async def test_effect_execute_multi_call_partial_batch_fills_missing_calls() -> None:
    """INV-PARALLEL-02: When batch observation only packed 1 of 3 calls, the missing 2
    must be filled with error rows so no call_id hangs in LLM history.
    """
    decision = _multi_call_decision()
    envelope = _envelope_for_call(decision, 0)
    writer = _FakeWriter()
    obs_partial = Observation(
        observation_id="obs_part",
        success=True,
        payload="batch part",
        extra={
            "tool_results": [
                {
                    "call_id": "call_news",
                    "tool_name": "list_role_cards",
                    "observation": Observation(
                        observation_id="obs_1", success=True, payload="news cards"
                    ),
                }
            ]
        },
    )
    gateway = _FakeGateway({"result": obs_partial, "invocation_id": "inv"})

    await EffectExecuteExecutor().node_execute(
        _ctx(writer, gateway),
        NodeInput(port_values={"envelope": envelope, "decision": decision, "state": None}),
    )

    assert len(writer.tool_results) == 3
    recorded_ids = [row["call_id"] for row in writer.tool_results]
    assert recorded_ids == ["call_news", "call_jour", "call_rese"]
    assert writer.tool_results[0]["error"] is None
    assert "news cards" in writer.tool_results[0]["content"]
    assert writer.tool_results[1]["error"] is not None
    assert writer.tool_results[2]["error"] is not None
