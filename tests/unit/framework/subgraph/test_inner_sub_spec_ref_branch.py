"""Inner driver sub_spec_ref branch tests (ADR-0219 §10.11 item 1).

Contract:
- NodeGraphDriver.run calls sub_runner.run when node.sub_spec_ref is set.
- The inner PhaseOutput is absorbed into the calling channel.
- A FAILED inner PhaseOutput (outcome_kind=FAILED) propagates as a
  _failed_result InterpretationResult to the outer caller.
- A missing sub_runner / channel_factory fails loud with a FAILED
  InterpretationResult (the contract violation message goes into the
  exception, which is then handed to _failed_result; stop.reason is
  always StopReason.ERROR per the canonical FAILED outcome shape).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphEdge,
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.framework.subgraph.plugins.channel import (
    InMemoryPhaseOutputChannel,
    PhaseOutput,
    PhaseOutputChannel,
)
from lca.framework.subgraph.plugins.node_graph_driver import (
    NodeGraphDriver,
)


def _state() -> AgentState:
    return AgentState(trace_id="t", task="test", budget=Budget())


@dataclass
class _FakeSubRunner:
    """Stub for the SubgraphRunner used by the inner-driver branch.

    Records the calls made by the driver and returns a canned
    PhaseOutput. The driver's ``channel.absorb`` step is asserted by
    the test.
    """

    output: PhaseOutput
    captured_ref: SubgraphReference | None = None
    captured_state: AgentState | None = None
    captured_channel: PhaseOutputChannel | None = None
    call_count: int = 0

    async def run(
        self,
        *,
        ref: SubgraphReference,
        outer_state: AgentState,
        channel: PhaseOutputChannel,
    ) -> tuple[AgentState, PhaseOutput]:
        self.call_count += 1
        self.captured_ref = ref
        self.captured_state = outer_state
        self.captured_channel = channel
        return outer_state, self.output


def _build_spec_terminating_after_inner() -> BundleGraphSpec:
    """Construct a 1-node spec whose entry carries sub_spec_ref.
    After the inner runs, the spec terminates (no edges)."""
    nodes = (
        BundleGraphNode(
            id="outer.entry",
            region="phase:think",
            factory="dummy.outer",
            config={"max_visits": 1},
            sub_spec_ref=SubgraphReference(
                plan_ref="bundles/inner.yaml",
                entry_node="inner.start",
                binding_edge="outer.entry",
            ),
        ),
    )
    return BundleGraphSpec(
        id="outer",
        region="phase:think",
        purpose="test",
        nodes=nodes,
        edges=(),
        entry="outer.entry",
    )


def _build_spec_with_two_nodes() -> BundleGraphSpec:
    """Construct a 2-node spec whose entry has sub_spec_ref and
    transitions to a second node, which the scope resolves to a no-op."""
    nodes = (
        BundleGraphNode(
            id="outer.entry",
            region="phase:think",
            factory="dummy.outer",
            config={"max_visits": 1},
            sub_spec_ref=SubgraphReference(
                plan_ref="bundles/inner.yaml",
                entry_node="inner.start",
                binding_edge="outer.entry",
            ),
        ),
        BundleGraphNode(
            id="outer.after",
            region="phase:think",
            factory="dummy.after",
            config={"max_visits": 1},
        ),
    )
    edges = (BundleGraphEdge(source="outer.entry", target="outer.after"),)
    return BundleGraphSpec(
        id="outer",
        region="phase:think",
        purpose="test",
        nodes=nodes,
        edges=edges,
        entry="outer.entry",
    )


class _NoopAfterScope:
    """Scope that returns None for any resolve_factory (won't be hit
    if the graph terminates at the entry node)."""

    def resolve(self, capability: str) -> Any:
        raise KeyError(capability)

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        # Used by the second node only; return None and let driver
        # treat it as missing.
        raise LookupError(factory)


class _AfterScope:
    """Scope that handles dummy.after by returning a stub executor
    that produces an empty NodeOutput so the outer driver can
    terminate cleanly."""

    def __init__(self) -> None:
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeOutput,
        )

        self._noop_output = NodeOutput(port_values={})

    def resolve(self, capability: str) -> Any:
        raise KeyError(capability)

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        if factory == "dummy.after":
            return _NoopExecutor(self._noop_output)
        raise LookupError(factory)


class _NoopExecutor:
    declared_inputs = ()

    def __init__(self, output: Any) -> None:
        self._output = output

    async def node_execute(self, ctx: Any, node_input: Any) -> Any:
        return self._output


async def test_inner_driver_delegates_to_sub_runner_when_sub_spec_ref_set() -> None:
    """Sub_spec_ref branch calls sub_runner.run, absorbs inner output,
    and advances via declared edges. Uses a 2-node spec so we exercise
    the advance path."""
    spec = _build_spec_with_two_nodes()
    sub_runner = _FakeSubRunner(output=PhaseOutput())
    channel_calls: list[PhaseOutput] = []

    class _SpyChannel(InMemoryPhaseOutputChannel):
        def absorb(self, delta: PhaseOutput) -> None:
            channel_calls.append(delta)

    spy_channel = _SpyChannel()

    driver = NodeGraphDriver(
        spec=spec,
        plan_ref="outer",
        scope=_AfterScope(),
        sub_runner=sub_runner,
        channel_factory=lambda: spy_channel,
    )
    result = await driver.run(
        outer_state=_state(),
        channel=InMemoryPhaseOutputChannel(),
        artifacts={},
        outer_input=None,
    )
    assert sub_runner.call_count == 1
    assert sub_runner.captured_ref is not None
    assert sub_runner.captured_ref.plan_ref == "bundles/inner.yaml"
    # spy channel got the absorb call with the inner PhaseOutput
    assert len(channel_calls) == 1
    assert channel_calls[0] is sub_runner.output
    # Outer driver advanced to outer.after and terminated cleanly
    assert result.terminal_node == "outer.after"
    assert result.outcome is None


async def test_inner_driver_propagates_failed_outcome_from_inner() -> None:
    spec = _build_spec_terminating_after_inner()
    failed_output = PhaseOutput(
        outcome_kind=ExecutionOutcome.FAILED, error="boom"
    )
    sub_runner = _FakeSubRunner(output=failed_output)
    driver = NodeGraphDriver(
        spec=spec,
        plan_ref="outer",
        scope=_NoopAfterScope(),
        sub_runner=sub_runner,
        channel_factory=InMemoryPhaseOutputChannel,
    )
    result = await driver.run(
        outer_state=_state(),
        channel=InMemoryPhaseOutputChannel(),
        artifacts={},
        outer_input=None,
    )
    # FAILED inner -> outer driver returns _failed_result with FAILED outcome
    assert result.outcome is not None
    assert result.outcome.kind is ExecutionOutcome.FAILED
    assert result.output.outcome_kind is ExecutionOutcome.FAILED
    assert result.output.error == "boom"


async def test_inner_driver_fails_loud_when_sub_runner_missing() -> None:
    spec = _build_spec_terminating_after_inner()
    # Constructed WITHOUT sub_runner / channel_factory
    driver = NodeGraphDriver(
        spec=spec,
        plan_ref="outer",
        scope=_NoopAfterScope(),
    )
    result = await driver.run(
        outer_state=_state(),
        channel=InMemoryPhaseOutputChannel(),
        artifacts={},
        outer_input=None,
    )
    assert result.outcome is not None
    assert result.outcome.kind is ExecutionOutcome.FAILED
    # stop.reason.value is the canonical 'error' string; the
    # contract-violation RuntimeError message travels separately
    # through the standard FAILED outcome shape. We assert the
    # outcome is FAILED — the contract violation is the message
    # baked into the runtime exception that produced the FAILED
    # outcome; consumers can fetch the exception via the failure
    # record in stop.failure if exposed.
    assert result.outcome.stop is not None
