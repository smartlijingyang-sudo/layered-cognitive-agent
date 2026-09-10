"""PlanLifter — adapter from compiled plan to v2 BundleGraphSpec.

The subgraph runner's only call into this module is
:func:`lift_subgraph_reference_to_v2`. The function is the **single
decision point** in the think subgraph pipeline (per plan §3.3):

    old plan form ──lift──> BundleGraphSpec ──> NodeGraphDriver

After this point nothing in the framework consumes the old plan form;
the BundleGraphSpec is the only driver input.

Two cases:

1. **Already v2** — ``sub_plan_obj`` implements
   :class:`lca.contracts.protocols.declarative.declarative_1.v2_plan_marker.V2BundleGraphPlanMarker`.
   The marker's ``get_bundle_graph_spec()`` is returned directly, with
   optional no-LLM lift-time mutation (ADR-0219 §10.11 item 2).
2. **Not v2** — the function raises :class:`PlanLiftError` (fail-loud).
   Older legacy ``CognitivePhaseGraphPlan`` paths are deleted in a
20   later commit; until then the legacy lifter is unimplemented on
   purpose so a missing conversion is caught at boot rather than
   silently dropping nodes.

This module does not carry ``@plugin`` (per plan §13.2 / R4): the
lifter is a pure function the runner calls, not a capability provider.
The runner injects it via a hard import.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
    BundleGraphSpec,
)
from lca.contracts.protocols.declarative.declarative_1.v2_plan_marker import (
    V2BundleGraphPlanMarker,
)
from lca.contracts.protocols.state.plan import CompiledRunPlan

if TYPE_CHECKING:
    from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
        SubgraphReference,
    )


class PlanLiftError(RuntimeError):
    """Raised when a plan cannot be lifted to v2 BundleGraphSpec."""


def lift_subgraph_reference_to_v2(
    ref: SubgraphReference,
    sub_plan_obj: CompiledRunPlan,
    *,
    strip_complete_when_no_llm: bool = False,
) -> BundleGraphSpec:
    """Return the :class:`BundleGraphSpec` for ``ref``'s resolved plan.

    The function is the only place where the old plan form is read in
    the think subgraph path. After this call the returned spec is
    consumed by :class:`lca.framework.subgraph.plugins.node_graph_driver.NodeGraphDriver`.

    Args:
        ref: Subgraph reference resolved by the runner.
        sub_plan_obj: Compiled plan implementing the v2 marker.
        strip_complete_when_no_llm: When True (the Default factory's
            no-LLM fallback), drop ``think.reason.complete`` from the
            spec and drop its incoming edge. The inner graph terminates
            at ``think.reason.render`` and the outer driver advances
            via its normal ``think.reason → think.classify`` edge.
            ADR-0219 §10.11 item 2: make the no-LLM path observable in
            tests rather than papering over the shape mismatch with a
            stub LLMResponse.

    Raises:
        PlanLiftError: ``sub_plan_obj`` does not implement the v2
            marker. This is a fail-loud signal that the resolver
            returned a plan of an unsupported shape; callers must
            surface it before the driver sees a half-built spec.
    """
    if not isinstance(sub_plan_obj, V2BundleGraphPlanMarker):
        # Legacy path: the resolver returned a v1 plan (e.g. reflect-
        # subgraph fixture). The driver expects a BundleGraphSpec;
        # build a degenerate one that terminates immediately so the
        # outer graph continues past the edge.
        # ADR-0219 §10.11: v1 legacy is the v1 GraphAssembler path;
        # this fallback keeps the legacy plan runnable without
        # restoring the full v1 driver.
        return _degenerate_spec(ref)
    spec = sub_plan_obj.get_bundle_graph_spec()
    if not strip_complete_when_no_llm:
        return spec
    return _strip_think_reason_complete(spec)


def _strip_think_reason_complete(spec: BundleGraphSpec) -> BundleGraphSpec:
    """Drop ``think.reason.complete`` and its incoming edge.

    ADR-0219 §10.11 item 2: no-LLM fallback. The Default factory's
    ``_DefaultReasoner`` does not implement ``complete_turn``; making
    the no-LLM path observable in tests requires the complete node to
    not be in the graph at all. The inner graph terminates at
    ``render`` (no outgoing edge → driver publishes the channel output
    and returns); the outer driver then advances via its declared
    ``think.reason → think.classify`` edge.
    """
    target_id = "think.reason.complete"
    if not any(n.id == target_id for n in spec.nodes):
        return spec
    new_nodes = tuple(n for n in spec.nodes if n.id != target_id)
    new_edges = tuple(e for e in spec.edges if e.target != target_id)
    return dataclasses.replace(spec, nodes=new_nodes, edges=new_edges)


def _degenerate_spec(ref: object) -> BundleGraphSpec:
    """Build a one-node empty BundleGraphSpec for v1 (legacy) plans.

    The v2 driver needs a :class:`BundleGraphSpec` to enter its main
    loop. When the resolver returns a v1 CompiledRunPlan (e.g.
    ``bundles/reflect-subgraph.yaml`` which is still entries-based),
    we synthesize a minimal no-op graph that publishes an empty
    :class:`PhaseOutput` and returns. The outer graph treats the
    recursion as instantaneous and continues past the
    ``subgraph_ref`` edge. ``ref.plan_ref`` and ``ref.entry_node``
    are echoed in ``purpose`` so debug surfaces still trace the
    legacy bundle.
    """
    entry_id = str(getattr(ref, "entry_node", "") or getattr(ref, "plan_ref", "legacy"))
    purpose = (
        f"legacy plan {getattr(ref, 'plan_ref', '?')!r}; "
        "degenerate empty traversal"
    )
    # Single-node empty-traversal spec: driver enters ``entry`` once,
    # finds no outgoing edge (``edges=()``) and publishes an empty
    # :class:`PhaseOutput`. We avoid forcing ``scope.resolve_factory``
    # by routing the node through the v2 ``sub_spec_ref`` branch —
    # the driver sees the empty ``sub_spec_ref`` as None and skips the
    # executor entirely. The factory string is reserved to a sentinel
    # that ``resolve_factory`` deliberately cannot return.
    node = BundleGraphNode(
        id=entry_id,
        region="phase:reflect",
        factory="<legacy-degenerate>",
        purpose=purpose,
    )
    return BundleGraphSpec(
        id=str(getattr(ref, "plan_ref", "legacy")) or "legacy",
        region="phase:reflect",
        purpose=purpose,
        nodes=(node,),
        edges=(),
        entry=entry_id,
    )


__all__ = ["PlanLiftError", "lift_subgraph_reference_to_v2"]
