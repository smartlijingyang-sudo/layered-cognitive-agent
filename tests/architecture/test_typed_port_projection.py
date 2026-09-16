"""ADR-0241 §1 — name-based typed-port projection at the subgraph seam.

The kernel projects outer input ports onto the inner declared inputs by
name, not by position. Three cases lock the contract:

1. outer feed 2 ports, inner declared 2 ports (same names) → inner sees
   both by name; order does not matter.
2. outer feed 3 ports, inner declared 1 port → inner sees only the 1
   named port it declared; the other 2 outer ports do NOT leak into
   the inner subgraph's input (avoid information leakage).
3. outer feed 1 port, inner declared 2 ports → inner sees the 1 outer
   port it can satisfy by name; the missing declared port is the
   kernel's responsibility (seeded at the outer plan entry — see
   ``tests/runtime/test_kernel_seeds_typed_ports.py``), not the
   translator's.

These tests pin :func:`lca.framework.graph.strategies.subgraph_run.translate_inputs`
so any positional-1:1 swap regression on the subgraph seam fails loud
at the architecture layer.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import (
    NodeInput,
    NodeIOSchema,
    PortSpec,
)
from lca.contracts.protocols.graph.plan import SubgraphReference
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.framework.graph.strategies.subgraph_run import translate_inputs


def _ctx(*, inner_input_names: tuple[str, ...]) -> StrategyContext:
    """Build a StrategyContext with the given inner declared input names."""
    return StrategyContext(
        plan_ref="outer",
        node_id="n",
        binding_kind=BindingKind.SUBGRAPH,
        node_config={},
        subgraph_ref=SubgraphReference(
            plan_ref="bundles/x.yaml",
            entry_node="entry",
            binding_edge="next",
        ),
        chain=(),
        inner_io_schema=NodeIOSchema(
            inputs=tuple(PortSpec(name=n) for n in inner_input_names),
        ),
    )


def test_case1_outer_two_inner_two_by_name() -> None:
    """Outer feeds 2 ports with same names as inner declared → all by name."""
    context = _ctx(inner_input_names=("bindings", "tools"))
    inp = NodeInput(
        port_values={
            "bindings": "B",
            "tools": "T",
        },
        consumer_node="n",
    )
    assert translate_inputs(context, inp) == {"bindings": "B", "tools": "T"}


def test_case1_outer_two_inner_two_order_independent() -> None:
    """Outer order does not matter when names match inner declared (1:1)."""
    context = _ctx(inner_input_names=("tools", "bindings"))
    inp = NodeInput(
        port_values={
            "bindings": "B",
            "tools": "T",
        },
        consumer_node="n",
    )
    # Name-based projection: inner sees 'tools' first, 'bindings' second
    # regardless of outer order. Positional 1:1 would have flipped them.
    assert translate_inputs(context, inp) == {"tools": "T", "bindings": "B"}


def test_case2_outer_three_inner_one_only_named_port() -> None:
    """Inner declared 1 port; outer feeds 3 → inner sees only the named 1.

    Outer ports not declared by inner MUST NOT leak into the inner
    subgraph's input (no information leakage across the seam).
    """
    context = _ctx(inner_input_names=("tools",))
    inp = NodeInput(
        port_values={
            "tools": "T",
            "bindings": "B",
            "extra_outer_port": "X",
        },
        consumer_node="n",
    )
    result = translate_inputs(context, inp)
    assert result == {"tools": "T"}
    assert "bindings" not in result
    assert "extra_outer_port" not in result


def test_case3_outer_one_inner_two_only_named_present() -> None:
    """Outer feeds 1 port with name that matches one of inner declared 2."""
    context = _ctx(inner_input_names=("bindings", "tools"))
    inp = NodeInput(
        port_values={"tools": "T"},
        consumer_node="n",
    )
    # Inner declared `bindings` is missing — the translator does NOT
    # silently fall back; the kernel must seed it at the outer plan
    # entry (see ``test_kernel_seeds_typed_ports``). The translator
    # itself only returns what outer can satisfy by name.
    assert translate_inputs(context, inp) == {"tools": "T"}


def test_translate_inputs_no_inner_schema_returns_outer_unchanged() -> None:
    """When inner_io_schema is None (identity translation), outer passes through."""
    context = StrategyContext(
        plan_ref="outer",
        node_id="n",
        binding_kind=BindingKind.SUBGRAPH,
        node_config={},
        subgraph_ref=None,
        chain=(),
        inner_io_schema=None,
    )
    inp = NodeInput(port_values={"tools": "T", "bindings": "B"}, consumer_node="n")
    assert translate_inputs(context, inp) == {"tools": "T", "bindings": "B"}


def test_translate_inputs_empty_inner_declared_returns_outer() -> None:
    """Inner declared no inputs → no projection; outer passes through unchanged."""
    context = _ctx(inner_input_names=())
    inp = NodeInput(
        port_values={"tools": "T", "bindings": "B"},
        consumer_node="n",
    )
    # Empty inner declared means "no port contract required" → the
    # outer feed is forwarded as-is. This is the legacy identity path
    # for subgraphs that don't declare an inner_io_schema.
    assert translate_inputs(context, inp) == {"tools": "T", "bindings": "B"}


def test_translate_inputs_empty_outer_no_inner_match() -> None:
    """Outer empty, inner declared → translator returns empty dict.

    The missing inner ports are the kernel's responsibility (seeded at
    the outer plan entry); the translator never invents values.
    """
    context = _ctx(inner_input_names=("bindings", "tools"))
    inp = NodeInput(port_values={}, consumer_node="n")
    assert translate_inputs(context, inp) == {}
