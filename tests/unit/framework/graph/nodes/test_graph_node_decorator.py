"""@graph_node decorator — typed-boundary contract (ADR-0227 §Decision)."""

from __future__ import annotations

from importlib import import_module
from typing import Any
from unittest.mock import MagicMock

import pytest

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.framework.graph.nodes.decorator import graph_node

# ── Minimal fixtures ──────────────────────────────────────────────


def _make_state() -> AgentState:
    """Construct a real ``AgentState`` so the isinstance gate passes."""
    return AgentState(trace_id="trace-test", task="", budget=Budget())


def _node_context(
    *,
    runtime: dict[str, Any] | None = None,
    budget: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> NodeContext:
    return NodeContext(
        runtime=runtime if runtime is not None else {},
        budget=budget if budget is not None else {},
        metadata=metadata if metadata is not None else {},
    )


# ── Surface / attribute contract ──────────────────────────────────


def _executor(carrier):
    """Return a fresh executor instance for a cordis Plugin carrier."""
    return carrier.__wrapped__()


def test_graph_node_decorator_wraps_async_fn_as_node_executor_dataclass() -> None:
    """`@graph_node` exposes semantic_name / region / declared_inputs / declared_outputs."""

    @graph_node(
        id="test.no_op",
        region="think",
        inputs=("state",),
        outputs=("result",),
    )
    async def no_op(*, state: AgentState) -> dict[str, Any]:
        return {"value": 42}

    executor = _executor(no_op)

    assert executor.semantic_name == "test.no_op"
    assert executor.region == "think"
    assert executor.declared_inputs == ("state",)
    assert executor.declared_outputs == ("result",)


def test_graph_node_decorator_evaluates_terminal_predicate() -> None:
    """`terminal_predicate` is stowed on the executor and applied to node output."""

    @graph_node(
        id="test.exit_on_respond",
        region="think",
        inputs=("state",),
        outputs=("decision",),
        terminal=lambda output, state: (
            ("exit", state) if output.get("action") == "respond" else ("continue", state)
        ),
    )
    async def decide(*, state: AgentState) -> dict[str, Any]:
        return {"action": "respond"}

    executor = _executor(decide)
    assert callable(executor.terminal_predicate)


def test_graph_node_decorator_without_terminal_predicate() -> None:
    """When `terminal` is omitted, the predicate is None and node output has no next_hint."""

    @graph_node(
        id="test.no_terminal",
        region="think",
        inputs=("state",),
        outputs=("value",),
    )
    async def no_terminal(*, state: AgentState) -> int:
        return 7

    executor = _executor(no_terminal)
    assert executor.terminal_predicate is None


def test_graph_node_decorator_produces_plugin_carrier() -> None:
    """`@graph_node` returns a `@plugin(...)` carrier; setup is the underlying fn."""

    @graph_node(
        id="test.plugin_carrier",
        region="think",
        inputs=(),
        outputs=(),
        effects="none",
        layer="L2",
    )
    async def no_op() -> None:
        pass

    # The wrapper exposes the cordis Plugin at `.setup`; the cordis Plugin's
    # own `.setup` attribute is the underlying async fn, so the registration
    # access pattern is `<decorated>.setup.setup(ctx, config=None)` — same as
    # the hand-written `module.setup.setup(ctx, config=None)` access.
    assert hasattr(no_op, "setup")
    assert hasattr(no_op.setup, "setup")
    assert callable(no_op.setup.setup)


def test_graph_node_decorator_plugin_carries_canonical_contract() -> None:
    """The `@plugin(...)` carrier carries the canonical PluginContract shape.

    Mirrors lca/plugins/concept/context_compose/collect.py — the carrier must
    expose identity / architecture (group + control_slots) / lifecycle /
    authority / observability so PR2 readers (e.g. ``audit-plugin-shape``)
    find the same surface.
    """

    @graph_node(
        id="test.contract_carrier",
        region="think",
        inputs=("state",),
        outputs=("result",),
        effects="none",
        layer="L2",
    )
    async def carrier(*, state: AgentState) -> dict[str, Any]:
        return {}

    plugin_carrier = carrier.setup
    meta = getattr(plugin_carrier, "meta", None)
    assert meta is not None, "cordis carrier must expose .meta"
    snapshot = meta.get("contract_snapshot")
    assert isinstance(snapshot, dict)
    assert snapshot["identity"]["version"] == "v1"
    assert snapshot["architecture"]["group"] == FunctionalGroup.G7_EXECUTION.value
    assert ControlSlot.OBSERVE_WILDCARD.value in snapshot["architecture"]["control_slots"]
    assert Scope.RUN.value in snapshot["lifecycle"]["allowed_scopes"]
    assert "plugin.serve" in snapshot["authority"]["grants"]


def test_graph_node_decorator_plugin_carries_ownership_declaration() -> None:
    """The carrier exposes the OwnershipDeclaration (reads / emits / state_mutation)."""

    @graph_node(
        id="test.ownership",
        region="think",
        inputs=("state",),
        outputs=("value",),
    )
    async def carrier(*, state: AgentState) -> int:
        return 1

    definition = getattr(carrier.setup, "_lca_definition", None)
    assert definition is not None
    ownership = definition.ownership
    assert isinstance(ownership, OwnershipDeclaration)
    assert ownership.reads == ("plugin.serve",)
    assert ownership.emits == ("plugin.served",)
    assert ownership.state_mutation == "forbidden"


# ── Composite-key registration ───────────────────────────────────


async def test_setup_registers_executor_under_composite_key() -> None:
    """``composite.setup(ctx, config=None)`` calls ``ctx.provide(f"{region}::{id}", executor)``.

    Mirrors the hand-written
    ``lca/plugins/concept/context_compose/collect.py:103-108`` and
    ``lca/plugins/think/history_assemble/execute.py:113-118``.

    The cordis Plugin's ``.setup`` attribute holds the underlying ``setup``
    async fn, so calling it is the registration entry point. In the
    hand-written pattern the module-level variable is also named ``setup``,
    so consumers see ``module.setup.setup(ctx)``; with the decorator the
    user variable name is whatever the user picks (e.g. ``composite``),
    so consumers see ``composite.setup(ctx)``.
    """

    @graph_node(
        id="test.composite_key",
        region="think",
        inputs=("state",),
        outputs=("value",),
    )
    async def composite(*, state: AgentState) -> int:
        return 0

    captured: dict[str, Any] = {}
    ctx = MagicMock()
    ctx.provide = MagicMock(side_effect=lambda key, value: captured.__setitem__(key, value))

    await composite.setup.setup(ctx, config=None)

    assert list(captured) == ["think::test.composite_key"]
    executor_cls = composite.__wrapped__
    assert isinstance(captured["think::test.composite_key"], executor_cls)
    assert captured["think::test.composite_key"].semantic_name == "test.composite_key"
    assert captured["think::test.composite_key"].region == "think"


# ── node_execute dispatch ────────────────────────────────────────


async def test_node_execute_resolves_ports_and_invokes_user_fn() -> None:
    """``node_execute`` reads ports, falls back to ``context.runtime``, calls the fn."""

    @graph_node(
        id="test.port_resolution",
        region="think",
        inputs=("state",),
        outputs=("value",),
    )
    async def port_resolution(*, state: AgentState) -> int:
        return state.step + 1

    executor = _executor(port_resolution)
    state = _make_state()
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": state}),
    )

    assert isinstance(out, NodeOutput)
    assert out.port_values == {"value": 1}
    # no terminal_predicate → next_hint stays None
    assert out.next_hint is None


