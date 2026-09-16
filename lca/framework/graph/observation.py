"""Graph observation — the typed seam between kernel and observability.

The kernel owns graph execution truth (visit order, edge selection,
subgraph recursion). Observability owns the spine. This module is
the typed carrier between them: the kernel builds a
:class:`GraphObservation` per lifecycle event and hands it to the
configured :class:`GraphObserver`. The observer is the only place
that knows about EP names.

Why a frozen dataclass instead of a dict:
- ``slots=True`` keeps memory bounded for long plans.
- ``frozen=True`` lets the carrier flow through multi-threaded
  observers (e.g. async tasks writing to spine) without defensive
  copies.
- Every field has a default so callers fill only what they have; the
  full payload is assembled in :func:`payload_of` for spine.

Why inputs/outputs/metadata are tuples of pairs:
- ``frozen=True`` forbids ``dict`` (mutable); tuples are frozen.
- Order is preserved so debug tools can show the same sequence the
  producer declared.
- A tuple of pairs is JSON-roundtrippable as ``dict(pair)`` without
  dropping iteration order.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from lca.contracts.protocols.graph.binding import BindingKind

KIND_VISIT_START = "visit_start"
KIND_VISIT_END = "visit_end"
KIND_EDGE = "edge"
KIND_SUBGRAPH_ENTER = "subgraph_enter"
KIND_SUBGRAPH_EXIT = "subgraph_exit"


@dataclass(frozen=True, slots=True)
class GraphObservation:
    """One graph lifecycle event. Carries every field the kernel can read.

    The ``kind`` field selects which EP the observer resolves to;
    the kernel never references EP names. Empty strings / zero
    integers are deliberate — they signal "this lifecycle stage did
    not fill this slot" rather than "this slot is unknown".
    """

    kind: str
    plan_ref: str
    occurred_at_ms: int
    node_id: str = ""
    node_index: int = 0
    depth: int = 0
    binding: str = ""
    edge_id: str = ""
    from_node: str = ""
    to_node: str = ""
    dispatch: str = ""
    outcome: str = ""
    error: str = ""
    elapsed_ms: int = 0
    # Phase is the canonical LCA lifecycle stage that owns the
    # node (``perceive`` / ``think`` / ``act`` / ``reflect`` /
    # ``remember`` / ``stop``). Producers derive it from the
    # node_id naming convention (``<phase>.<subnode>``) so the
    # kernel does not need a separate ``PlanNode.phase`` field —
    # the graph names itself. Empty string means "phase unknown".
    phase: str = ""
    inputs: tuple[tuple[str, Any], ...] = ()
    outputs: tuple[tuple[str, Any], ...] = ()
    metadata: tuple[tuple[str, Any], ...] = ()


@runtime_checkable
class GraphObserver(Protocol):
    """The only seam the kernel calls. Knows nothing about EP names."""

    def observe(self, event: GraphObservation) -> None: ...


class NullGraphObserver:
    """Default observer for unit tests and pre-boot paths."""

    def observe(self, event: GraphObservation) -> None:
        del event


EmitFn = Callable[[str, dict[str, Any]], None]
"""Write one EP + payload to the observability backend.

