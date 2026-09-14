"""Graph timeline — one canonical text rendering of a ``phase_graph.*`` record.

The graph kernel durable-records every node visit through
:class:`lca.framework.graph.observation.GraphObservation`, and ``payload_of``
writes every field. Three separate readers used to decode that payload each on
their own: ``observation trace-show``, ``journal trace`` and ``observation
run-replay``. Two of them still read a retired contract (``input_params``,
``output_schema``, ``error_type``, ``return_value_fingerprint``,
``exception_message``), none of which the kernel writes any more, so they
silently rendered nothing for a real node visit.

This module owns the payload-to-line rule for all of them, plus the live
console carrier. A record renders identically whether it came off the append
stream or from disk, which is what makes the two interchangeable in a debug
session.

Line shape is deliberately grep-safe: one logical event is one physical line,
no leading whitespace, no glyphs, ASCII status words, and ``depth`` is an
explicit field rather than indentation. ``in=``/``out=`` carry port *names*
only — port values stay in ``--json``, following the industry default of not
putting message bodies on the log line.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.infrastructure.observability.adapters.policy import sanitize

GRAPH_EP_PREFIX = "phase_graph."

EP_NODE_START = "phase_graph.node.start"
EP_NODE_END = "phase_graph.node.end"
EP_EDGE_TRANSIT = "phase_graph.edge.transit"
EP_SUBGRAPH_ENTER = "phase_graph.subgraph.enter"
EP_SUBGRAPH_EXIT = "phase_graph.subgraph.exit"

GRAPH_EPS = (EP_NODE_START, EP_NODE_END, EP_EDGE_TRANSIT, EP_SUBGRAPH_ENTER, EP_SUBGRAPH_EXIT)

ERROR_FIELD_LIMIT = 120
"""Bound on the rendered error text.

Exception strings routinely embed the payload that provoked them, so the field
goes through :func:`sanitize` before it is shortened. Port values are never
rendered at all, which keeps the message-body question off this line entirely.
"""


def is_graph_event(execution_point: str) -> bool:
    """Whether an execution point is a graph lifecycle event this module renders."""
    return execution_point in GRAPH_EPS


def _port_names(carried: Any) -> str:
    """Port names of a payload's ``inputs``/``outputs`` mapping, or ``-`` when empty."""
    if isinstance(carried, Mapping):
        keys = list(carried)
    elif isinstance(carried, (list, tuple)):
        keys = [pair[0] for pair in carried if isinstance(pair, (list, tuple)) and pair]
    else:
        keys = []
    return ",".join(str(key) for key in keys) if keys else "-"


def _status(outcome: str) -> str:
    if not outcome:
        return "-"
    return "ok" if outcome == "success" else "FAIL"


def _one_line(text: str) -> str:
    """Flatten embedded newlines so one record stays one physical line."""
    return text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def _bounded(text: str) -> str:
    """Redact, flatten and length-bound a free-text field for the console line."""
    safe = _one_line(sanitize(text))
    if len(safe) <= ERROR_FIELD_LIMIT:
        return safe
    return f"{safe[:ERROR_FIELD_LIMIT]}…(+{len(safe) - ERROR_FIELD_LIMIT})"


def render_line(
    execution_point: str,
    payload: Mapping[str, Any],
    *,
    run_id: str = "",
    seq: int | str = "",
) -> str:
    """Render one graph lifecycle record as a single grep-safe line.

    ``run_id``/``seq`` are the join keys back to the durable spine record. The
    live carrier reads them off the :class:`EventRecord` it is handed; the
    post-hoc CLI reads them from ``event_id``, which the spine writes as
    ``<run_id>:<seq>``. Both therefore produce the same bytes for the same
    event, which is what lets a person and an agent quote one line to each
    other. Unknown execution points still get a line rather than being
    dropped, so a new kernel kind degrades to visible-but-plain.
    """
    node = _one_line(str(payload.get("node_id") or ""))
    plan_ref = str(payload.get("plan_ref") or "")
    depth = payload.get("depth", 0)
    parts = [execution_point]
    if run_id:
        parts.insert(0, f"run={run_id}")
    if seq != "":
        parts.insert(1 if run_id else 0, f"seq={seq}")

    if execution_point == EP_NODE_START:
        parts.append(f"node={node or '-'}")
        parts.append(f"binding={payload.get('binding') or '-'}")
        parts.append(f"visit={payload.get('node_index', 0)}")
        parts.append(f"depth={depth}")
        parts.append(f"plan={plan_ref or '-'}")
        subgraph = str((payload.get("metadata") or {}).get("subgraph_plan_ref") or "")
        if subgraph:
            parts.append(f"sub={subgraph}")
    elif execution_point == EP_NODE_END:
        parts.append(f"node={node or '-'}")
        parts.append(_status(str(payload.get("outcome") or "")))
        parts.append(f"{payload.get('elapsed_ms', 0)}ms")
        parts.append(f"depth={depth}")
        if payload.get("dispatch"):
            parts.append(f"dispatch={payload['dispatch']}")
        parts.append(f"in={_port_names(payload.get('inputs'))}")
        parts.append(f"out={_port_names(payload.get('outputs'))}")
        if payload.get("error"):
            parts.append(f"error={_bounded(str(payload['error']))}")
    elif execution_point == EP_EDGE_TRANSIT:
        parts.append(f"edge={payload.get('edge_id') or '-'}")
        parts.append(f"depth={depth}")
        when = str((payload.get("metadata") or {}).get("when") or "")
        parts.append(f"when={_one_line(when) if when else '-'}")
    elif execution_point in (EP_SUBGRAPH_ENTER, EP_SUBGRAPH_EXIT):
        meta = payload.get("metadata") or {}
        parts.append(f"node={node or '-'}")
        parts.append(f"sub={meta.get('subgraph_plan_ref') or '-'}")
        parts.append(f"depth={depth}")
        if execution_point == EP_SUBGRAPH_ENTER:
            parts.append(f"entry={meta.get('entry_node') or '-'}")
        else:
            parts.append(_status(str(payload.get("outcome") or "")))
            if payload.get("error"):
                parts.append(f"error={_bounded(str(payload['error']))}")

    return "  ".join(parts)


def render_record(record: Mapping[str, Any]) -> str:
    """Render one spine record, deriving the join keys from its ``event_id``."""
    payload = record.get("payload")
    run_id, seq = split_event_id(str(record.get("event_id") or ""))
    return render_line(
        str(record.get("execution_point") or ""),
        payload if isinstance(payload, Mapping) else {},
        run_id=run_id,
        seq=seq,
    )


def split_event_id(event_id: str) -> tuple[str, str]:
    """``<run_id>:<seq>`` as the spine writes it; empty pair when it has no separator.

    A record whose ``event_id`` does not carry the separator gets no join keys
    rather than a line claiming the whole id is its sequence.
    """
    run_id, sep, seq = event_id.rpartition(":")
    return (run_id, seq) if sep else ("", "")


__all__ = [
    "EP_EDGE_TRANSIT",
    "EP_NODE_END",
    "EP_NODE_START",
    "EP_SUBGRAPH_ENTER",
    "EP_SUBGRAPH_EXIT",
    "GRAPH_EPS",
    "GRAPH_EP_PREFIX",
    "is_graph_event",
    "render_line",
    "render_record",
    "split_event_id",
]