async def test_node_execute_falls_back_to_context_runtime() -> None:
    """Missing port values fall back to ``context.runtime`` (matches history_assemble)."""

    @graph_node(
        id="test.runtime_fallback",
        region="think",
        inputs=("state",),
        outputs=("value",),
    )
    async def runtime_fallback(*, state: AgentState) -> int:
        return state.step

    executor = _executor(runtime_fallback)
    state = _make_state()
    out = await executor.node_execute(
        context=_node_context(runtime={"state": state}),
        input=NodeInput(port_values={}),
    )

    assert out.port_values == {"value": 0}


async def test_node_execute_returns_dict_port_values_when_outputs_named_explicitly() -> None:
    """When the user fn returns a dict, the decorator maps by declared output names."""

    @graph_node(
        id="test.dict_output",
        region="think",
        inputs=("state",),
        outputs=("alpha", "beta"),
    )
    async def dict_output(*, state: AgentState) -> dict[str, int]:
        return {"alpha": 1, "beta": 2}

    executor = _executor(dict_output)
    state = _make_state()
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": state}),
    )

    assert out.port_values == {"alpha": 1, "beta": 2}


async def test_node_execute_returns_tuple_port_values_in_declared_order() -> None:
    """When the user fn returns a tuple, zip with declared output names."""

    @graph_node(
        id="test.tuple_output",
        region="think",
        inputs=("state",),
        outputs=("alpha", "beta"),
    )
    async def tuple_output(*, state: AgentState) -> tuple[int, str]:
        return (3, "ok")

    executor = _executor(tuple_output)
    state = _make_state()
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": state}),
    )

    assert out.port_values == {"alpha": 3, "beta": "ok"}


