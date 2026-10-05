"""region.plan shared helpers — ADR-0228 plan node internals.

Internal seam for the plan region nodes (compose / revise): pure
helpers that both nodes need, without making the two sibling node
modules import each other.
"""

from __future__ import annotations

from lca.contracts.models.cognition.task import TaskList


def _extract_task_list(state: object) -> TaskList:
    """Resolve the current ``TaskList`` from the state port value.

    Accepts a bare ``TaskList`` (typed shortcut projection) or an
    ``AgentState`` carrying the ``task_list`` field added by ADR-0228.
    Missing / unset → empty list so the node always produces a valid
    typed artifact (C6 minimization).
    """
    if isinstance(state, TaskList):
        return state
    candidate: object = getattr(state, "task_list", None)
    if isinstance(candidate, TaskList):
        return candidate
    return TaskList()
