"""spine_reflector_phase_graph plugin（ADR-0181 PR-5）。

PR-5：phase_graph 全部 4 emit 下沉到 EventMechanism.send：
- phase_graph.node.start / .end
- phase_graph.edge.transit
- phase_graph.instrument.coverage
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

if TYPE_CHECKING:
    from lca_kernel.events.mechanism import EventRef

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    from lca_kernel.events.mechanism import EventMechanism

    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventMechanism.default().send(sp, plugin=ReflectorClass)


# ── phase_graph.node.start / .end ─────────────────────────────────────


def emit_phase_graph_node_start(*, node_id: str, run_id: str) -> EventRef:
    return _send(
        execution_point="phase_graph.node.start",
        channel="control",
        payload={"node_id": node_id, "run_id": run_id},
    )


def emit_phase_graph_node_end(
    *,
    node_id: str,
    run_id: str,
    outcome: str = "success",
) -> EventRef:
    return _send(
        execution_point="phase_graph.node.end",
        channel="control",
        payload={"node_id": node_id, "run_id": run_id, "outcome": outcome},
    )


# ── phase_graph.edge.transit ─────────────────────────────────────────


def emit_phase_graph_edge_transit(
    *,
    from_node: str,
    to_node: str,
    run_id: str,
) -> EventRef:
    return _send(
        execution_point="phase_graph.edge.transit",
        channel="control",
        payload={"from_node": from_node, "to_node": to_node, "run_id": run_id},
    )


# ── phase_graph.instrument.coverage ──────────────────────────────────


def emit_phase_graph_instrument_coverage(
    *,
    covered_nodes: int,
    total_nodes: int,
    run_id: str,
) -> EventRef:
    return _send(
        execution_point="phase_graph.instrument.coverage",
        channel="diagnostic",
        payload={
            "covered_nodes": covered_nodes,
            "total_nodes": total_nodes,
            "run_id": run_id,
        },
    )


__all__ = [
    "ReflectorClass",
    "emit_phase_graph_edge_transit",
    "emit_phase_graph_instrument_coverage",
    "emit_phase_graph_node_end",
    "emit_phase_graph_node_start",
]
