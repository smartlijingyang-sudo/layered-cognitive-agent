"""Orchestration families, process→family map, and industry pattern slots.

See ADR-0027. Pure taxonomy (no behavior).
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from lca.contracts.enums import TeamProcess


class OrchestrationFamily(str, Enum):
    """Who holds scheduling authority for a team run."""

    SUPERVISOR = "supervisor"
    CHOREOGRAPHY = "choreography"
    PEER = "peer"
    GRAPH = "graph"


class SupervisorPlane(str, Enum):
    """Control-plane kind for SUPERVISOR-family processes only."""

    CONSULTATION = "consultation"
    """``ConsultationState`` + optional settlement gates."""

    ROUTING = "routing"
    """``RoutingState`` freeform PM — no full-roster settlement."""


PROCESS_FAMILY: Final[dict[TeamProcess, OrchestrationFamily]] = {
    TeamProcess.HIERARCHICAL: OrchestrationFamily.SUPERVISOR,
    TeamProcess.SEQUENTIAL: OrchestrationFamily.CHOREOGRAPHY,
    TeamProcess.PARALLEL: OrchestrationFamily.CHOREOGRAPHY,
    TeamProcess.DEBATE: OrchestrationFamily.CHOREOGRAPHY,
    TeamProcess.HANDOFF: OrchestrationFamily.PEER,
    TeamProcess.SWARM: OrchestrationFamily.PEER,
    TeamProcess.GRAPH: OrchestrationFamily.GRAPH,
}


# Names reserved for future TeamProcess values (not enum members yet).
RESERVED_PROCESS_SLOTS: Final[frozenset[str]] = frozenset(
    {
        "supervisor_routing",  # optional alias process; plane=ROUTING covers it
        "consensus",
    }
)


INDUSTRY_PATTERN_SLOTS: Final[dict[str, str]] = {
    "crew_sequential": "process=sequential family=choreography",
    "crew_hierarchical_free": (
        "process=hierarchical decision_gate=none plane=routing|consultation"
    ),
    "crew_hierarchical_must_consult": (
        "process=hierarchical decision_gate=must_consult_all plane=consultation"
    ),
    "langgraph_supervisor": "process=hierarchical + multi-delegate fan-out",
    "langgraph_subagents_as_tools": "ActionType.DELEGATE + AgentTransport",
    "langgraph_swarm": "process=swarm family=peer",
    "openai_swarm_handoff": "process=handoff|swarm family=peer",
    "scatter_gather": "process=parallel family=choreography",
    "explicit_dag": "process=graph family=graph",
    "nested_supervisors": "nested TeamUnit / graph subgraph (TBD)",
}


def family_of(process: TeamProcess) -> OrchestrationFamily:
    """Return the orchestration family for *process*."""
    return PROCESS_FAMILY[process]


def assert_process_family_complete() -> None:
    """Raise AssertionError if PROCESS_FAMILY drifts from TeamProcess members."""
    actual = set(PROCESS_FAMILY)
    expected = set(TeamProcess)
    if actual != expected:
        missing = expected - actual
        extra = actual - expected
        raise AssertionError(
            "PROCESS_FAMILY must cover every TeamProcess exactly once. "
            f"missing={sorted(m.value for m in missing)} "
            f"extra={sorted(e.value for e in extra)}"
        )
    overlap = RESERVED_PROCESS_SLOTS & {p.value for p in TeamProcess}
    if overlap:
        raise AssertionError(
            f"RESERVED_PROCESS_SLOTS collide with live TeamProcess values: {sorted(overlap)}"
        )