The observer does not import spine directly; the wiring layer
injects this seam so unit tests can pass a recording callable
without standing up an EventSpine.
"""


@dataclass(frozen=True, slots=True)
class BindingKindField:
    """Helper: coerce a BindingKind enum or string into a stable string."""

    value: str = ""

    @classmethod
    def of(cls, binding: BindingKind | str | None) -> str:
        if binding is None:
            return ""
        if isinstance(binding, BindingKind):
            return binding.value
        return str(binding)


def _json_safe(value: Any) -> Any:
    """Project one carried value into the lossless-JSON form the fact plane accepts.

    ``Session.append`` is the only journal write path and it refuses payloads it
    cannot round-trip, which drops the whole record. Port values are live kernel
    objects — per-turn ``ForkedTools`` holds ``Tool`` instances with bound
    closures — so anything without a JSON form degrades to its ``repr``: the
    value stays attributable instead of the terminal event vanishing.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _json_safe(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value


def payload_of(event: GraphObservation) -> dict[str, Any]:
    """Serialize one :class:`GraphObservation` for spine.

    Every field is included. No filtering: empty strings and zero
    integers are part of the contract so debug readers can
    distinguish "start" from "end" without a separate marker.
    Port values are projected by :func:`_json_safe` here, the single
    seam between kernel truth and the fact plane, so no call site can
    hand a live object to ``Session.append`` and lose the record.
    """
    return {
        "kind": event.kind,
        "plan_ref": event.plan_ref,
        "occurred_at_ms": event.occurred_at_ms,
        "node_id": event.node_id,
        "node_index": event.node_index,
        "depth": event.depth,
        "binding": event.binding,
        "edge_id": event.edge_id,
        "from_node": event.from_node,
        "to_node": event.to_node,
        "dispatch": event.dispatch,
        "outcome": event.outcome,
        "error": event.error,
        "elapsed_ms": event.elapsed_ms,
        "phase": event.phase,
        "inputs": {str(k): _json_safe(v) for k, v in event.inputs},
        "outputs": {str(k): _json_safe(v) for k, v in event.outputs},
        "metadata": {str(k): _json_safe(v) for k, v in event.metadata},
    }


def inputs_of(port_values: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Convert a port-value mapping into the frozen carrier form."""
    return tuple(port_values.items())


# LCA 顶层 phase 闭集（ADR-0161 六语义 + terminal commit）。
# 命名约定：``<phase>.<subnode>``；phase_of 第一段必须落在本集合，
# 否则按 :data:`_PHASE_ALIAS_OF` 表归类到正确顶层。
LCA_TOP_PHASES: frozenset[str] = frozenset(
    {"perceive", "think", "act", "reflect", "remember", "stop", "terminal"}
)

# 节点命名缺顶层 phase 前缀时的归类映射 —— 收敛在此,不再散布到 caller。
# 每条注释说明来源(哪个 plan / spec / factory)。
_PHASE_ALIAS_OF: dict[str, str] = {
    # 历史 fold EP 用了 ``phase.<top>.<stage>`` 双前缀(应该是 ``<top>.phase.fold``);
    # alias 集中归到 top phase,顶层 phase 才是 LCA 六语义之一。
    "phase": "perceive",  # phase.perceive.observe / phase.think.fold / 等
    # think subgraph 节点命名缺 ``think.`` 前缀 —— 全部归到 think。
    "tool": "think",       # tool.fork.dispatch  ── think.tool.fork_dispatch(计划中改名)
    "history": "think",    # history.derive      ── think.history.assemble subgraph
    "llm": "think",        # llm.call            ── think.llm.dispatch subgraph
    "decision": "think",   # decision.parse / decision.repair ── think.decision.*
    "gate": "think",       # gate.chain.run / gate.chain.reject ── think.gate subgraph
    # act subgraph 节点命名缺 ``act.`` 前缀。
    "effect": "act",       # effect.execute      ── act.effect.execute
}


def phase_of(node_id: str) -> str:
    """Derive the LCA lifecycle phase from a node_id.

    Canonical naming is ``<phase>.<subnode>`` (e.g. ``think.main``,
    ``perceive.observe``, ``terminal.commit``). The graph framework
    does not own phase semantics — it only derives them from the
    convention — so the kernel never stores phase as a separate
    field on PlanNode.

    Convention violations (legacy ``phase.<>.<>`` fold EPs, or
    subnodes that dropped their top-level prefix) are mapped to the
    correct LCA top phase via :data:`_PHASE_ALIAS_OF`. This keeps
    downstream consumers (observers, NodeEnter/Exit facts) on the
    canonical six-phase vocabulary regardless of historical naming
    drift; renaming the plan YAML is a separate cleanup.
    Returns ``""`` when node_id is empty or the first segment is
    not a recognised top phase or alias.
    """
    if not node_id:
        return ""
    head = node_id.split(".", 1)[0]
    if head in LCA_TOP_PHASES:
        return head
    return _PHASE_ALIAS_OF.get(head, "")


def metadata_of(
    *,
    binding: BindingKind | str | None = None,
    purpose: str = "",
    region: str = "",
    subgraph_plan_ref: str = "",
    extras: tuple[tuple[str, Any], ...] = (),
) -> tuple[tuple[str, Any], ...]:
    """Build a metadata tuple from the fields a kernel call site knows.

    ADR-0225: ``max_visits`` parameter removed. The per-node visit
    ceiling is gone; ``metadata_of`` no longer carries a ``max_visits``
    pair. Resume replays still surface the per-node visit count via
    the ``GraphObservation.node_index`` field (set by ``_visit_start_of``).
    """
    binding_str = BindingKindField.of(binding)
    pairs: list[tuple[str, Any]] = [
        ("binding", binding_str),
        ("purpose", purpose),
        ("region", region),
        ("subgraph_plan_ref", subgraph_plan_ref),
    ]
    pairs.extend(extras)
    return tuple(pairs)


__all__ = [
    "KIND_EDGE",
    "KIND_SUBGRAPH_ENTER",
    "KIND_SUBGRAPH_EXIT",
    "KIND_VISIT_END",
    "KIND_VISIT_START",
    "EmitFn",
    "GraphObservation",
    "GraphObserver",
    "NullGraphObserver",
    "inputs_of",
    "metadata_of",
    "payload_of",
]
