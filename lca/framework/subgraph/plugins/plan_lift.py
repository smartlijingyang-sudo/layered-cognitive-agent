"""PlanLifter — adapter from compiled plan to v2 BundleGraphSpec.

The subgraph runner's only call into this module is
:func:`lift_subgraph_reference_to_v2`. The function is the **single
decision point** in the think subgraph pipeline (per plan §3.3):

    old plan form ──lift──> BundleGraphSpec ──> NodeGraphDriver

After this point nothing in the framework consumes the old plan form;
10│  the BundleGraphSpec is the only driver input.

ADR-0220 P9 history: the v1 helper ``_strip_think_reason_complete`` and
the ``strip_complete_when_no_llm`` parameter used to drop the
``think.reason.complete`` node when the Default factory ran without an
LLM. The Default reasoner now implements ``complete_turn`` (the typed
``ForkedTools`` boundary from P5 / ``primitive.llm.call`` makes the LLM
call typed and reachable from any factory wiring), so the strip is no
longer needed. P9 deletes both.

This module does not carry ``@plugin`` (per plan §13.2 / R4): the
lifter is a pure function the runner calls, not a capability provider.
The runner injects it via a hard import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
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
) -> BundleGraphSpec:
    """Return the :class:`BundleGraphSpec` for ``ref``'s resolved plan.

    The function is the only place where the old plan form is read in
    the think subgraph path. After this call the returned spec is
    consumed by :class:`lca.framework.subgraph.plugins.node_graph_driver.NodeGraphDriver`.

    Args:
        ref: Subgraph reference resolved by the runner.
        sub_plan_obj: Compiled plan implementing the v2 marker.

    Raises:
        PlanLiftError: ``sub_plan_obj`` does not implement the v2
            marker. This is a fail-loud signal that the resolver
            returned a plan of an unsupported shape; callers must
            surface it before the driver sees a half-built spec.
    """
    if not isinstance(sub_plan_obj, V2BundleGraphPlanMarker):
        raise PlanLiftError(
            f"sub_plan_obj for ref.plan_ref={ref.plan_ref!r} does not implement "
            "V2BundleGraphPlanMarker; only Bundle Graph Schema v2 plans are "
            "supported by the subgraph driver."
        )
    return sub_plan_obj.get_bundle_graph_spec()


__all__ = ["PlanLiftError", "lift_subgraph_reference_to_v2"]
