"""NodeGraphDriver fan-in dispatch test.

ADR-0220 §3.3 declares ``concept.decision.classify`` as a 3-node subgraph
with two fan-in edges into ``decision.compose.action``:

    decision.parse.tool_calls ──┐
                                ├──> decision.compose.action
    decision.parse.intent ──────┘

The driver must schedule every node whose ``declared_inputs`` are
satisfied, not only the one reachable by walking edges from the
entry node. A regression that walked only the entry chain would
silently skip ``decision.parse.intent`` and leave ``compose.action``
with ``intent=None``.

This test pins the dispatch semantics with a minimal diamond-shaped
spec and asserts that the fan-in source node is actually executed
and its output reaches the join node's input.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphEdge,
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeOutput,
)
from lca.framework.subgraph.plugins.channel import InMemoryPhaseOutputChannel
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver


def _state() -> AgentState:
    return AgentState(trace_id="t", task="test", budget=Budget())


class _RecordingFactoryResolver:
    """Resolves factory names to a per-name executor; records calls."""

    def __init__(self, executors: dict[str, Any]) -> None:
        self._executors = executors
        self.calls: list[str] = []

    def resolve_factory(self, factory: str, region: str | None = None) -> Any:
        self.calls.append(factory)
        return self._executors[factory]

    def resolve(self, capability: str) -> Any:
        return None


@dataclass
class _RecordingObserver:
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def __call__(self, event_name: str, payload: dict[str, Any]) -> None:
        self.events.append((event_name, dict(payload)))


class _ParseToolCallsExecutor:
    declared_inputs: tuple[str, ...] = ("response",)
    declared_outputs: tuple[str, ...] = ("tool_calls", "delegations")

    async def node_execute(self, ctx: Any, inp: Any) -> NodeOutput:
        return NodeOutput(
            port_values={"tool_calls": ("call_1",), "delegations": ()},
        )


class _ParseIntentExecutor:
    declared_inputs: tuple[str, ...] = ("response",)
    declared_outputs: tuple[str, ...] = ("intent",)

    async def node_execute(self, ctx: Any, inp: Any) -> NodeOutput:
        return NodeOutput(port_values={"intent": "the actual joke"})


class _ComposeActionExecutor:
    declared_inputs: tuple[str, ...] = ("tool_calls", "delegations", "intent")
    declared_outputs: tuple[str, ...] = ("decision",)

    def __init__(self) -> None:
        self.received_intent: Any = "<sentinel-not-called>"

    async def node_execute(self, ctx: Any, inp: Any) -> NodeOutput:
        self.received_intent = inp.port_values.get("intent")
        return NodeOutput(port_values={})


def _build_diamond_spec() -> BundleGraphSpec:
    nodes = (
        BundleGraphNode(
            id="parse.tool_calls",
            region="concept",
            factory="decision.parse.tool_calls",
        ),
        BundleGraphNode(
            id="parse.intent",
            region="concept",
            factory="decision.parse.intent",
        ),
        BundleGraphNode(
            id="compose.action",
            region="concept",
            factory="decision.compose.action",
        ),
    )
    edges = (
        BundleGraphEdge(source="parse.tool_calls", target="compose.action"),
        BundleGraphEdge(source="parse.intent", target="compose.action"),
    )
    return BundleGraphSpec(
        id="concept.decision.classify",
        region="concept",
        purpose="fan-in test",
        nodes=nodes,
        edges=edges,
        entry="parse.tool_calls",
    )


@pytest.mark.asyncio
async def test_fan_in_node_gets_executed() -> None:
    """parse.intent has no edge from entry — driver must still schedule it.

    Prior bug: driver walked entry → select_edge chain only, leaving
    fan-in nodes unvisited. This test would fail under the bug because
    ``_parse_intent_calls`` would be 0.
    """
    compose = _ComposeActionExecutor()
    scope = _RecordingFactoryResolver(
        executors={
            "decision.parse.tool_calls": _ParseToolCallsExecutor(),
            "decision.parse.intent": _ParseIntentExecutor(),
            "decision.compose.action": compose,
        }
    )
    observer = _RecordingObserver()
    driver = NodeGraphDriver(
        spec=_build_diamond_spec(),
        plan_ref="test-plan",
        scope=scope,
        observers=(observer,),
    )

    # Use a real LLMResponse-like object so driver_signal phase output
    # accepts it; the exact content is irrelevant for this test.
    from lca.contracts.models.core.conversation.llm import LLMResponse

    response = LLMResponse(text="", tool_calls=None)
    with contextlib.suppress(Exception):
        await driver.run(
            outer_state=_state(),
            channel=InMemoryPhaseOutputChannel(),
            artifacts={},
            outer_input={"response": response},
        )

    assert scope.calls.count("decision.parse.intent") >= 1, (
        "parse.intent never scheduled; driver only walks edge chain"
    )


@pytest.mark.asyncio
async def test_join_node_receives_fan_in_output() -> None:
    """compose.action must receive the intent produced by parse.intent.

    This is the regression that surfaced as '抱歉,模型未返回有效决策'
    in run_4e1c973fb8df: parse.intent never ran, compose.action saw
    intent=None, fell back to the empty-response user message.
    """
    compose = _ComposeActionExecutor()
    scope = _RecordingFactoryResolver(
        executors={
            "decision.parse.tool_calls": _ParseToolCallsExecutor(),
            "decision.parse.intent": _ParseIntentExecutor(),
            "decision.compose.action": compose,
        }
    )
    driver = NodeGraphDriver(
        spec=_build_diamond_spec(),
        plan_ref="test-plan",
        scope=scope,
    )

    from lca.contracts.models.core.conversation.llm import LLMResponse

    response = LLMResponse(text="", tool_calls=None)
    with contextlib.suppress(Exception):
        await driver.run(
            outer_state=_state(),
            channel=InMemoryPhaseOutputChannel(),
            artifacts={},
            outer_input={"response": response},
        )

    assert compose.received_intent == "the actual joke", (
        f"compose.action got intent={compose.received_intent!r}; "
        "fan-in dispatch did not propagate parse.intent output"
    )
