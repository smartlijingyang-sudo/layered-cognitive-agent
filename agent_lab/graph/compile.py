"""Compile InfoEdgeSpec -> CompiledGraphBundle.

Borrowed shape from lca_kernel/plan (plan_hash + bindings).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_lab.graph.spec import InfoEdgeSpec
from agent_lab.graph.validate import ValidationError, validate


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


class CompiledGraphBundle(BaseModel):
    """Immutable execution plan. Recompile when plan_hash changes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_id: str
    plan_hash: str
    spec_dump: dict[str, Any]
    bindings: list[dict[str, Any]] = Field(default_factory=list)
    layers: list[list[str]] = Field(default_factory=list)         # topological schedule
    effect_receipt_targets: dict[str, str] = Field(default_factory=dict)
    subgraph_calls: list[dict[str, Any]] = Field(default_factory=list)


def compile(
    spec: InfoEdgeSpec,
    sub_registry: dict[str, InfoEdgeSpec] | None = None,
) -> CompiledGraphBundle:
    """Validate, build bindings, topological layers, return frozen bundle.

    Raises ValidationError on invariant violations.
    """
    errs = validate(spec)
    if errs:
        raise ValidationError(errs)

    # Build bindings (edge -> dict). Each binding references its kind for runtime dispatch.
    bindings: list[dict[str, Any]] = []
    for e in spec.edges:
        bindings.append({
            "edge_id": e.id,
            "from": e.from_ref.label(),
            "to": e.to_ref.label(),
            "kind": e.kind.value,
            "required": e.required,
        })

    # Topological schedule: BFS over data edges only.
    in_deg: dict[str, int] = {n.id: 0 for n in spec.nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in spec.nodes}
    for e in spec.edges:
        if e.kind.value in ("data", "project"):  # only data flow contributes to schedule
            if e.from_ref.node_id == "_initial":
                continue  # external input doesn't count toward schedule
            if e.from_ref.spec_id != spec.id or e.to_ref.spec_id != spec.id:
                continue  # cross-spec project edges are dispatched at runtime, not locally
            if e.from_ref.node_id in adj and e.to_ref.node_id in adj:
                adj[e.from_ref.node_id].append(e.to_ref.node_id)
                in_deg[e.to_ref.node_id] = in_deg.get(e.to_ref.node_id, 0) + 1
    layers: list[list[str]] = []
    frontier = [nid for nid, d in in_deg.items() if d == 0]
    remaining = dict(in_deg)
    while frontier:
        layers.append(sorted(frontier))
        next_frontier: list[str] = []
        for nid in frontier:
            for tgt in adj.get(nid, []):
                remaining[tgt] -= 1
                if remaining[tgt] == 0:
                    next_frontier.append(tgt)
        frontier = next_frontier
    if sum(remaining.values()) > 0:
        # cycles among non-data edges are allowed (e.g. control). Surface a warning, not error.
        layers.append(sorted(nid for nid, d in remaining.items() if d > 0))

    # effect_receipt_targets: every effect edge -> target node id (for C2/C3 dispatch)
    effect_receipt_targets: dict[str, str] = {}
    for e in spec.edges:
        if e.kind.value == "effect":
            effect_receipt_targets[e.id] = e.to_ref.node_id

    # subgraph_calls: list of (node_id, sub_spec_id) — runtime resolves nested specs
    subgraph_calls = [
        {"node_id": link.node_id, "sub_spec_id": link.sub_spec_id,
         "input_map": link.input_map, "output_map": link.output_map}
        for link in spec.sub_specs
    ]

    spec_dump = spec.model_dump(mode="json")
    plan_hash = _stable_hash({
        "spec_id": spec.id,
        "version": spec.version,
        "nodes": [n.model_dump() for n in spec.nodes],
        "edges": [e.model_dump() for e in spec.edges],
        "sub_specs": [s.model_dump() for s in spec.sub_specs],
        "grants": [g.model_dump() for g in spec.grants],
    })

    return CompiledGraphBundle(
        spec_id=spec.id,
        plan_hash=plan_hash,
        spec_dump=spec_dump,
        bindings=bindings,
        layers=layers,
        effect_receipt_targets=effect_receipt_targets,
        subgraph_calls=subgraph_calls,
    )
