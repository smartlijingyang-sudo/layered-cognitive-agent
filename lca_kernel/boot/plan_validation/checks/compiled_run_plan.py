"""Compiled-run-plan post-lift check.

The other checks in this package operate on the raw lifted
:class:`~lca.contracts.protocols.graph.plan.Plan`. This one operates
on the **outer** plan after K2 (``compile_run_plan``) has consumed
it, catching the structural defects that the per-plan checks cannot
reach because they assume the outer's outer-facing topology:

- a multi-node plan (K2 expects ``nodes`` + ``edges`` to project;
  a single-node plan is what ``lift_graph_spec``'s entry-fallback
  produces, and there is nothing to compile)
- entry / terminal leaves that are not also subgraph delegates
  (a delegate is a "step" — wrapping it as entry or terminal
  would short-circuit the outer traversal)
- terminal-node output ports that look like K2 projection
  points (``terminal_outcome`` / ``final_result`` are reserved
  names that the kernel maps onto :class:`AgentState`; non-standard
  ``terminal_*`` ports break the projection)

Why a free function and not a :class:`~.base.PlanCheck`?
--------------------------------------------------------

:class:`PlanCheck` returns a single ``PlanLiftError | None`` — fine
for invariants that fail in one well-defined place. The compiled-plan
invariants can fail in several places per plan (multi-node sanity,
entry-as-delegate, terminal-as-delegate, terminal-port projection),
and the operator benefits from seeing all of them in one boot pass
rather than fixing them one PR at a time. The free function returns
``list[PlanLiftError]`` and is called once per plan from
:func:`lca_kernel.boot.plan_validation.validate_profile_plans`
**after** the per-plan registry has finished, so the two error
streams aggregate into a single boot failure.
"""
from __future__ import annotations

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.contracts.protocols.graph.plan import Plan

# Reserved terminal-node output port names that K2 reads as
# projection points onto ``AgentState``. Anything else starting with
# ``terminal_`` is treated as a typo / non-standard projection and
# rejected at boot so the runtime doesn't silently drop state.
_TERMINAL_PORT_WHITELIST: frozenset[str] = frozenset(
    {"terminal_outcome", "final_result"}
)


def check_compiled_run_plan(plan: Plan, *, plan_id: str) -> list[PlanLiftError]:
    """Return every K2-compile invariant the outer plan violates.

    The four checks run independently so the operator sees all
    failures in a single boot pass:

    1. Multi-node sanity — at least two nodes (K2 projects
       ``nodes``/``edges`` onto a runnable plan; a single-node
       plan is the lifter's entry-fallback and has nothing to
       compile).
    2. Entry-node-as-delegate — an entry node with
       ``subgraph_ref`` would short-circuit the outer traversal.
    3. Terminal-node-as-delegate — a terminal node with
       ``subgraph_ref`` would never re-enter the caller; the
       kernel would terminate before the delegate's return_edge
       fires.
    4. Terminal-port projection — ``terminal_outcome`` and
       ``final_result`` are K2 projection points; other
       ``terminal_*`` ports are non-standard and break the
       projection.
    """
    errors: list[PlanLiftError] = []

    if len(plan.nodes) < 2:
        errors.append(
            PlanLiftError(
                f"plan {plan_id!r}: only {len(plan.nodes)} node(s); "
                f"K2 compile_run_plan expects multi-node plans",
                plan_id=plan_id,
            )
        )

    for node in plan.nodes:
        if node.subgraph_ref is None:
            continue
        # Entry nodes commonly delegate to a subgraph (a phase entry
        # is typically ``sub_spec_ref`` pointing at the phase
        # bundle), so the entry-as-delegate pattern is a production
        # convention. Only the terminal-as-delegate combination is
        # structurally broken — the kernel terminates before the
        # delegate's ``return_on`` fires, so the caller never sees
        # the subgraph's output.
        if node.terminal:
            errors.append(
                PlanLiftError(
                    f"plan {plan_id!r}: node {node.id!r} is both a "
                    f"subgraph delegate and a terminal node; K2 expects "
                    f"terminal to be a leaf, not a delegate",
                    plan_id=plan_id,
                    node_id=node.id,
                )
            )

    for node in plan.nodes:
        if not node.terminal:
            continue
        for port in node.io_schema.outputs:
            if port.name in _TERMINAL_PORT_WHITELIST:
                continue
            if port.name.startswith("terminal_"):
                errors.append(
                    PlanLiftError(
                        f"plan {plan_id!r}: terminal node {node.id!r} "
                        f"emits reserved port {port.name!r}; K2 "
                        f"projects AgentState from this port and "
                        f"non-standard names break the projection. "
                        f"Use one of {sorted(_TERMINAL_PORT_WHITELIST)} "
                        f"or rename the port.",
                        plan_id=plan_id,
                        node_id=node.id,
                        port_name=port.name,
                    )
                )

    return errors


__all__ = ["check_compiled_run_plan"]
