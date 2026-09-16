"""ADR-0241 §2 — kernel seeds `tools` + `bindings` at outer plan entry.

The kernel (PlanInterpreterAdapter) is the single entry point for every
outer plan. It seeds two kernel-owned typed ports into the outer plan's
``PortRegistry`` before interpretation begins:

- ``tools`` — resolved from ``node_executor_runtime_scope.get("tools")``
  (the Cordis carrier that already publishes ``tools`` on every visit).
- ``bindings`` — resolved from ``RuntimePlane.current_bindings_view()``
  (the typed seam replacing the legacy ``AgentState._xxx_ref`` attrs).

Both are **additive** — when neither seam is bound the kernel seeds
nothing, matching the pre-ADR behaviour. The seed is exercised through
an injectable ``port_registry_seed`` parameter on
``PlanInterpreterAdapter.run`` so the test does not need to spin up
Cordis / RuntimePlane.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeIOSchema,
    NodeOutput,
    PortSpec,
)
from lca.contracts.protocols.graph.plan import Plan, PlanNode
from lca.framework.graph.adapter import PlanInterpreterAdapter


@dataclass(frozen=True, slots=True)
class _RecordingExec:
    """Node executor that records the NodeInput it received."""

    recorded_inputs: list[Mapping[str, Any]]

    async def execute(self, context, input):  # type: ignore[override]
        # Capture a snapshot so we can assert what the kernel actually
        # delivered — frozen input is fine to read here.
        self.recorded_inputs.append(dict(input.port_values))
        return NodeOutput(port_values={}, producer_node=context.node_id)


def _executable_for(plan: Plan) -> object:
    """Return either a duck-typed executable or the plan directly.

    :func:`lift_executable_plan` pass-throughs a raw :class:`Plan`, so
    tests can construct the plan in v2 shape (``PlanNode(io_schema=...)``
    instead of executable-node attrs) and hand it straight in.
    """
    return plan


def _terminal_plan() -> Plan:
    """Terminal plan whose only node declares ``tools`` + ``bindings`` inputs.

    Required-input projection is what carries the seed into the
    executor's :class:`NodeInput` — without declared inputs the seed
    would be filtered out by :meth:`PortRegistry.build_input` and the
    test would not observe it.
    """
    return Plan(
        id="p",
        nodes=(
            PlanNode(
                id="entry",
                binding=BindingKind.TRANSFORM,
                entry=True,
                io_schema=NodeIOSchema(
                    inputs=(
                        PortSpec(name="tools"),
                        PortSpec(name="bindings"),
                    ),
                ),
            ),
        ),
        edges=(),
    )


@pytest.mark.asyncio
async def test_explicit_seed_writes_tools_and_bindings_into_registry() -> None:
    """``port_registry_seed`` (Mapping) is set_outer_input before interpretation."""
    recorded: list[Mapping[str, Any]] = []
    recorder = _RecordingExec(recorded_inputs=recorded)

    @dataclass(frozen=True, slots=True)
    class _StubStrategy:
        kind: BindingKind = BindingKind.TRANSFORM

        async def execute(self, context, input):  # type: ignore[override]
            return await recorder.execute(context, input)

    from lca.framework.graph.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    registry.register(_StubStrategy())

    adapter = PlanInterpreterAdapter(registry=registry)
    seed = {"tools": "T-SVC", "bindings": "B-VIEW"}
    await adapter.run(
        executable=_executable_for(_terminal_plan()),
        state=None,
        port_registry_seed=seed,
    )
    assert recorded, "terminal node did not run"
    delivered = recorded[0]
    assert delivered.get("tools") == "T-SVC"
    assert delivered.get("bindings") == "B-VIEW"


@pytest.mark.asyncio
async def test_callable_seed_invoked_at_outer_plan_entry() -> None:
    """``port_registry_seed`` as Callable is invoked once at outer entry."""
    recorded: list[Mapping[str, Any]] = []
    recorder = _RecordingExec(recorded_inputs=recorded)

    @dataclass(frozen=True, slots=True)
    class _StubStrategy:
        kind: BindingKind = BindingKind.TRANSFORM

        async def execute(self, context, input):  # type: ignore[override]
            return await recorder.execute(context, input)

    from lca.framework.graph.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    registry.register(_StubStrategy())

    adapter = PlanInterpreterAdapter(registry=registry)
    call_count = {"n": 0}

    def seed_fn() -> Mapping[str, Any]:
        call_count["n"] += 1
        return {"tools": "FROM-CALLABLE", "bindings": "B-VIEW"}

    await adapter.run(
        executable=_executable_for(_terminal_plan()),
        state=None,
        port_registry_seed=seed_fn,
    )
    assert call_count["n"] == 1, "seed callable must be invoked exactly once"
    delivered = recorded[0]
    assert delivered.get("tools") == "FROM-CALLABLE"


@pytest.mark.asyncio
async def test_default_seed_resolves_tools_from_scope_and_bindings_from_seam() -> None:
    """When ``port_registry_seed`` is None, kernel reads from production seams.

    ``tools`` comes from ``node_executor_runtime_scope.get("tools")``;
    ``bindings`` comes from ``RuntimePlane.current_bindings_view()``.
    Either may be absent — the kernel only seeds what is bound.
    """
    from lca.contracts.models.cognition.boundary import BindingsView
    from lca.infrastructure.runtime_plane.capability_bindings import (
        BindingsViewBuilder,
        reset_capability_bindings,
        set_capability_bindings,
    )

    class _ToolsScope:
        """Stand-in for the Cordis runtime carrier exposing ``tools``."""

        def __init__(self, tools: Any) -> None:
            self._tools = tools

        def get(self, name: str) -> Any:
            if name == "tools":
                return self._tools
            return None

    bindings_fs = object()
    builder = BindingsViewBuilder(file_store=bindings_fs)
    token = set_capability_bindings(builder)
    recorded: list[Mapping[str, Any]] = []
    recorder = _RecordingExec(recorded_inputs=recorded)

    @dataclass(frozen=True, slots=True)
    class _StubStrategy:
        kind: BindingKind = BindingKind.TRANSFORM

        async def execute(self, context, input):  # type: ignore[override]
            return await recorder.execute(context, input)

    from lca.framework.graph.strategy_registry import StrategyRegistry

    registry = StrategyRegistry()
    registry.register(_StubStrategy())

    tools_obj = object()
    adapter = PlanInterpreterAdapter(
        registry=registry,
        node_executor_runtime_scope=_ToolsScope(tools=tools_obj),
    )
    try:
        await adapter.run(
            executable=_executable_for(_terminal_plan()),
            state=None,
        )
    finally:
        reset_capability_bindings(token)

    delivered = recorded[0]
    assert delivered.get("tools") is tools_obj
    assert isinstance(delivered.get("bindings"), BindingsView)


@pytest.mark.asyncio
async def test_default_seed_when_neither_seam_bound_is_empty() -> None:
    """When both production seams are unbound, kernel seeds nothing.

    Tested via a scope that resolves ``tools`` to ``None`` and a
    BindingsView seam that is unset (default ContextVar). The kernel
    must not invent ports out of thin air — empty seed → empty
    outer input.
    """
    from lca.infrastructure.runtime_plane.capability_bindings import (
        _capability_bindings,
    )

    class _EmptyScope:
        def get(self, name: str) -> Any:
            return None

    # Ensure no bindings ContextVar is set for this test (pytest may run
    # other tests that left one in scope; ContextVar default is None
    # outside a set call).
    empty_token = _capability_bindings.set(None)
    try:
        recorded: list[Mapping[str, Any]] = []
        recorder = _RecordingExec(recorded_inputs=recorded)

        @dataclass(frozen=True, slots=True)
        class _StubStrategy:
            kind: BindingKind = BindingKind.TRANSFORM

            async def execute(self, context, input):  # type: ignore[override]
                return await recorder.execute(context, input)

        from lca.framework.graph.strategy_registry import StrategyRegistry

        registry = StrategyRegistry()
        registry.register(_StubStrategy())

        adapter = PlanInterpreterAdapter(
            registry=registry,
            node_executor_runtime_scope=_EmptyScope(),
        )
        await adapter.run(
            executable=_executable_for(_terminal_plan()),
            state=None,
        )
        delivered = recorded[0]
        # Neither seam bound → delivered `tools` / `bindings` are
        # None (the registry never wrote them; build_input projects
        # ``None`` for declared ports that the registry never received).
        assert delivered.get("tools") is None
        assert delivered.get("bindings") is None
    finally:
        _capability_bindings.reset(empty_token)
