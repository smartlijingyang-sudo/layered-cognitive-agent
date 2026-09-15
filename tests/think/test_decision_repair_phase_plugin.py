"""Tests for phase.think.decision.repair plugin.

Verifies the typed ``think.decision.repair`` node that lifts the
truncated-JSON / unknown-tool / schema-repair work into a typed
boundary between ``think.decision.parse`` and ``think.gate``.

Spec: ``docs/superpowers/specs/2026-09-15-pr3.8-borrowed-nodes-design.md``
§2.3 + ADR-0047 wire-block split.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.think.decision_repair import ThinkDecisionRepairExecutor


def _ctx(runtime: Mapping[str, Any] | None = None) -> NodeContext:
    """Minimal NodeContext; the repair node only reads ``runtime['tools']``."""
    return NodeContext(runtime=dict(runtime or {}), budget={}, metadata={})


class _FakeTool:
    """Typed stand-in for the ``Tool`` protocol.

    Only ``name`` and ``parameters`` are exercised by the repair
    node, so the rest of the protocol surface is left undefined.
    """

    def __init__(self, name: str, parameters: Mapping[str, Any]) -> None:
        self.name = name
        self.parameters = parameters


class _FakeRegistry:
    """Minimal ``ToolRegistry`` shape: ``register`` + ``get``.

    The repair node only calls ``get``; ``register`` is provided so
    the fixture also matches the registered protocols at runtime.
    """

    def __init__(self, tools: dict[str, _FakeTool]) -> None:
        self._tools = dict(tools)

    def register(self, tool: _FakeTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> _FakeTool | None:
        return self._tools.get(name)


# Schema for the ``echo`` tool used by most tests. Mirrors the
# OpenAI function-calling JSON Schema shape that the Tool protocol
# stores on ``parameters``. ``count`` is required so the truncated
# payload (which drops ``count`` during JSON truncation) actually
# fails the schema check and triggers the repair path.
_ECHO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["text", "count"],
}


def _registry_with_echo() -> _FakeRegistry:
    return _FakeRegistry({"echo": _FakeTool("echo", _ECHO_SCHEMA)})


def _decision(*tool_calls: ToolCall) -> Decision:
    """Wrap ``ToolCall`` list into a minimal valid ``Decision``."""
    return Decision(
        decision_id="dec_test",
        action_type="use_tool",
        rationale="test",
        confidence=1.0,
        tool_calls=list(tool_calls),
    )


def _call(
    *,
    name: str = "echo",
    arguments: Mapping[str, Any] | None = None,
    call_id: str = "call_1",
) -> ToolCall:
    return ToolCall(call_id=call_id, tool_name=name, arguments=dict(arguments or {}))


@pytest.mark.asyncio
async def test_decision_repair_well_formed_passes_through_to_gate() -> None:
    """Happy path: schema-valid arguments → ``decision_ok`` → ``think.gate``."""
    executor = ThinkDecisionRepairExecutor()
    decision = _decision(_call(arguments={"text": "hello", "count": 1}))

    output = await executor.node_execute(
        _ctx({"tools": _registry_with_echo()}),
        NodeInput(port_values={"decision": decision}),
    )

    forwarded: Decision = output.port_values["decision"]
    routing: RoutingDecision = output.port_values["routing"]

    # The forwarded Decision is the original instance — no mutation.
    assert forwarded is decision
    assert routing.next_node == "think.gate"
    assert routing.next_hint == "decision_ok"
    assert routing.should_terminate is False
    assert routing.action_type == ActionType.RESPOND


@pytest.mark.asyncio
async def test_decision_repair_truncated_json_repairs_then_forwards_to_gate() -> None:
    """Truncated JSON: repair closes braces and forwards as ``decision_repaired``."""
    executor = ThinkDecisionRepairExecutor()
    # The raw preview represents what the LLM emitted before the
    # adapter truncated it; the parsed ``arguments`` dict is the
    # broken best-effort the upstream parser produced. The repair
    # path reads the raw preview from ``Decision.extra`` (per
    # ADR-0047 wire-block structure), closes braces, re-parses, and
    # re-validates against the schema.
    raw_preview = '{"text": "hello", "count": 1'
    call = ToolCall(
        call_id="call_truncated",
        tool_name="echo",
        arguments={"text": "hello"},  # best-effort: missing ``count``
    )
    decision = _decision(call)
    decision.extra["tool_wire_raw_preview"] = raw_preview

    output = await executor.node_execute(
        _ctx({"tools": _registry_with_echo()}),
        NodeInput(port_values={"decision": decision}),
    )

    forwarded: Decision = output.port_values["decision"]
    routing: RoutingDecision = output.port_values["routing"]

    assert routing.next_node == "think.gate"
    assert routing.next_hint == "decision_repaired"
    assert routing.should_terminate is False

    # The repaired call now carries the full ``count`` field that
    # the truncated JSON omitted at parse time.
    assert forwarded is not decision  # repair produced a fresh Decision
    repaired_call = forwarded.tool_calls[0]
    assert repaired_call.arguments == {"text": "hello", "count": 1}


@pytest.mark.asyncio
async def test_decision_repair_unknown_tool_name_rejects_to_route_decide() -> None:
    """Unknown tool_name → ``decision_rejected_schema`` → ``think.route.decide``.

    Per spec §2.3 the repair node never silently passes a malformed
    Decision downstream. When the registry does not recognize a
    tool name, the node forwards the original Decision unchanged
    (so diagnostics can read it) and re-routes to
    ``think.route.decide`` for a full re-reason.
    """
    executor = ThinkDecisionRepairExecutor()
    decision = _decision(_call(name="mystery_tool", arguments={"text": "x", "count": 1}))

    output = await executor.node_execute(
        _ctx({"tools": _registry_with_echo()}),
        NodeInput(port_values={"decision": decision}),
    )

    forwarded: Decision = output.port_values["decision"]
    routing: RoutingDecision = output.port_values["routing"]

    # Original is forwarded unchanged for diagnostics.
    assert forwarded is decision
    assert routing.next_node == "think.route.decide"
    assert routing.next_hint == "decision_rejected_schema"
    assert routing.should_terminate is False


@pytest.mark.asyncio
async def test_decision_repair_irreparable_arguments_rejects_to_route_decide() -> None:
    """Repair attempt fails → ``decision_rejected_truncated`` → ``think.route.decide``.

    The raw preview is not closeable with the deterministic
    brace-balance repair (unbalanced closers, no opener) so the
    node falls back to the truncated-reject path. Per spec §2.3 the
    node must never silently pass an unparseable / schema-invalid
    payload to Gate.
    """
    executor = ThinkDecisionRepairExecutor()
    raw_preview = '{"text": "hello"'  # missing closer; repairable
    # Use a registry whose schema does not match the repairable
    # payload so the schema check fails after the brace fix.
    bad_schema_registry = _FakeRegistry(
        {"echo": _FakeTool("echo", {"type": "object", "required": ["never_present"]})}
    )

    decision = _decision(
        ToolCall(
            call_id="call_bad",
            tool_name="echo",
            arguments={"text": "hello"},
        )
    )
    decision.extra["tool_wire_raw_preview"] = raw_preview

    output = await executor.node_execute(
        _ctx({"tools": bad_schema_registry}),
        NodeInput(port_values={"decision": decision}),
    )

    forwarded: Decision = output.port_values["decision"]
    routing: RoutingDecision = output.port_values["routing"]

    # Original is forwarded unchanged so diagnostics see the
    # unparseable payload; Gate is bypassed.
    assert forwarded is decision
    assert routing.next_node == "think.route.decide"
    assert routing.next_hint == "decision_rejected_truncated"


@pytest.mark.asyncio
async def test_decision_repair_is_idempotent() -> None:
    """Same ``decision`` input → identical ``(decision, routing)`` across calls.

    C9 contract. Same executor instance is called twice with the
    same input, then two fresh executor instances are called with
    the same input. All four outputs must agree on every observable
    field (per-call ``decision_id`` is part of the input, not the
    output, so equality is content-based).
    """
    executor = ThinkDecisionRepairExecutor()
    decision = _decision(_call(arguments={"text": "hello", "count": 1}))
    port_values = {
        "decision": decision,
    }
    runtime = {"tools": _registry_with_echo()}

    out_a = await executor.node_execute(_ctx(runtime), NodeInput(port_values=port_values))
    out_b = await executor.node_execute(_ctx(runtime), NodeInput(port_values=port_values))
    assert out_a.port_values["routing"] == out_b.port_values["routing"]
    assert out_a.port_values["decision"] is out_b.port_values["decision"]

    out_c = await ThinkDecisionRepairExecutor().node_execute(
        _ctx(runtime), NodeInput(port_values=port_values)
    )
    out_d = await ThinkDecisionRepairExecutor().node_execute(
        _ctx(runtime), NodeInput(port_values=port_values)
    )
    assert out_c.port_values["routing"] == out_d.port_values["routing"]
    assert out_c.port_values["decision"] is out_d.port_values["decision"]


@pytest.mark.asyncio
async def test_decision_repair_empty_decision_returns_empty_output() -> None:
    """``decision is None`` or has no tool_calls → empty ``NodeOutput``.

    The bundle edge decides routing for the empty case; the repair
    node stays out of the way so the bundle predicate on the
    ``parse → repair`` edge can re-route to ``think.route.decide``
    when the LLM chose ``respond`` / ``ask_user`` (Decision with
    no tool_calls) or when ``decision.parse`` returned ``None``.
    """
    executor = ThinkDecisionRepairExecutor()

    # ``None`` decision.
    out_none = await executor.node_execute(
        _ctx({"tools": _registry_with_echo()}),
        NodeInput(port_values={"decision": None}),
    )
    assert out_none.port_values == {}

    # Decision with an empty tool_calls list.
    empty_decision = _decision()
    out_empty = await executor.node_execute(
        _ctx({"tools": _registry_with_echo()}),
        NodeInput(port_values={"decision": empty_decision}),
    )
    assert out_empty.port_values == {}


@pytest.mark.asyncio
async def test_decision_repair_no_registry_passes_known_calls() -> None:
    """No ``tools`` registry on ``runtime`` → unknown-name check is skipped.

    Per ADR-0047's wire-block split, schema repair lives here and
    wire-level rejection lives in Body. Without a registry the
    repair node cannot tell whether a name is unknown, so it lets
    the call through and emits ``decision_ok`` — the wire gate at
    Body remains the safety net for unknown-tool-name blocking.
    """
    executor = ThinkDecisionRepairExecutor()
    decision = _decision(_call(arguments={"text": "hello", "count": 1}))

    output = await executor.node_execute(
        _ctx(),  # no ``tools`` key on runtime
        NodeInput(port_values={"decision": decision}),
    )

    forwarded: Decision = output.port_values["decision"]
    routing: RoutingDecision = output.port_values["routing"]
    assert forwarded is decision
    assert routing.next_node == "think.gate"
    assert routing.next_hint == "decision_ok"


@pytest.mark.asyncio
async def test_decision_repair_empty_tool_name_rejects() -> None:
    """``tool_name == ""`` is rejected even without a registry.

    Empty / whitespace-only tool names are always rejected because
    they can never be a valid schema-bearing payload — no registry
    is needed to detect the empty-string case.
    """
    executor = ThinkDecisionRepairExecutor()
    decision = _decision(_call(name="", arguments={"text": "hello", "count": 1}))

    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": decision}),
    )

    routing: RoutingDecision = output.port_values["routing"]
    assert routing.next_node == "think.route.decide"
    assert routing.next_hint == "decision_rejected_schema"


@pytest.mark.asyncio
async def test_decision_repair_multi_call_one_repair_emits_repaired_decision() -> None:
    """One repair + one already-valid call → ``decision_repaired`` with a fresh list.

    The repair path must preserve the order of the original
    ``tool_calls`` list and only replace the entries whose
    arguments were repaired. This pins the multi-call contract:
    a mixed payload produces a repaired Decision with the same
    length and ordering as the input.
    """
    executor = ThinkDecisionRepairExecutor()
    valid_call = _call(
        call_id="call_valid",
        name="echo",
        arguments={"text": "fine", "count": 7},
    )
    truncated_call = ToolCall(
        call_id="call_truncated",
        tool_name="echo",
        arguments={"text": "fine"},  # missing ``count`` triggers repair
    )
    decision = _decision(valid_call, truncated_call)
    decision.extra["tool_wire_raw_preview"] = '{"text": "fine", "count": 7'

    output = await executor.node_execute(
        _ctx({"tools": _registry_with_echo()}),
        NodeInput(port_values={"decision": decision}),
    )

    forwarded: Decision = output.port_values["decision"]
    routing: RoutingDecision = output.port_values["routing"]

    assert routing.next_hint == "decision_repaired"
    assert forwarded is not decision
    assert len(forwarded.tool_calls) == 2
    # First call: untouched (already valid).
    assert forwarded.tool_calls[0] is valid_call
    assert forwarded.tool_calls[0].arguments == {"text": "fine", "count": 7}
    # Second call: repaired with the ``count`` field the truncation
    # had dropped.
    assert forwarded.tool_calls[1] is not truncated_call
    assert forwarded.tool_calls[1].arguments == {"text": "fine", "count": 7}
