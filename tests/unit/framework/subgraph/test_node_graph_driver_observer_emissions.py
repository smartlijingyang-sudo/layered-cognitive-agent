"""NodeGraphDriver observer emission tests.

Locks in that ``phase_graph.node.start`` and ``phase_graph.node.end``
observer events fire for EVERY node execution, including exception paths.
Previously the observer emissions were skipped when the executor raised.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver


def _state() -> AgentState:
    return AgentState(trace_id="t", task="test", budget=Budget())


@dataclass
class _RecordingObserver:
    """Collects all observer calls for assertion."""

    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def __call__(self, event_name: str, payload: dict[str, Any]) -> None:
        self.events.append((event_name, dict(payload)))


class _FailingExecutor:
    """Executor that raises on node_execute."""

    declared_inputs: tuple[str, ...] = ()

    async def node_execute(self, ctx: Any, inp: Any) -> Any:
        raise ValueError("executor exploded")


class _OkExecutor:
    """Executor that returns a minimal output."""

    declared_inputs: tuple[str, ...] = ()

    async def node_execute(self, ctx: Any, inp: Any) -> Any:
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeOutput,
        )

        return NodeOutput(port_values={})


@dataclass
class _FakeScope:
    """Scope that resolves factory to a canned executor."""

    executor: Any

    def resolve_factory(self, factory: str, region: str | None = None) -> Any:
        return self.executor

    def resolve(self, capability: str) -> Any:
        return None


def _build_failing_spec() -> BundleGraphSpec:
    nodes = (
        BundleGraphNode(
            id="fail.node",
            region="phase:think",
            factory="test.failing",
            config={},
        ),
    )
    return BundleGraphSpec(
        id="test",
        region="phase:think",
        purpose="test",
        nodes=nodes,
        edges=(),
        entry="fail.node",
    )


def _build_ok_spec() -> BundleGraphSpec:
    nodes = (
        BundleGraphNode(
            id="ok.node",
            region="phase:think",
            factory="test.ok",
            config={},
        ),
    )
    return BundleGraphSpec(
        id="test",
        region="phase:think",
        purpose="test",
        nodes=nodes,
        edges=(),
        entry="ok.node",
    )


@pytest.mark.asyncio
async def test_observer_fires_on_exception_path() -> None:
    """When executor raises, both start and end observer events must fire."""
    observer = _RecordingObserver()
    driver = NodeGraphDriver(
        spec=_build_failing_spec(),
        plan_ref="test-plan",
        scope=_FakeScope(_FailingExecutor()),
        observers=(observer,),
    )
    result = await driver.run(
        outer_state=_state(),
        channel=__import__(
            "lca.framework.subgraph.plugins.channel", fromlist=["InMemoryPhaseOutputChannel"]
        ).InMemoryPhaseOutputChannel(),
        artifacts={},
    )
    # Result should be a failure
    assert result.outcome is not None

    # Observer must have received start + end events
    event_names = [e[0] for e in observer.events]
    assert "phase_graph.node.start" in event_names
    assert "phase_graph.node.end" in event_names

    # End event should carry failure info
    end_events = [e for e in observer.events if e[0] == "phase_graph.node.end"]
    assert len(end_events) == 1
    assert end_events[0][1]["result_kind"] == "failure"
    assert "ValueError" in end_events[0][1].get("error", "")


@pytest.mark.asyncio
async def test_observer_fires_on_success_path() -> None:
    """Success path fires start then end with success result_kind."""
    observer = _RecordingObserver()

    from lca.contracts.protocols.declarative.declarative_1.node_executor import (
        NodeOutput,
    )

    class _SimpleOkExecutor:
        declared_inputs: tuple[str, ...] = ()

        async def node_execute(self, ctx: Any, inp: Any) -> Any:
            return NodeOutput(port_values={})

    driver = NodeGraphDriver(
        spec=_build_ok_spec(),
        plan_ref="test-plan",
        scope=_FakeScope(_SimpleOkExecutor()),
        observers=(observer,),
    )
    from lca.framework.subgraph.plugins.channel import InMemoryPhaseOutputChannel

    await driver.run(
        outer_state=_state(),
        channel=InMemoryPhaseOutputChannel(),
        artifacts={},
    )

    event_names = [e[0] for e in observer.events]
    assert "phase_graph.node.start" in event_names
    assert "phase_graph.node.end" in event_names

    # start fires BEFORE end
    start_idx = next(i for i, e in enumerate(observer.events) if e[0] == "phase_graph.node.start")
    end_idx = next(i for i, e in enumerate(observer.events) if e[0] == "phase_graph.node.end")
    assert start_idx < end_idx

    # end event should not have failure info
    end_events = [e for e in observer.events if e[0] == "phase_graph.node.end"]
    assert "error" not in end_events[0][1]
