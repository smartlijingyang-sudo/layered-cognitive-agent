"""Driver recursive sub_spec_ref guards (ADR-0217 §3.3.1, PG-007-*).

PG-007-depth + PG-007-cycle detection live on
:class:`lca.framework.subgraph.plugins.node_graph_driver.NodeGraphDriver`.
These tests cover the seam ``_drive_subgraph_ref(ref, outer_state, depth=0)``
in isolation — no real executor, no Cordis container, no Profile
resolution. The full recursion body (``_drive_subgraph_inner``) is a
no-op seam until PR-3 wires up inner-spec resolution.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from lca.contracts.exceptions.subgraph import (
    SubgraphCycleError,
    SubgraphDepthExceededError,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.framework.subgraph.plugins.node_graph_driver import (
    MAX_SUBGRAPH_DEPTH_DEFAULT,
    NodeGraphDriver,
)


def _state() -> AgentState:
    return AgentState(trace_id="trace:test", task="test", budget=Budget())


def _spec() -> BundleGraphSpec:
    return BundleGraphSpec(
        id="unit.spec",
        region="phase:think",
        purpose="unit",
        nodes=(
            BundleGraphNode(
                id="outer.node",
                region="phase:think",
                factory="unit.factory",
                purpose="",
                inputs=(),
                outputs=(),
                config={},
            ),
        ),
        edges=(),
        entry="outer.node",
    )


def _ref(plan_ref: str = "bundles/inner.yaml") -> SubgraphReference:
    return SubgraphReference(
        plan_ref=plan_ref,
        entry_node="inner.entry",
        binding_edge="outer.node",
    )


def _driver(
    *,
    max_subgraph_depth: int = MAX_SUBGRAPH_DEPTH_DEFAULT,
    plan_ref: str = "bundles/outer.yaml",
) -> NodeGraphDriver:
    return NodeGraphDriver(
        spec=_spec(),
        plan_ref=plan_ref,
        scope=SimpleNamespace(resolve_factory=lambda *a, **k: SimpleNamespace()),
        max_subgraph_depth=max_subgraph_depth,
    )


class TestDepthGuard:
    """PG-007-depth: nesting depth > max_subgraph_depth fails loud."""

    @pytest.mark.asyncio
    async def test_depth_within_limit_passes(self) -> None:
        """depth == max_subgraph_depth 不报错(只 > max 才抛)。"""
        driver = _driver(max_subgraph_depth=2)
        out = await driver._drive_subgraph_ref(_ref(), _state(), depth=2)
        assert out is not None
        # plan_ref 已被 try/finally discard
        assert "bundles/inner.yaml" not in driver._recursion_stack

    @pytest.mark.asyncio
    async def test_depth_exceeded_fail_loud(self) -> None:
        """depth > max_subgraph_depth → PG-007-depth fail-loud。"""
        driver = _driver(max_subgraph_depth=2)
        with pytest.raises(SubgraphDepthExceededError) as excinfo:
            await driver._drive_subgraph_ref(_ref(), _state(), depth=3)
        assert excinfo.value.depth == 3
        assert excinfo.value.max_depth == 2


class TestCycleGuard:
    """PG-007-cycle: same plan_ref appears twice on the recursion stack."""

    @pytest.mark.asyncio
    async def test_cycle_detected_fail_loud(self) -> None:
        """同 plan_ref 在递归栈出现第二次 → PG-007-cycle fail-loud。"""
        driver = _driver()
        shared = "bundles/recursive.yaml"
        ref = _ref(shared)
        # Prime the stack to simulate mid-recursion entry.
        driver._recursion_stack.add(shared)
        with pytest.raises(SubgraphCycleError) as excinfo:
            await driver._drive_subgraph_ref(ref, _state(), depth=1)
        assert excinfo.value.plan_ref == shared

    @pytest.mark.asyncio
    async def test_stack_discarded_on_unwind(self) -> None:
        """try/finally 始终把 plan_ref discard(成功路径也清理)。"""
        driver = _driver()
        ref = _ref("bundles/once.yaml")
        await driver._drive_subgraph_ref(ref, _state(), depth=0)
        assert "bundles/once.yaml" not in driver._recursion_stack

        # Re-enter at a fresh depth — same plan_ref, distinct call.
        await driver._drive_subgraph_ref(ref, _state(), depth=0)
        assert "bundles/once.yaml" not in driver._recursion_stack
