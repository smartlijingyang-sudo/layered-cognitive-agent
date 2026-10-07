"""Align the run budget (``max_steps``) with graph loop bounds (RA-023).

A plan's ``loop.maxIterations`` is a per-edge safety cap written by the
profile author (e.g. the act→think re-ask loop allows 24 rounds in
``bundles/outer/phase_main.yaml``); ``max_steps`` is the caller's
"at most N agent steps" contract carried on ``AgentState.budget``.
The two limits count the same thing: each take of a bounded re-entry
edge is one agent iteration (one LLM call + dispatch), and the edge
loop even declares ``budget: run.steps``.

The translation rule is ``min``: ``max_steps`` can only *tighten* a
plan bound, never loosen it — the profile's own cap stays the ultimate
safety. Non-convergence at either bound still raises
``LoopObligationExceededError`` from the interpreter; the agent layer
(:meth:`CognitiveAgent._run_lifecycle_body`) translates that raise into
a failed ``Result`` instead of letting it escape ``run()``.
"""

from __future__ import annotations

from lca.contracts.protocols.graph.plan import Plan


def clamp_loop_bounds(plan: Plan, *, max_steps: int | None) -> Plan:
    """Return ``plan`` with every loop bound tightened to ``max_steps``.

    Plans are frozen pydantic models, so this builds copies — the
    compiled plan owned by the bindings is never mutated. Edges without
    a loop obligation, a ``None`` budget, and bounds already at or below
    ``max_steps`` are returned untouched (the same ``plan`` object).
    """
    if max_steps is None:
        return plan
    edges = []
    changed = False
    for edge in plan.edges:
        loop = edge.loop
        if loop is not None and loop.max_iterations > max_steps:
            loop = loop.model_copy(update={"max_iterations": max_steps})
            edge = edge.model_copy(update={"loop": loop})
            changed = True
        edges.append(edge)
    if not changed:
        return plan
    return plan.model_copy(update={"edges": tuple(edges)})


__all__ = ["clamp_loop_bounds"]
