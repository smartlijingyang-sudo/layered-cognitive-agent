"""Compile InfoEdgeSpec -> CompiledGraphBundle.

Skeleton only: resolve plugins, fan before_compile, validate structure,
build bindings + topological layers. No business wiring.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent_lab.graph.spec import InfoEdgeSpec
from agent_lab.graph.validate import ValidationError, validate

_log = logging.getLogger(__name__)


def _resolve_plugins(spec: InfoEdgeSpec) -> list:
    """Materialise every PluginRef in ``spec.plugins`` into a live plugin."""
    from agent_lab.plugins import resolve_plugin
    from agent_lab.plugins.base import GraphPlugin

    plugins: list[GraphPlugin] = []
    for ref in spec.plugins:
        inst = resolve_plugin(ref)
        if inst is not None:
            plugins.append(inst)
    return plugins


def _stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


class CompiledGraphBundle(BaseModel):
    """Immutable execution plan. Recompile when plan_hash changes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_id: str
    plan_hash: str
    spec_dump: dict[str, Any]
    bindings: list[dict[str, Any]] = Field(default_factory=list)
    layers: list[list[str]] = Field(default_factory=list)  # topological schedule
    subgraph_calls: list[dict[str, Any]] = Field(default_factory=list)
    # Materialised plugin instances — the runner reads this and fans out
    # events. Empty list when the spec declares no plugins.
    plugin_instances: list[Any] = Field(default_factory=list)


def compile(
    spec: InfoEdgeSpec,
    sub_registry: dict[str, InfoEdgeSpec] | None = None,
) -> CompiledGraphBundle:
    """Validate, build bindings, topological layers, return frozen bundle.

    Plugins may rewrite ``spec`` and mutate ``sub_registry`` in place via
    ``before_compile``. The rewritten spec is what ``spec_dump`` /
    ``subgraph_calls`` reflect; callers that execute should rebuild the
    spec from ``spec_dump`` (see ``runtime.runner.run``).

    Raises ValidationError on invariant violations.
    """
    if sub_registry is None:
        sub_registry = {}

    plugins = _resolve_plugins(spec)
    # Pass the live sub_registry: plugins (e.g. control_slots) may mutate it
    # in place so the runner can resolve inserted sub_spec ids.
    for plugin in plugins:
        try:
            rewritten = plugin.before_compile(spec, sub_registry)
            if rewritten is not None:
                spec = rewritten
        except Exception as exc:  # pragma: no cover
            _log.warning("plugin %s before_compile raised: %s", plugin.name, exc)

    errs = validate(spec)
    if errs:
        raise ValidationError(errs)

    bindings: list[dict[str, Any]] = []
    for e in spec.edges:
        bindings.append(
            {
                "edge_id": e.id,
                "from": e.from_ref.label(),
                "to": e.to_ref.label(),
                "kind": e.kind.value,
                "required": e.required,
            }
        )

    # Topological schedule: BFS over data edges only.
    in_deg: dict[str, int] = {n.id: 0 for n in spec.nodes}
    adj: dict[str, list[str]] = {n.id: [] for n in spec.nodes}
    for e in spec.edges:
        if e.kind.value in ("data", "project"):
            if e.from_ref.node_id == "_initial":
                continue
            if e.from_ref.spec_id != spec.id or e.to_ref.spec_id != spec.id:
                continue
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
        layers.append(sorted(nid for nid, d in remaining.items() if d > 0))

    subgraph_calls = [
        {
            "node_id": link.node_id,
            "sub_spec_id": link.sub_spec_id,
            "input_map": link.input_map,
            "output_map": link.output_map,
        }
        for link in spec.sub_specs
    ]

    spec_dump = spec.model_dump(mode="json")
    plan_hash = _stable_hash(
        {
            "spec_id": spec.id,
            "version": spec.version,
            "nodes": [n.model_dump() for n in spec.nodes],
            "edges": [e.model_dump() for e in spec.edges],
            "sub_specs": [s.model_dump() for s in spec.sub_specs],
            "grants": [g.model_dump() for g in spec.grants],
        }
    )

    return CompiledGraphBundle(
        spec_id=spec.id,
        plan_hash=plan_hash,
        spec_dump=spec_dump,
        bindings=bindings,
        layers=layers,
        subgraph_calls=subgraph_calls,
        plugin_instances=list(plugins),
    )
