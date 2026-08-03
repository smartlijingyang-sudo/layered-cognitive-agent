"""Team domain language: LeadMandate + Coordination value objects (ADR-0030)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from lca.contracts.enums import DecisionGateName

if TYPE_CHECKING:
    from lca.contracts.graph import ExecutionGraph

STRATEGY_KEY_LEAD = "lead"
STRATEGY_KEY_PIPELINE = "pipeline"
STRATEGY_KEY_FAN_OUT = "fan_out"
STRATEGY_KEY_PEER_RELAY = "peer_relay"
STRATEGY_KEY_PEER_SWARM = "peer_swarm"
STRATEGY_KEY_DEBATE = "debate"
STRATEGY_KEY_GRAPH = "graph"


class LeadMandate(str, Enum):
    """Authority and obligations of a TeamLead (closed set)."""

    ROUTING = "routing"
    """Free assignment; no full-roster settlement duty."""

    CONSULT = "consult"
    """Roster-aware board; settlement not forced."""

    BOARD = "board"
    """Must consult all required members before final respond."""


@dataclass(frozen=True)
class Pipeline:
    """Members in order; prior output becomes next task."""


@dataclass(frozen=True)
class FanOut:
    """All members run the same objective concurrently."""


@dataclass(frozen=True)
class PeerRelay:
    """Peers tried in order; first completed result wins."""


@dataclass(frozen=True)
class PeerSwarm:
    """Round-robin peers with context accumulation."""

    max_rounds: int = 3


@dataclass(frozen=True)
class Debate:
    """Multi-round peer debate."""

    max_rounds: int = 3


@dataclass(frozen=True)
class Graph:
    """Explicit DAG execution."""

    execution_graph: ExecutionGraph


Coordination = Pipeline | FanOut | PeerRelay | PeerSwarm | Debate | Graph


def strategy_key_for_coordination(coordination: Coordination) -> str:
    if isinstance(coordination, Pipeline):
        return STRATEGY_KEY_PIPELINE
    if isinstance(coordination, FanOut):
        return STRATEGY_KEY_FAN_OUT
    if isinstance(coordination, PeerRelay):
        return STRATEGY_KEY_PEER_RELAY
    if isinstance(coordination, PeerSwarm):
        return STRATEGY_KEY_PEER_SWARM
    if isinstance(coordination, Debate):
        return STRATEGY_KEY_DEBATE
    if isinstance(coordination, Graph):
        return STRATEGY_KEY_GRAPH
    raise TypeError(f"unknown coordination type: {type(coordination)!r}")


def strategy_key_for_lead() -> str:
    return STRATEGY_KEY_LEAD


def gate_name_for_mandate(mandate: LeadMandate) -> DecisionGateName:
    if mandate is LeadMandate.BOARD:
        return DecisionGateName.MUST_CONSULT_ALL
    return DecisionGateName.NONE


def mandate_uses_consultation_session(mandate: LeadMandate) -> bool:
    return mandate is not LeadMandate.ROUTING


def max_rounds_from_coordination(coordination: Coordination) -> int | None:
    if isinstance(coordination, (PeerSwarm, Debate)):
        return coordination.max_rounds
    return None
