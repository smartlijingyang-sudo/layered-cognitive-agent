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

from collections.abc import Callable, Mapping
from dataclasses import dataclass
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


def payload_of(event: GraphObservation) -> dict[str, Any]:
    """Serialize one :class:`GraphObservation` for spine.

    Every field is included. No filtering: empty strings and zero
    integers are part of the contract so debug readers can
    distinguish "start" from "end" without a separate marker.
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
        "inputs": dict(event.inputs),
        "outputs": dict(event.outputs),
        "metadata": dict(event.metadata),
    }


def inputs_of(port_values: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Convert a port-value mapping into the frozen carrier form."""
    return tuple(port_values.items())


def metadata_of(
    *,
    binding: BindingKind | str | None = None,
    purpose: str = "",
    region: str = "",
    max_visits: int = 1,
    subgraph_plan_ref: str = "",
    extras: tuple[tuple[str, Any], ...] = (),
) -> tuple[tuple[str, Any], ...]:
    """Build a metadata tuple from the fields a kernel call site knows."""
    binding_str = BindingKindField.of(binding)
    pairs: list[tuple[str, Any]] = [
        ("binding", binding_str),
        ("purpose", purpose),
        ("region", region),
        ("max_visits", int(max_visits)),
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
