"""RA-140 pin: ``act.authorize`` declares the kernel-owned ``tools`` port.

Before RA-140, ``ActAuthorizeExecutor.node_execute`` read
``input.port_values.get(PortName("tools"))`` but
``bundles/act/act_subgraph.yaml`` declared only ``inputs: [decision, state]``,
and ``PortRegistry.build_input(schema.required_inputs())`` projects only
declared required inputs — so the read was provably always ``None`` and the
executor silently fell back to the global ``current_tools_service()`` probe.

After RA-140, the yaml declares ``inputs: [decision, state, tools]`` and
``declared_inputs`` mirrors it, so the kernel-owned seed
(``PlanInterpreter(port_registry_seed={"tools": ...})``; in production
``_port_registry_seed_from_runtime_plane``) flows through the typed port seam.
The fallback stays as fail-soft (``build_input`` yields ``None`` for missing
ports, no error), so paths without a seed are unchanged.

This test runs the lifted bundle's ``act.authorize`` node (single-node plan,
real ``PlanInterpreter``, real ``ActAuthorizeExecutor`` behind a recording
spy) with the kernel ``tools`` port seeded, and asserts the executor received
the seeded ToolsService — not ``None``. It fails on pre-RA-140 code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.plan import Plan
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.lifter import _lift_graph_spec_inner
from lca.framework.graph.strategies.node_executor_strategy import (
    NodeExecutorStrategy,
)
from lca.framework.graph.strategy_registry import StrategyRegistry
from lca.nodes.act.authorize.authorize import ActAuthorizeExecutor

BUNDLE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "bundles" / "act" / "act_subgraph.yaml"
)


class _SeededToolsService:
    """Stand-in for the per-turn ToolsService the kernel seeds."""

    def get(self, name: str) -> Any:
        return None


class _SpyAuthorize:
    """Records the ``tools`` port value the executor actually received."""

    def __init__(self) -> None:
        self.inner = ActAuthorizeExecutor()
        self.seen_tools: Any = "not-called"

    async def node_execute(self, context: NodeContext, input: NodeInput) -> NodeOutput:
        self.seen_tools = input.port_values.get(PortName("tools"))
        return await self.inner.node_execute(context, input)


def _lift_authorize_node():
    """Lift the real bundle and return the ``act.authorize`` node spec.

    Mirrors the production validation path (``lca_kernel.boot.plan_validation``):
    inject ``entry: True`` on the first node when no node marks itself as entry,
    like the e2e's ``_apply_entry_fallback``.
    """
    raw = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8"))
    nodes = list(raw.get("nodes") or ())
    if nodes and not any(isinstance(n, dict) and n.get("entry") for n in nodes):
        nodes[0] = {**nodes[0], "entry": True}
        raw = {**raw, "nodes": nodes}
    plan = _lift_graph_spec_inner(raw)
    for node in plan.nodes:
        if node.id == "act.authorize":
            return node
    raise AssertionError("act.authorize node missing from lifted bundle")


def _single_node_plan(node) -> Plan:
    entry = node.model_copy(update={"entry": True})
    return Plan(id="ra140-tools-port", nodes=(entry,), edges=())


def _registry(spy: _SpyAuthorize) -> StrategyRegistry:
    def executor_lookup(*, binding: BindingKind, node_id: str, region: Any) -> Any:
        del region
        assert binding is BindingKind.NODE_EXECUTOR
        assert node_id == "act.authorize"
        return spy

    registry = StrategyRegistry()
    registry.register(NodeExecutorStrategy(executor_lookup=executor_lookup))
    return registry


def test_bundle_declares_tools_input_for_act_authorize() -> None:
    """The yaml declaration is the seam: ``tools`` must be a required input."""
    node = _lift_authorize_node()
    assert PortName("tools") in node.io_schema.required_inputs()


async def test_interpreter_seed_reaches_act_authorize_node_execute() -> None:
    """The kernel ``tools`` seed arrives at ``node_execute`` (not ``None``)."""
    spy = _SpyAuthorize()
    seeded = _SeededToolsService()
    plan = _single_node_plan(_lift_authorize_node())
    interpreter = PlanInterpreter(registry=_registry(spy))

    decision = Decision(
        decision_id="ra140-tools-port",
        action_type="respond",
        rationale="RA-140 port-flow pin",
        confidence=1.0,
        tool_calls=[],
        delegations=[],
    )
    outer_state = AgentState(trace_id="ra140-tools-port", task="", budget=Budget())

    await interpreter.run(
        plan,
        port_registry_seed={
            "decision": decision,
            "tools": seeded,
        },
        outer_state=outer_state,
    )

    assert spy.seen_tools is seeded, (
        "act.authorize did not receive the seeded tools service; "
        f"got {spy.seen_tools!r} (pre-RA-140 this is always None)"
    )
