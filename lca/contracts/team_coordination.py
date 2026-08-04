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

DEFAULT_COORDINATION_MAX_ROUNDS = 3
"""轮次型协调机制（PeerSwarm / Debate）的默认轮数上限。"""


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

    max_rounds: int = DEFAULT_COORDINATION_MAX_ROUNDS


@dataclass(frozen=True)
class Debate:
    """Multi-round peer debate."""

    max_rounds: int = DEFAULT_COORDINATION_MAX_ROUNDS


@dataclass(frozen=True)
class Graph:
    """Explicit DAG execution."""

    execution_graph: ExecutionGraph


Coordination = Pipeline | FanOut | PeerRelay | PeerSwarm | Debate | Graph


_COORDINATION_STRATEGY_KEYS: dict[type, str] = {
    Pipeline: STRATEGY_KEY_PIPELINE,
    FanOut: STRATEGY_KEY_FAN_OUT,
    PeerRelay: STRATEGY_KEY_PEER_RELAY,
    PeerSwarm: STRATEGY_KEY_PEER_SWARM,
    Debate: STRATEGY_KEY_DEBATE,
    Graph: STRATEGY_KEY_GRAPH,
}
"""Coordination 类型 → 策略注册键的声明式映射（数据驱动分发，无 if 链）。"""

_MANDATE_DECISION_GATES: dict[LeadMandate, DecisionGateName] = {
    LeadMandate.BOARD: DecisionGateName.MUST_CONSULT_ALL,
}
"""LeadMandate → DecisionGate 注册名的展开表；未列出者为 NONE。"""


def strategy_key_for_coordination(coordination: Coordination) -> str:
    key = _COORDINATION_STRATEGY_KEYS.get(type(coordination))
    if key is None:
        raise TypeError(f"unknown coordination type: {type(coordination)!r}")
    return key


def gate_name_for_mandate(mandate: LeadMandate) -> DecisionGateName:
    return _MANDATE_DECISION_GATES.get(mandate, DecisionGateName.NONE)
