"""Hook seam for the declarative phase graph interpreter.

The interpreter emits subgraph enter/exit observations through a passive
seam (``SubgraphHookEmitter``) without statically importing
``lca.plugins.lab``. Boot adapters translate these harness-local events
into the legacy ``lca.plugins.lab.internal.hooks.fanout_hooks`` path.

Why the seam exists:
    * ``lca.harness`` must not import ``lca.plugins`` (import-linter
      business-event-isolation rule).
    * The HookContext dataclass lives in ``lca.plugins.lab.internal.hooks``
      and is therefore invisible to the interpreter.
    * We define a harness-local ``SubgraphHookEvent`` enum and
      ``SubgraphHookContext`` dataclass that captures only the subgraph
      fields the interpreter actually carries (plan_ref, entry_node,
      binding_edge, depth, parent_path, node_id, edge_id).
    * ``SubgraphHookEmitter.emit`` is a noop for the default
      ``NullSubgraphHookEmitter`` so unit tests stay self-contained.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class SubgraphHookEvent(StrEnum):
    """Closed set of subgraph-observation events the interpreter emits."""

    SUBGRAPH_ENTER = "subgraph_enter"
    SUBGRAPH_EXIT = "subgraph_exit"


@dataclass(frozen=True, slots=True)
class SubgraphHookContext:
    """Carrier-safe payload for one subgraph hook emission.

    The interpreter builds one of these around every ``PhaseEdge.subgraph_ref``
    traversal. Boot adapters map the fields onto the agent_lab HookContext
    schema (subgraph_path / node_id / edge_id / payload) when wiring the
    fanout to ``lca.plugins.lab.internal.hooks.fanout_hooks``.
    """

    event: SubgraphHookEvent
    plan_ref: str
    entry_node: str
    binding_edge: str
    depth: int
    parent_path: str
    node_id: str
    edge_id: str
    outcome: str = "in_progress"
    error: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SubgraphHookEmitter(Protocol):
    """Passive seam the interpreter calls when crossing a subgraph boundary.

    Implementations MUST NOT raise into the interpreter; observation failures
    must be contained at the boundary (C7 control/observation separation).
    """

    def emit(self, ctx: SubgraphHookContext) -> None: ...


class NullSubgraphHookEmitter:
    """Default no-op emitter; keeps unit tests free of plugin-tree imports."""

    def emit(self, ctx: SubgraphHookContext) -> None:
        del ctx


__all__ = [
    "NullSubgraphHookEmitter",
    "SubgraphHookContext",
    "SubgraphHookEmitter",
    "SubgraphHookEvent",
]
