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
from lca.contracts.models.core.conversation.llm import LLMResponse, NativeToolCall
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.think.decision.parse import DecisionParseExecutor
from lca.nodes.think.decision_repair import ThinkDecisionRepairExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; the repair node reads the ``tools`` typed port."""
    return NodeContext(runtime={}, budget={}, metadata={})


def _input(decision: Decision | None = None, *, tools: Any | None = None) -> NodeInput:
    """Build a NodeInput with the ``decision`` + ``tools`` typed ports populated."""
    port_values: dict[str, Any] = {}
    if decision is not None:
        port_values["decision"] = decision
    if tools is not None:
        port_values["tools"] = tools
    return NodeInput(port_values=port_values)


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
        _ctx(),
        _input(decision, tools=_registry_with_echo()),
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
        _ctx(),
        _input(decision, tools=_registry_with_echo()),
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
        _ctx(),
        _input(decision, tools=_registry_with_echo()),
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
        _ctx(),
        _input(decision, tools=bad_schema_registry),
    )

    forwarded: Decision = output.port_values["decision"]
    routing: RoutingDecision = output.port_values["routing"]

    # Original is forwarded unchanged so diagnostics see the
    # unparseable payload; Gate is bypassed.
    assert forwarded is decision
    assert routing.next_node == "think.route.decide"
    assert routing.next_hint == "decision_rejected_truncated"


@pytest.mark.asyncio
async def test_incomplete_wire_passes_through_so_body_can_observe() -> None:
    """Truncated writeFile must reach Body, not skip act via re-route."""
    executor = ThinkDecisionRepairExecutor()
    write_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }
    registry = _FakeRegistry({"writeFile": _FakeTool("writeFile", write_schema)})
    decision = _decision(
        ToolCall(
            call_id="call_wf",
            tool_name="writeFile",
            arguments={},
            wire_status="incomplete",
            wire_reason="unterminated_or_truncated_json",
            wire_raw_preview='{"content": "from reportlab',
        )
    )

    output = await executor.node_execute(_ctx(), _input(decision, tools=registry))
    routing: RoutingDecision = output.port_values["routing"]
    forwarded: Decision = output.port_values["decision"]

    assert routing.next_hint == "decision_ok"
    assert forwarded.tool_calls[0].wire_status == "incomplete"


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
    registry = _registry_with_echo()
    inp = _input(decision, tools=registry)

    out_a = await executor.node_execute(_ctx(), inp)
    out_b = await executor.node_execute(_ctx(), inp)
    assert out_a.port_values["routing"] == out_b.port_values["routing"]
    assert out_a.port_values["decision"] is out_b.port_values["decision"]

    out_c = await ThinkDecisionRepairExecutor().node_execute(_ctx(), inp)
    out_d = await ThinkDecisionRepairExecutor().node_execute(_ctx(), inp)
    assert out_c.port_values["routing"] == out_d.port_values["routing"]
    assert out_c.port_values["decision"] is out_d.port_values["decision"]


@pytest.mark.asyncio
async def test_decision_repair_empty_decision_returns_empty_output() -> None:
    """``decision is None`` → empty ``NodeOutput``.

    The bundle edge decides routing for the truly empty case; the
    repair node stays out of the way so the bundle predicate on the
    ``parse → repair`` edge can re-route to ``think.route.decide``
    when ``decision.parse`` returned ``None``.

    A populated ``Decision`` with no ``tool_calls`` (a ``respond``
    or other non-use_tool action) is a different shape: ``repair``
    is a use_tool-only concern, so the node passes the carry-in
    ``decision`` through with ``decision_ok`` routing rather than
    emit an empty output. Clearing it would strip the outer plan's
    edge predicate (``decision.action_type == respond``) of the
    signal that lets the run complete — see the 2026-09-16
    act→think re-ask loop guard note.
    """
    executor = ThinkDecisionRepairExecutor()
    registry = _registry_with_echo()

    # ``None`` decision.
    out_none = await executor.node_execute(
        _ctx(),
        _input(decision=None, tools=registry),
    )
    assert out_none.port_values == {}

    # Decision with an empty tool_calls list — a ``respond`` action;
    # the executor must forward it (do not strip the carry-in signal).
    empty_decision = _decision()
    out_empty = await executor.node_execute(
        _ctx(),
        _input(empty_decision, tools=registry),
    )
    assert out_empty.port_values["decision"] is empty_decision
    routing = out_empty.port_values["routing"]
    assert routing.next_hint == "decision_ok"


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
        _ctx(),  # no ``tools`` typed port either
        _input(decision),
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
        _input(decision),
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
        _ctx(),
        _input(decision, tools=_registry_with_echo()),
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


# ── Regression: undecodable tool-call markup must re-ask, not answer ──────
#
# run_c6df7c01ccae: qwen3.7-plus returned finish_reason=stop with 15 completion
# tokens whose entire text was the trailing close of an invoke/parameter block.
# No native tool_calls, so the text was classified ``respond``, the fragment
# became ``response_text``, and the loop committed it as a successful final
# answer. run_b695b0b85115 lost a *well-formed* block the same way — the model
# asked for ``search_skill`` and the tool never ran.

_CLOSE_PARAM = "</" + "parameter>"
_CLOSE_FUNC = "</" + "function>"
_DEGENERATE = "`\n\n" + _CLOSE_PARAM + "\n" + _CLOSE_FUNC + "\n"
_WELL_FORMED = (
    "Now let me activate the PDF skill and generate the report.\n"
    '<tool_calls>\n<invoke name="echo">\n'
    '<parameter name="text">hi' + _CLOSE_PARAM + "\n"
    "</invoke>\n</tool_calls>"
)


def _response(text: str) -> LLMResponse:
    return LLMResponse(text=text, tool_calls=(), model="qwen3.7-plus", finish_reason="stop")


async def _parse(response: LLMResponse) -> Decision:
    output = await DecisionParseExecutor().node_execute(
        _ctx(),
        NodeInput(port_values={"state": _ctx(), "llm_response": response}),
    )
    decision = output.port_values.get("decision")
    assert isinstance(decision, Decision)
    return decision


@pytest.mark.asyncio
async def test_degenerate_markup_fragment_reroutes_instead_of_answering() -> None:
    decision = await _parse(_response(_DEGENERATE))

    assert decision.action_type == ActionType.USE_TOOL.value
    assert decision.response_text is None
    assert decision.tool_calls[0].tool_name == ""
    assert decision.tool_calls[0].wire_status == "incomplete"
    assert _CLOSE_PARAM in decision.tool_calls[0].wire_raw_preview

    output = await ThinkDecisionRepairExecutor().node_execute(
        _ctx(), _input(decision, tools=_registry_with_echo())
    )
    routing = output.port_values.get("routing")
    assert isinstance(routing, RoutingDecision)
    assert routing.next_node == "think.route.decide"
    assert routing.next_hint == "decision_rejected_schema"
    assert routing.should_terminate is False


@pytest.mark.asyncio
async def test_well_formed_markup_block_becomes_an_executable_call() -> None:
    decision = await _parse(_response(_WELL_FORMED))

    assert decision.action_type == ActionType.USE_TOOL.value
    assert [c.tool_name for c in decision.tool_calls] == ["echo"]
    assert decision.tool_calls[0].arguments == {"text": "hi"}
    assert decision.tool_calls[0].wire_status == "ok"

    # An invoke/parameter block carries strings only, so validate against a
    # schema the encoding can actually satisfy; _ECHO_SCHEMA also requires an
    # integer and would reject on grounds unrelated to this test.
    registry = _FakeRegistry(
        {
            "echo": _FakeTool(
                "echo",
                {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        }
    )
    output = await ThinkDecisionRepairExecutor().node_execute(
        _ctx(), _input(decision, tools=registry)
    )
    routing = output.port_values.get("routing")
    assert isinstance(routing, RoutingDecision)
    assert routing.next_node == "think.gate"
    assert routing.next_hint == "decision_ok"


def _ask_user_response() -> LLMResponse:
    return LLMResponse(
        text="",
        tool_calls=(
            NativeToolCall(
                call_id="c1",
                name="askUserQuestion",
                arguments={
                    "questions": [
                        {
                            "question": "Which color scheme?",
                            "header": "Theme",
                            "options": [
                                {"label": "Dark", "description": "Dark mode"},
                                {"label": "Light", "description": "Light mode"},
                            ],
                        }
                    ]
                },
            ),
        ),
        model="qwen3.7-plus",
        finish_reason="tool_calls",
    )


@pytest.mark.asyncio
async def test_think_parse_sets_needs_approval_for_ask_user() -> None:
    """``think.decision.parse`` must flag HITL like ``decision.compose.action``.

    The live solo path parses through this node, not the concept graph; a
    missing flag lets ``act.approve.gate`` skip and the tool executes,
    folding to FAILED instead of pausing (run_7a88995dd563).
    """
    decision = await _parse(_ask_user_response())
    assert decision.action_type == ActionType.USE_TOOL.value
    assert decision.tool_calls[0].tool_name == "askUserQuestion"
    assert decision.needs_approval is True


@pytest.mark.asyncio
async def test_think_parse_leaves_flag_clear_for_normal_tool() -> None:
    decision = await _parse(
        LLMResponse(
            text="",
            tool_calls=(NativeToolCall(call_id="c1", name="listFiles", arguments={}),),
            model="qwen3.7-plus",
            finish_reason="tool_calls",
        )
    )
    assert decision.needs_approval is False
