"""Name-based subgraph output translation regression tests.

The reflect subgraph's entry node lists ``observation`` before
``reflection`` in its output schema, while the terminal node emits
``reflection`` and ``routing``. Positional translation by the entry
schema used to map outer ``reflection`` to the inner ``observation``
and outer ``routing`` to the inner ``reflection``, silently dropping
the reflection (and with it the semantic memory candidate) before
``remember.main``. Name-based translation fixes the seam.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.binding import BindingKind
from lca.contracts.protocols.graph.node_io import NodeIOSchema, PortSpec
from lca.contracts.protocols.graph.strategy import StrategyContext
from lca.framework.graph.strategies.subgraph_run import translate_outputs


def _context(
    *,
    outer_outputs: list[str],
    inner_entry_outputs: list[str],
) -> StrategyContext:
    return StrategyContext(
        plan_ref="outer.yaml",
        node_id="reflect.main",
        binding_kind=BindingKind.SUBGRAPH,
        node_config={"declared_outputs": outer_outputs},
        inner_io_schema=NodeIOSchema(
            inputs=(),
            outputs=tuple(PortSpec(name=n) for n in inner_entry_outputs),
        ),
    )


def test_name_based_mapping_wins_over_positional() -> None:
    reflection = {"reflection_id": "refl_1", "extra": {"memory_candidate": {}}}
    merged = {
        "observation": {"manifest": "obs"},
        "reflection": reflection,
        "routing": {"action_type": "respond"},
    }
    ctx = _context(
        outer_outputs=["reflection", "routing"],
        inner_entry_outputs=["observation", "reflection"],
    )
    translated = translate_outputs(ctx, merged)
    assert translated["reflection"] is reflection
    assert translated["routing"] == {"action_type": "respond"}


def test_positional_fallback_when_names_differ() -> None:
    merged = {"inner_a": "A", "inner_b": "B"}
    ctx = _context(
        outer_outputs=["outer_a", "outer_b"],
        inner_entry_outputs=["inner_a", "inner_b"],
    )
    translated = translate_outputs(ctx, merged)
    assert translated == {"outer_a": "A", "outer_b": "B"}
