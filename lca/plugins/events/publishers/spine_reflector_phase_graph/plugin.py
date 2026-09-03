"""spine_reflector_phase_graph plugin（ADR-0181 PR-5 / ADR-0183 PR-7）。

PR-5：phase_graph 全部 4 emit 下沉到 EventBus.publish：
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
    from lca_kernel.events.bus import EventRef

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    from lca_kernel.events.bus import EventBus

    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


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
    "setup",
]




class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine.reflector.phase_graph",
    provides=["event.bus.reflector.phase_graph"],
    requires=["event.bus"],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "phase_graph publisher（ADR-0181）：event.bus.reflector.phase_graph 由本 plugin 发出。"
    ),
    test_suite="tests/plugins/events/publishers/test_events_spine_reflector_phase_graph.py",
    functional_group=FunctionalGroup.G6_DECISION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.phase_graph.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.phase_graph.node.start",
            "spine.phase_graph.node.end",
            "spine.phase_graph.edge.transit",
            "spine.phase_graph.instrument.coverage",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """events.spine.reflector.phase_graph boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.reflector.phase_graph", ReflectorClass)

