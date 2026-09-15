"""End-to-end wiring test for ``act.dispatch → act.join → act.observe``.

PR-3.8.5 fix1: closes the runtime port mismatch that the unit tests on
``act.join`` could not catch (unit tests invoke ``node_execute`` directly
with synthetic ``NodeInput(port_values={"receipts": [receipt]})``,
bypassing the kernel port registry). The inner executor
``concept.effect.execute`` previously emitted a singular ``receipt``
port while the downstream ``act.join`` typed-boundary reads
``receipts`` (list) — at runtime the registry stored only
``receipt``, ``act.join`` saw ``receipts=None`` and emitted an empty
``NodeOutput``, and the kernel classified the dispatch as ``terminal``
without ever visiting ``act.observe``.

This integration test wires the real bundle subgraph ``act.dispatch``
through :class:`SubgraphStrategy` (entry into ``bundles/concept/effect/
effect_execute.yaml``) with a stub ``effect_gateway`` so the real
``effect.execute`` executor produces an :class:`EffectReceipt`. The
outer ``PlanInterpreter` then advances to ``act.join`` (whose
``declared_inputs=("receipts",)`` matches the inner emit port) and
finally to ``act.observe``. The test asserts:

- ``act.observe`` is visited (the kernel did NOT classify the dispatch
  as ``terminal`` after the join).
- ``act.observe`` receives the same ``EffectReceipt`` instance the inner
  ``effect.execute`` produced (passthrough identity).
- The outer port registry carries ``receipts: list[EffectReceipt]``
  while ``act.join`` runs, then is reduced to ``receipt: EffectReceipt``
  for ``act.observe`` — proving the typed-port translation at the
  subgraph boundary actually closes the seam.

Per AGENTS.md §3 C10 the inner executor is still the unique effect
entry (``effect.execute → Body → SafeExecutor → Sandbox``). This test
only stubs the *runtime* capability, not the seam itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.protocols.act.command.envelope import (
    BudgetReservation,
    CapabilityGrant,
    CommandEnvelope,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext as LegacyNodeContext,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeExecutor,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeInput as LegacyNodeInput,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeOutput as LegacyNodeOutput,
)
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.plan import Plan
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.port_registry import PortRegistry
from lca.framework.graph.strategies.node_executor_strategy import (
    NodeExecutorStrategy,
)
from lca.framework.graph.strategies.subgraph_strategy import SubgraphStrategy
from lca.framework.graph.strategy_registry import StrategyRegistry
from lca.nodes.act.join import ActJoinExecutor
from lca.nodes.act.observe.observe import ActObserveExecutor
from lca.nodes.concept.effect.execute import EffectExecuteExecutor

# ── Stubs ──────────────────────────────────────────────────────────────


class _StubEffectGateway:
    """Fake effect gateway that always returns a successful receipt dict.

    Mirrors the production ``EffectDispatcher.execute(envelope, policy)``
    return shape so ``effect.execute._dispatch``'s
    :func:`_derive_outcome` takes the success path.
    """

    def __init__(self, invocation_id: str = "inv_e2e") -> None:
        self.invocation_id = invocation_id
        self.calls: list[CommandEnvelope] = []

    async def execute(self, envelope: CommandEnvelope, policy: Any) -> dict[str, Any]:
        del policy
        self.calls.append(envelope)
        return {
            "invocation_id": self.invocation_id,
            "idempotency_key": envelope.idempotency_key or self.invocation_id,
            "result": {"success": True, "echo": "ok"},
        }


class _RuntimeScope:
    """Duck-typed capability scope exposing ``effect_gateway``.

    The ``NodeExecutorStrategy._build_runtime`` factory wires this
    into ``context.runtime`` so ``effect.execute`` can
    ``getattr(runtime, "effect_gateway", None)``.
    """

    def __init__(self, gateway: _StubEffectGateway) -> None:
        self._gateway = gateway

    def get(self, key: str) -> Any:
        if key == "effect_gateway":
            return self._gateway
        return None

    def resolve(self, key: str) -> Any:
        return self.get(key)


def _build_runtime_view(gateway: _StubEffectGateway) -> Any:
    """Match the production ``_NodeRuntimeView`` interface."""

    class _View:
        __slots__ = ("_scope", "_state")

        def __init__(self) -> None:
            object.__setattr__(self, "_scope", _RuntimeScope(gateway))
            object.__setattr__(self, "_state", None)

        @property
        def state(self) -> Any:
            return object.__getattribute__(self, "_state")

        def get(self, key: str) -> Any:
            scope = object.__getattribute__(self, "_scope")
            getter = getattr(scope, "get", None) or getattr(scope, "resolve", None)
            return getter(key) if getter else None

        def __getattr__(self, key: str) -> Any:
            scope = object.__getattribute__(self, "_scope")
            getter = getattr(scope, "get", None) or getattr(scope, "resolve", None)
            return getter(key) if getter else None

    return _View()


# ── Plan + registry helpers ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _ObserveRecorder:
    """Wraps the real :class:`ActObserveExecutor` and captures the receipt.

    The dataclass is frozen; receipt capture writes through the module-level
    :data:`_OBSERVED` dict keyed by ``node_id`` so the test can assert on
    what ``act.observe`` actually received.
    """

    inner: ActObserveExecutor
    captured: list[EffectReceipt] = field(default_factory=list)

    async def node_execute(
        self,
        context: LegacyNodeContext,
        input: LegacyNodeInput,
    ) -> LegacyNodeOutput:
        output = await self.inner.node_execute(context, input)
        receipt = output.port_values.get("receipt")
        if isinstance(receipt, EffectReceipt):
            object.__setattr__(self, "captured", [*self.captured, receipt])
        return output


def _make_outer_registry(
    *,
    gateway: _StubEffectGateway,
    observe_recorder: _ObserveRecorder,
) -> StrategyRegistry:
    """Build a StrategyRegistry with the real ``effect.execute`` executor + ``act.join`` + observe."""

    executors: dict[str, NodeExecutor] = {
        "effect.execute": EffectExecuteExecutor(),
        "act.join": ActJoinExecutor(),
        "act.observe": observe_recorder,
    }

    def executor_lookup(*, binding: BindingKind, node_id: str, region: str | None) -> NodeExecutor:
        del region
        if binding is not BindingKind.NODE_EXECUTOR:
            raise KeyError(f"unexpected binding {binding!r}")
        if node_id not in executors:
            raise KeyError(f"no executor for node_id={node_id!r}")
        return executors[node_id]

    def runtime_view_factory(agent_state: Any) -> Any:
        del agent_state
        return _build_runtime_view(gateway)

    registry = StrategyRegistry()
    registry.register(
        NodeExecutorStrategy(
            executor_lookup=executor_lookup,
            node_runtime_view_factory=runtime_view_factory,
        )
    )
    return registry


def _make_inner_registry(gateway: _StubEffectGateway) -> StrategyRegistry:
    """Inner subgraph registry: only ``effect.execute`` resolves."""

    executors: dict[str, NodeExecutor] = {
        "effect.execute": EffectExecuteExecutor(),
    }

    def executor_lookup(*, binding: BindingKind, node_id: str, region: str | None) -> NodeExecutor:
        del region
        if binding is not BindingKind.NODE_EXECUTOR:
            raise KeyError(f"unexpected binding {binding!r}")
        if node_id not in executors:
            raise KeyError(f"no executor for node_id={node_id!r}")
        return executors[node_id]

    def runtime_view_factory(agent_state: Any) -> Any:
        del agent_state
        return _build_runtime_view(gateway)

    registry = StrategyRegistry()
    registry.register(
        NodeExecutorStrategy(
            executor_lookup=executor_lookup,
            node_runtime_view_factory=runtime_view_factory,
        )
    )
    return registry


async def _inner_runner(
    sub_plan: Plan,
    outer_state: Any,
    depth: int,
    outer_ports: PortRegistry | None,
    outer_mirror: dict | None,
) -> dict[str, Any]:
    """Recursive runner that re-enters the inner plan via PlanInterpreter.

    Mirrors the kernel-native production closure (see
    ``lca/framework/graph/strategies/subgraph_strategy.py`` module
    docstring §"Production callers").
    """
    del depth
    registry = outer_mirror.get("inner_registry") if outer_mirror else None
    if registry is None:
        raise RuntimeError(
            "test_act_dispatch_join_observe_e2e: outer_mirror must carry "
            "the inner StrategyRegistry under 'inner_registry'"
        )
    inner = PlanInterpreter(
        registry=registry,
        results_by_phase=outer_mirror.get("results_by_phase", {}) if outer_mirror else {},
    )
    result = await inner.run(sub_plan, port_registry=outer_ports, outer_state=outer_state)
    return dict(result.output)


def _outer_plan(inner_registry: StrategyRegistry) -> Plan:
    """Three-node plan: dispatch (subgraph) → join → observe.

    Built via the production yaml-shaped spec + :func:`lift_graph_spec`
    so the outer ``act.dispatch`` node carries the correct
    ``io_schema.inputs`` (= the inner entry's required inputs) and the
    kernel pre-seeds the subgraph with the ``envelope`` port from the
    outer registry. Same code path as the production
    ``bundles/act/act_subgraph.yaml``.
    """
    del inner_registry  # used implicitly by the test setup; not the plan itself
    spec = {
        "id": "act_dispatch_join_observe",
        "nodes": [
            {
                "id": "act.dispatch",
                "factory": "act.dispatch.ref",
                "entry": True,
                "inputs": ["envelope"],
                "outputs": ["receipts"],
                "sub_spec_ref": {
                    "plan_ref": "bundles/concept/effect/effect_execute.yaml",
                    "entry_node": "effect.execute",
                    "binding_edge": "act.dispatch",
                },
            },
            {
                "id": "act.join",
                "factory": "act.join",
                "inputs": ["receipts"],
                "outputs": ["receipt", "routing"],
            },
            {
                "id": "act.observe",
                "factory": "act.observe",
                "inputs": ["receipt"],
                "outputs": ["receipt", "should_terminate"],
                "terminal": True,
            },
        ],
        "edges": [
            {"from": "act.dispatch", "to": "act.join"},
            {
                "from": "act.join",
                "to": "act.observe",
                "when": {
                    "kind": "eq",
                    "port": {"name": "routing", "field": "next_hint"},
                    "value": "join_1to1",
                },
            },
        ],
    }
    from lca.framework.graph.lifter import lift_graph_spec

    return lift_graph_spec(spec)


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_act_dispatch_emits_receipts_and_act_observe_visits() -> None:
    """End-to-end: dispatch → join → observe delivers the receipt through the registry.

    The inner ``effect.execute`` emits ``receipts=[receipt]``. The outer
    port registry carries that to ``act.join``, which routes to
    ``act.observe`` on ``routing.next_hint == "join_1to1"``. ``act.observe``
    reads ``receipt`` (singular — produced by ``act.join`` as the
    pass-through) and runs to completion.
    """
    gateway = _StubEffectGateway(invocation_id="inv_e2e")
    observe_recorder = _ObserveRecorder(inner=ActObserveExecutor())

    inner_registry = _make_inner_registry(gateway)
    outer_registry = _make_outer_registry(
        gateway=gateway,
        observe_recorder=observe_recorder,
    )
    outer_registry.register(
        SubgraphStrategy(
            recursive_runner=_inner_runner,
            max_depth=4,
        )
    )

    plan = _outer_plan(inner_registry)
    # The kernel passes ``results_by_phase`` through ``context.node_config``
    # to the SubgraphStrategy, which forwards it as ``outer_mirror`` to
    # the recursive runner. The test's recursive runner reads the inner
    # StrategyRegistry from that dict (production callers wire the
    # kernel-native PlanInterpreter.run closure the same way).
    results_by_phase = {
        "inner_registry": inner_registry,
    }

    interpreter = PlanInterpreter(
        registry=outer_registry,
        results_by_phase=results_by_phase,
    )
    # Pre-seed the outer port registry with the typed CommandEnvelope so
    # the inner ``effect.execute`` entry receives it via ``set_outer_input``
    # (the upstream ``act.envelope`` node is out of scope for this test —
    # the brief targets the dispatch → join → observe boundary).
    registry = PortRegistry()
    registry.set_outer_input({"envelope": _test_envelope()})
    result = await interpreter.run(
        plan,
        port_registry=registry,
        outer_state=_outer_state(),
    )

    visited_ids = [v.node_id for v in result.visits]
    assert visited_ids == ["act.dispatch", "act.join", "act.observe"], (
        f"all three nodes must be visited; got sequence={visited_ids}. "
        "If this fails with ['act.dispatch'], the inner executor did not "
        "emit a port matching act.join.declared_inputs — regression of "
        "the receipt/receipts mismatch fixed in PR-3.8.5 fix1."
    )

    # Gateway was actually called by the inner executor.
    assert gateway.calls, "effect_gateway was not invoked by effect.execute"
    assert len(gateway.calls) == 1

    # act.observe received the receipt.
    assert observe_recorder.captured, (
        "act.observe did not capture a receipt — kernel terminated after "
        "join or join's output was empty (regression of receipt/receipts "
        "port mismatch fixed in PR-3.8.5 fix1)"
    )
    observed = observe_recorder.captured[-1]
    assert isinstance(observed, EffectReceipt)
    assert observed.invocation_id == "inv_e2e"
    assert observed.outcome is EffectOutcome.SUCCEEDED


@pytest.mark.asyncio
async def test_inner_executor_emits_receipts_list_not_singular_receipt() -> None:
    """Belt-and-suspenders: the inner entry's typed contract is now ``receipts``.

    Pins the PR-3.8.5 fix1 contract so a future regression that flips
    the emit port back to ``receipt`` is caught at unit-test time
    without booting the kernel.
    """
    executor = EffectExecuteExecutor()
    envelope = CommandEnvelope(
        plan_ref="plan_test",
        scope_ref="run_test",
        decision_ref="dec_test",
        provider="bash",
        grant=CapabilityGrant(capability="tool.bash", scope="run", effect_class="bash"),
        budget_reservation=BudgetReservation(),
        idempotency_key="idem_test",
        metadata={"operation": "bash"},
    )

    # Wire a minimal stub gateway through the runtime view.
    gateway = _StubEffectGateway(invocation_id="inv_unit")
    ctx = LegacyNodeContext(
        runtime=_build_runtime_view(gateway),
        budget={},
        metadata={"plan_ref": "plan_test", "node_id": "effect.execute"},
    )
    output = await executor.node_execute(
        ctx,
        LegacyNodeInput(port_values={"envelope": envelope}),
    )

    assert "receipts" in output.port_values, (
        f"effect.execute must emit 'receipts' (list); got keys={sorted(output.port_values)}"
    )
    assert "receipt" not in output.port_values, (
        "effect.execute must NOT emit the singular 'receipt' port any "
        "more — that port name is the regression closed in PR-3.8.5 fix1"
    )
    receipts = output.port_values["receipts"]
    assert isinstance(receipts, list) and len(receipts) == 1
    assert isinstance(receipts[0], EffectReceipt)
    assert receipts[0].invocation_id == "inv_unit"


# ── Tiny helper ────────────────────────────────────────────────────────


def _outer_state() -> Any:
    """Minimal AgentState-shaped object the strategies don't actually read."""
    from lca.contracts.models.core.state.state import AgentState, Budget

    return AgentState(trace_id="trace_e2e", task="", budget=Budget())


def _test_envelope() -> CommandEnvelope:
    """Minimal typed ``CommandEnvelope`` the inner ``effect.execute`` accepts."""
    return CommandEnvelope(
        plan_ref="plan_e2e",
        scope_ref="run_e2e",
        decision_ref="dec_e2e",
        provider="bash",
        grant=CapabilityGrant(
            capability="tool.bash",
            scope="run",
            effect_class="bash",
        ),
        budget_reservation=BudgetReservation(),
        idempotency_key="idem_e2e",
        metadata={"operation": "bash"},
    )


__all__ = [
    "test_act_dispatch_emits_receipts_and_act_observe_visits",
    "test_inner_executor_emits_receipts_list_not_singular_receipt",
]
