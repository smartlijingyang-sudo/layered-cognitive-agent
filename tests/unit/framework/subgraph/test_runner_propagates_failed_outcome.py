"""SubgraphRunner.run populates outcome_kind + error on FAILED path.

ADR-0219 §10.11 item (3): the runner reads sub_result.outcome at the
return site and, when kind=FAILED, copies outcome_kind=FAILED plus a
derived error string onto the returned PhaseOutput.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    DeclarativeRunOutcome,
    ExecutionOutcome,
    PhaseRunCursor,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.framework.subgraph.plugins.channel import (
    InMemoryPhaseOutputChannel,
    PhaseOutput,
)
from lca.framework.subgraph.plugins.runner import SubgraphRunner


@dataclass
class _MarkerImpl:
    """V2 marker + get_bundle_graph_spec returning a 1-node inner spec."""

    spec: Any

    def get_bundle_graph_spec(self) -> Any:
        return self.spec


class _OneNodeSpecFactory:
    """Tiny stub v2 marker — single-node inner graph that the runner
    can drive to completion."""

    def __init__(self) -> None:
        from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
            BundleGraphNode,
            BundleGraphSpec,
        )

        self._node = BundleGraphNode(
            id="inner.only",
            region="phase:think",
            factory="dummy.inner",
            config={"max_visits": 1},
        )
        self._spec = BundleGraphSpec(
            id="inner",
            region="phase:think",
            purpose="stub",
            nodes=(self._node,),
            edges=(),
            entry="inner.only",
        )

    def get_bundle_graph_spec(self) -> Any:
        return self._spec


class _FailedDriverFactory:
    """Driver factory that returns a FAILED InterpretationResult."""

    def __init__(self, reason: StopReason | None = None) -> None:
        self._reason = reason or StopReason.ERROR

    def make(
        self,
        *,
        cursor_plan_ref: str,
        cursor_node_id: str,
        output: PhaseOutput,
        outer_state: AgentState,
    ) -> Any:
        from lca.harness.declarative.execute.outcome_projection import (
            InterpretationResult,
        )

        cursor = PhaseRunCursor(
            plan_ref=cursor_plan_ref,
            node_id=cursor_node_id,
            visit_counts=(),
            edge_counts=(),
            artifacts={},
            causation_refs=(),
            budget_snapshot={"step": 0},
        )
        outcome = DeclarativeRunOutcome(
            kind=ExecutionOutcome.FAILED,
            cursor=cursor,
            stop=StopDecision(should_stop=True, reason=self._reason),
            error_fact=None,
        )
        return InterpretationResult(
            state=outer_state,
            artifact=None,
            visits=(),
            facts=(),
            terminal_node=cursor_node_id,
            outcome=outcome,
            output=output,
        )


class _StubDriver:
    """Stand-in for NodeGraphDriver; records run() calls and returns the
    canned InterpretationResult.
    """

    def __init__(self, interpretation_result: Any) -> None:
        self._result = interpretation_result

    async def run(
        self,
        *,
        outer_state: AgentState,
        channel: Any,
        artifacts: Any,
    ) -> Any:
        return self._result


def _state() -> AgentState:
    return AgentState(trace_id="t", task="test", budget=Budget())


class _StubResolver:
    """SubgraphResolver stub returning the v2 marker plan."""

    def __init__(self, plan: Any) -> None:
        self._plan = plan
        self.calls: list[str] = []

    def resolve(self, plan_ref: str) -> Any:
        self.calls.append(plan_ref)
        return self._plan


class _StubRuntime:
    """SubgraphRuntime stub. We don't use it for the FAILED test path."""

    def resolve(self, capability: str) -> Any:
        return None

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        return None


