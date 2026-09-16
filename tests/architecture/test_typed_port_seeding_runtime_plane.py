"""ADR-0241 R-1 follow-up — kernel seeds typed ports from RuntimePlane.

The v2 driver (``lca.loop.driver.DeclarativeExecution``) calls
``PlanInterpreter.run`` directly without going through
``PlanInterpreterAdapter``.  That driver therefore needs its own
seeding seam: ``PlanInterpreter.run(..., port_registry_seed=...)``
with a default that reads the typed ``RuntimePlane`` ContextVars
(``current_tools_service`` + ``current_bindings_view``).

This module pins the contract:

1. ``port_registry_seed=None`` reads from ``RuntimePlane`` and seeds
   both ``tools`` and ``bindings`` into the outer ``PortRegistry``.
2. ``port_registry_seed=Mapping`` overrides the default (test
   injection).
3. ``port_registry_seed=Callable`` is invoked once and its result
   becomes the seed (test injection + late-bound composition).
4. Neither seam bound → empty seed → ``tools`` / ``bindings`` are
   ``None`` (kernel never invents ports).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.models.cognition.boundary import BindingsView
from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeIOSchema,
    NodeOutput,
    PortSpec,
)
from lca.contracts.protocols.graph.plan import Plan, PlanNode
from lca.framework.graph.interpreter import PlanInterpreter
from lca.framework.graph.strategy_registry import StrategyRegistry


@dataclass(frozen=True, slots=True)
class _RecordingExec:
    """Node executor that records the NodeInput it received."""

    recorded_inputs: list[Mapping[str, Any]]

    async def execute(self, context, input):  # type: ignore[override]
        self.recorded_inputs.append(dict(input.port_values))
        return NodeOutput(port_values={}, producer_node=context.node_id)


def _terminal_plan() -> Plan:
    """Plan whose only node declares ``tools`` + ``bindings`` inputs.

    Required-input projection is what carries the seed into the
    executor's :class:`NodeInput` — without declared inputs the seed
    would be filtered out by :meth:`PortRegistry.build_input`.
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


def _strategy_registry(recorder: _RecordingExec) -> StrategyRegistry:
    @dataclass(frozen=True, slots=True)
    class _StubStrategy:
        kind: BindingKind = BindingKind.TRANSFORM

        async def execute(self, context, input):  # type: ignore[override]
            return await recorder.execute(context, input)

    registry = StrategyRegistry()
    registry.register(_StubStrategy())
    return registry


@pytest.mark.asyncio
async def test_default_seed_reads_tools_and_bindings_from_runtime_plane() -> None:
    """``port_registry_seed=None`` reads from RuntimePlane (production seam).

    Both ``current_tools_service`` and ``current_bindings_view`` are
    set; the kernel must seed both ports into the outer plan's
    ``PortRegistry`` and the terminal node must observe them.
    """
    from lca.infrastructure.runtime_plane.capability_bindings import (
        BindingsViewBuilder,
        reset_capability_bindings,
        reset_current_tools_service,
        set_capability_bindings,
        set_current_tools_service,
    )

    bindings_fs = object()
    tools_obj = object()
    builder = BindingsViewBuilder(file_store=bindings_fs)
    bindings_token = set_capability_bindings(builder)
    tools_token = set_current_tools_service(tools_obj)
    recorded: list[Mapping[str, Any]] = []
    recorder = _RecordingExec(recorded_inputs=recorded)
    interpreter = PlanInterpreter(registry=_strategy_registry(recorder))
    try:
        await interpreter.run(_terminal_plan())
    finally:
        reset_capability_bindings(bindings_token)
        reset_current_tools_service(tools_token)

    assert recorded, "terminal node did not run"
    delivered = recorded[0]
    assert delivered.get("tools") is tools_obj
    assert isinstance(delivered.get("bindings"), BindingsView)


@pytest.mark.asyncio
async def test_explicit_seed_mapping_overrides_runtime_plane() -> None:
    """``port_registry_seed=Mapping`` takes priority over RuntimePlane.

    Even if the RuntimePlane is populated, an explicit Mapping seed
    wins — useful for tests that want to assert the kernel respected
    an injected binding without depending on the ambient plane.
    """
    from lca.infrastructure.runtime_plane.capability_bindings import (
        BindingsViewBuilder,
        reset_capability_bindings,
        reset_current_tools_service,
        set_capability_bindings,
        set_current_tools_service,
    )

    builder_token = set_capability_bindings(BindingsViewBuilder())
    tools_token = set_current_tools_service(object())
    recorded: list[Mapping[str, Any]] = []
    recorder = _RecordingExec(recorded_inputs=recorded)
    interpreter = PlanInterpreter(registry=_strategy_registry(recorder))
    try:
        await interpreter.run(
            _terminal_plan(),
            port_registry_seed={
                "tools": "INJECTED-TOOLS",
                "bindings": "INJECTED-BINDINGS",
            },
        )
    finally:
        reset_capability_bindings(builder_token)
        reset_current_tools_service(tools_token)

    delivered = recorded[0]
    assert delivered.get("tools") == "INJECTED-TOOLS"
    assert delivered.get("bindings") == "INJECTED-BINDINGS"


@pytest.mark.asyncio
async def test_callable_seed_invoked_once_at_outer_plan_entry() -> None:
    """``port_registry_seed=Callable`` is invoked once and used as seed."""
    recorded: list[Mapping[str, Any]] = []
    recorder = _RecordingExec(recorded_inputs=recorded)
    interpreter = PlanInterpreter(registry=_strategy_registry(recorder))
    call_count = {"n": 0}

    def seed_fn() -> Mapping[str, Any]:
        call_count["n"] += 1
        return {"tools": "FROM-CALLABLE", "bindings": "B-VIEW"}

    await interpreter.run(_terminal_plan(), port_registry_seed=seed_fn)

    assert call_count["n"] == 1
    delivered = recorded[0]
    assert delivered.get("tools") == "FROM-CALLABLE"


@pytest.mark.asyncio
async def test_default_seed_when_neither_seam_bound_is_empty() -> None:
    """Neither seam bound → kernel seeds nothing.

    The kernel never invents default typed values.  When both
    ContextVars are unset, ``tools`` and ``bindings`` are ``None``
    in the node input — exactly the same surface as a missing
    declared port.
    """
    from lca.infrastructure.runtime_plane.capability_bindings import (
        _capability_bindings,
        _tools_service,
    )

    empty_builder_token = _capability_bindings.set(None)
    empty_tools_token = _tools_service.set(None)
    recorded: list[Mapping[str, Any]] = []
    recorder = _RecordingExec(recorded_inputs=recorded)
    interpreter = PlanInterpreter(registry=_strategy_registry(recorder))
    try:
        await interpreter.run(_terminal_plan())
    finally:
        _capability_bindings.reset(empty_builder_token)
        _tools_service.reset(empty_tools_token)

    delivered = recorded[0]
    assert delivered.get("tools") is None
    assert delivered.get("bindings") is None
