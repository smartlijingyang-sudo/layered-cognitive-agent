"""SupervisorMode closed set + Recipe — user/config surface for SUPERVISOR (ADR-0029).

Illegal plane×gate products are not representable. DecisionGateName remains a
registry key resolved from Mode, not a peer user knob.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from lca.contracts.enums import DecisionGateName, TeamProcess


class SupervisorMode(str, Enum):
    """Closed SUPERVISOR product modes (not free plane×gate product)."""

    ROUTING = "routing"
    """Free PM — RoutingState, no settlement gate."""

    CONSULTATION = "consultation"
    """Board + roster, free settle (gate none)."""

    BOARD = "board"
    """Full-roster consultation settlement (must_consult_all)."""


class Recipe(str, Enum):
    """L-User team recipes — expand to process (+ optional SupervisorMode)."""

    PIPELINE = "pipeline"
    FANOUT = "fanout"
    MANAGER = "manager"
    CONSULT = "consult"
    BOARD = "board"
    RELAY = "relay"
    SWARM = "swarm"
    GRAPH = "graph"
    DEBATE = "debate"


# recipe -> (process, supervisor_mode | None)
RECIPE_EXPAND: Final[dict[Recipe, tuple[TeamProcess, SupervisorMode | None]]] = {
    Recipe.PIPELINE: (TeamProcess.SEQUENTIAL, None),
    Recipe.FANOUT: (TeamProcess.PARALLEL, None),
    Recipe.MANAGER: (TeamProcess.HIERARCHICAL, SupervisorMode.ROUTING),
    Recipe.CONSULT: (TeamProcess.HIERARCHICAL, SupervisorMode.CONSULTATION),
    Recipe.BOARD: (TeamProcess.HIERARCHICAL, SupervisorMode.BOARD),
    Recipe.RELAY: (TeamProcess.HANDOFF, None),
    Recipe.SWARM: (TeamProcess.SWARM, None),
    Recipe.GRAPH: (TeamProcess.GRAPH, None),
    Recipe.DEBATE: (TeamProcess.DEBATE, None),
}


def decision_gate_name_for_mode(mode: SupervisorMode) -> DecisionGateName:
    """Registry key for optional DecisionGate; NONE means no gate instance."""
    if mode is SupervisorMode.BOARD:
        return DecisionGateName.MUST_CONSULT_ALL
    return DecisionGateName.NONE


def mode_uses_consultation_session(mode: SupervisorMode) -> bool:
    return mode is not SupervisorMode.ROUTING


def expand_recipe(recipe: Recipe) -> tuple[TeamProcess, SupervisorMode | None]:
    return RECIPE_EXPAND[recipe]
