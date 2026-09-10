"""End-to-end: inner driver failure surfaces to outer as outcome_kind=FAILED.

ADR-0219 §10.11 item (3): when the inner driver's terminal node fails
(e.g. an executor raises), SubgraphRunner.run populates
output.outcome_kind=FAILED and output.error on the returned PhaseOutput.

This integration test injects a driver factory whose executor raises,
and verifies:
1. The outer driver (running the outer think subgraph) sees the
   FAILED inner outcome via output.outcome_kind.
2. The outer driver returns a FAILED InterpretationResult to its
   caller, surfacing the inner error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.contracts.protocols.declarative.declarative_1.v2_plan_marker import (
    V2BundleGraphPlanMarker,
)
from lca.framework.subgraph.plugins.channel import InMemoryPhaseOutputChannel
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver
from lca.framework.subgraph.plugins.runner import SubgraphRunner


def _state() -> AgentState:
    return AgentState(trace_id="t", task="hello", budget=Budget())


class _StubPlan(V2BundleGraphPlanMarker):
    _spec: BundleGraphSpec

    def __init__(self, spec: BundleGraphSpec) -> None:
        self._spec = spec

    def get_bundle_graph_spec(self) -> BundleGraphSpec:
        return self._spec


class _RaisingExecutor:
    """Executor that always raises. Used as the resolve_factory target
    for the inner graph's nodes — driver catches the exception and
    returns a FAILED InterpretationResult.
    """

    declared_inputs = ()

    async def node_execute(self, ctx: Any, node_input: Any) -> Any:
        raise RuntimeError("inner driver exploded")


class _RaisingScope:
    """SubgraphRuntime whose resolve_factory returns the raising
    executor. Used for the inner subgraph's runtime."""

    def resolve(self, capability: str) -> Any:
        raise KeyError(capability)

    def resolve_capability(self, capability: str) -> Any:
        raise KeyError(capability)

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        return _RaisingExecutor()


class _OuterScope:
    """SubgraphRuntime that delegates to a real executor for outer nodes
    except think.reason — but think.reason has sub_spec_ref so we never
    resolve its factory in the outer driver. All other factories
    resolve to a no-op executor so the outer driver advances past
    them. (We assert outcome at the point where the inner
    sub_spec_ref branch fires.)"""

    def resolve(self, capability: str) -> Any:
        raise KeyError(capability)

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        from lca.framework.subgraph.plugins.node_graph_driver import (
            NodeGraphDriver,
        )

        # Won't be hit for nodes with sub_spec_ref. Other nodes are
        # bypassed via entry = think.reason in this test.
        raise LookupError(factory)


def _build_minimal_inner_spec() -> BundleGraphSpec:
    """Inner spec: single node that triggers the executor."""
    from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
        BundleGraphNode,
    )

    node = BundleGraphNode(
        id="inner.boom",
        region="phase:think",
        factory="dummy.boom",
        config={"max_visits": 1},
    )
    return BundleGraphSpec(
        id="inner",
        region="phase:think",
        purpose="test",
        nodes=(node,),
        edges=(),
        entry="inner.boom",
    )


def _build_outer_spec_with_inner_sub_spec() -> BundleGraphSpec:
    """Outer spec: single node with typed sub_spec_ref pointing at
    the inner spec. The inner driver will fail, propagating to outer."""
    from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
        BundleGraphNode,
    )

    node = BundleGraphNode(
        id="outer.boom",
        region="phase:think",
        factory="dummy.outer",
        config={"max_visits": 1},
        sub_spec_ref=SubgraphReference(
            plan_ref="bundles/inner.yaml",
            entry_node="inner.boom",
            binding_edge="outer.boom",
        ),
    )
    return BundleGraphSpec(
        id="outer",
        region="phase:think",
        purpose="test",
        nodes=(node,),
        edges=(),
        entry="outer.boom",
    )


class TestInnerFailureSurfacesToOuter:
    @pytest.mark.asyncio
    async def test_inner_executor_failure_propagates_to_outer(self) -> None:
        """When the inner driver's executor raises, the runner
        populates output.outcome_kind=FAILED. The outer driver sees
        this in its sub_spec_ref branch and returns a FAILED
        InterpretationResult.
        """
        inner_spec = _build_minimal_inner_spec()
        outer_spec = _build_outer_spec_with_inner_sub_spec()

        class _Resolver:
            def __init__(self) -> None:
                self._inner_plan = _StubPlan(inner_spec)

            def resolve(self, plan_ref: str) -> Any:
                if plan_ref == "bundles/inner.yaml":
                    return self._inner_plan
                return None

        runner = SubgraphRunner(
            resolver=_Resolver(),
            runtime=_RaisingScope(),
        )

        outer_driver = NodeGraphDriver(
            spec=outer_spec,
            plan_ref="bundles/outer.yaml",
            scope=_OuterScope(),
            sub_runner=runner,
            channel_factory=InMemoryPhaseOutputChannel,
        )

        result = await outer_driver.run(
            outer_state=_state(),
            channel=InMemoryPhaseOutputChannel(),
            artifacts={},
            outer_input=None,
        )
        # FAILED inner propagated to outer
        assert result.outcome is not None
        assert result.outcome.kind is ExecutionOutcome.FAILED
        # output carries outcome_kind + error
        assert result.output.outcome_kind is ExecutionOutcome.FAILED
        assert result.output.error is not None
        assert "inner" in result.output.error.lower() or "boom" in result.output.error.lower()

    @pytest.mark.asyncio
    async def test_runner_run_populates_outcome_kind_on_inner_failure(self) -> None:
        """Direct test on SubgraphRunner.run: when the inner driver
        raises, runner.run returns output.outcome_kind=FAILED.
        """
        inner_spec = _build_minimal_inner_spec()

        class _Resolver:
            def __init__(self) -> None:
                self._inner_plan = _StubPlan(inner_spec)

            def resolve(self, plan_ref: str) -> Any:
                if plan_ref == "bundles/inner.yaml":
                    return self._inner_plan
                return None

        runner = SubgraphRunner(
            resolver=_Resolver(),
            runtime=_RaisingScope(),
        )
        ref = SubgraphReference(
            plan_ref="bundles/inner.yaml",
            entry_node="inner.boom",
            binding_edge="outer.boom",
        )
        state, output = await runner.run(
            ref=ref,
            outer_state=_state(),
            channel=InMemoryPhaseOutputChannel(),
        )
        assert output.outcome_kind is ExecutionOutcome.FAILED
        assert output.error is not None