async def test_node_execute_evaluates_terminal_predicate_into_next_hint() -> None:
    """`terminal_predicate` verdict is stowed in `NodeOutput.next_hint`."""

    @graph_node(
        id="test.terminal",
        region="think",
        inputs=("state",),
        outputs=("decision",),
        terminal=lambda output, state: (
            ("exit", state)
            if output.get("decision", {}).get("action") == "respond"
            else ("continue", state)
        ),
    )
    async def terminal_fn(*, state: AgentState) -> dict[str, Any]:
        return {"action": "respond"}

    executor = _executor(terminal_fn)
    state = _make_state()
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": state}),
    )

    assert out.port_values == {"decision": {"action": "respond"}}
    assert out.next_hint == "exit"


async def test_node_execute_terminal_predicate_continue() -> None:
    """`terminal_predicate` returning "continue" puts next_hint == "continue"."""

    @graph_node(
        id="test.terminal_continue",
        region="think",
        inputs=("state",),
        outputs=("decision",),
        terminal=lambda output, state: ("continue", state),
    )
    async def terminal_continue(*, state: AgentState) -> dict[str, Any]:
        return {"action": "wait"}

    executor = _executor(terminal_continue)
    state = _make_state()
    out = await executor.node_execute(
        context=_node_context(),
        input=NodeInput(port_values={"state": state}),
    )

    assert out.next_hint == "continue"


async def test_node_execute_missing_required_port_raises_type_error() -> None:
    """When a port is declared but missing on both ports and runtime, raise TypeError.

    Mirrors `lca/plugins/think/history_assemble/execute.py:80-87` where
    ``writer=None`` raises ``TypeError("'writer' port must be...")``.
    """

    @graph_node(
        id="test.missing_port",
        region="think",
        inputs=("state",),
        outputs=("value",),
    )
    async def missing_port(*, state: AgentState) -> int:
        return 0

    executor = _executor(missing_port)
    with pytest.raises(TypeError, match="'state' port must be"):
        await executor.node_execute(
            context=_node_context(),
            input=NodeInput(port_values={}),
        )


# ── Region / id validation ───────────────────────────────────────


def test_graph_node_decorator_rejects_unknown_region() -> None:
    """`region` is constrained to the six-phase closed set (ADR-0227 §3)."""

    with pytest.raises(ValueError, match="region"):

        @graph_node(
            id="test.bad_region",
            region="not_a_phase",
            inputs=(),
            outputs=(),
        )
        async def bad_region() -> None:
            pass


def test_graph_node_decorator_accepts_all_six_phases() -> None:
    """All six phase regions must be accepted at decoration time."""
    for region in ("perceive", "think", "act", "remember", "reflect", "stop"):

        @graph_node(
            id=f"test.{region}.ok",
            region=region,
            inputs=(),
            outputs=(),
        )
        async def ok() -> None:
            pass

        assert _executor(ok).region == region


# ── Module re-export ─────────────────────────────────────────────


def test_decorator_module_is_importable() -> None:
    """`lca.framework.graph.nodes.decorator` is the public surface for `@graph_node`."""
    module = import_module("lca.framework.graph.nodes.decorator")
    assert callable(module.graph_node)