async def test_runner_propagates_failed_with_reason(monkeypatch) -> None:
    """When the driver returns FAILED, runner populates output.outcome_kind
    and output.error from the driver's stop.reason."""
    spec_factory = _OneNodeSpecFactory()
    resolver = _StubResolver(_MarkerImpl(spec_factory.get_bundle_graph_spec()))
    runner = SubgraphRunner(resolver=resolver, runtime=_StubRuntime())

    failed_output = PhaseOutput()
    driver_factory = _FailedDriverFactory(reason=StopReason.ERROR)
    fake_result = driver_factory.make(
        cursor_plan_ref="bundles/inner.yaml",
        cursor_node_id="inner.only",
        output=failed_output,
        outer_state=_state(),
    )
    stub_driver = _StubDriver(fake_result)

    # Monkey-patch NodeGraphDriver in the runner module so the runner
    # builds our stub instead of the real driver.
    from lca.framework.subgraph.plugins import runner as runner_mod

    monkeypatch.setattr(runner_mod, "NodeGraphDriver", lambda **kwargs: stub_driver)

    ref = SubgraphReference(
        plan_ref="bundles/inner.yaml",
        entry_node="inner.only",
        binding_edge="outer.entry",
    )
    _new_state, output = await runner.run(
        ref=ref,
        outer_state=_state(),
        channel=InMemoryPhaseOutputChannel(),
    )
    assert output.outcome_kind is ExecutionOutcome.FAILED
    # StopReason.ERROR has .value == "error"
    assert output.error == "error"


async def test_runner_falls_back_to_literal_when_no_stop(monkeypatch) -> None:
    """When stop is None, the derived string falls back to
    'inner subgraph failed'."""
    spec_factory = _OneNodeSpecFactory()
    resolver = _StubResolver(_MarkerImpl(spec_factory.get_bundle_graph_spec()))
    runner = SubgraphRunner(resolver=resolver, runtime=_StubRuntime())

    # Manually craft a result whose outcome has stop=None
    from lca.harness.declarative.execute.outcome_projection import (
        InterpretationResult,
    )

    cursor = PhaseRunCursor(
        plan_ref="bundles/inner.yaml",
        node_id="inner.only",
        visit_counts=(),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={"step": 0},
    )
    outcome = DeclarativeRunOutcome(
        kind=ExecutionOutcome.FAILED,
        cursor=cursor,
        stop=None,
        error_fact=None,
    )
    fake_result = InterpretationResult(
        state=_state(),
        artifact=None,
        visits=(),
        facts=(),
        terminal_node="inner.only",
        outcome=outcome,
        output=PhaseOutput(),
    )
    stub_driver = _StubDriver(fake_result)
    from lca.framework.subgraph.plugins import runner as runner_mod

    monkeypatch.setattr(runner_mod, "NodeGraphDriver", lambda **kwargs: stub_driver)

    ref = SubgraphReference(
        plan_ref="bundles/inner.yaml",
        entry_node="inner.only",
        binding_edge="outer.entry",
    )
    _new_state, output = await runner.run(
        ref=ref,
        outer_state=_state(),
        channel=InMemoryPhaseOutputChannel(),
    )
    assert output.outcome_kind is ExecutionOutcome.FAILED
    assert output.error == "inner subgraph failed"


async def test_runner_does_not_populate_outcome_kind_on_success(monkeypatch) -> None:
    """When the driver returns outcome=None (success), the runner must NOT
    populate outcome_kind on the returned output."""
    spec_factory = _OneNodeSpecFactory()
    resolver = _StubResolver(_MarkerImpl(spec_factory.get_bundle_graph_spec()))
    runner = SubgraphRunner(resolver=resolver, runtime=_StubRuntime())

    from lca.harness.declarative.execute.outcome_projection import (
        InterpretationResult,
    )

    fake_result = InterpretationResult(
        state=_state(),
        artifact=None,
        visits=(),
        facts=(),
        terminal_node="inner.only",
        outcome=None,
        output=PhaseOutput(),
    )
    stub_driver = _StubDriver(fake_result)
    from lca.framework.subgraph.plugins import runner as runner_mod

    monkeypatch.setattr(runner_mod, "NodeGraphDriver", lambda **kwargs: stub_driver)

    ref = SubgraphReference(
        plan_ref="bundles/inner.yaml",
        entry_node="inner.only",
        binding_edge="outer.entry",
    )
    _new_state, output = await runner.run(
        ref=ref,
        outer_state=_state(),
        channel=InMemoryPhaseOutputChannel(),
    )
    assert output.outcome_kind is None
    assert output.error is None
