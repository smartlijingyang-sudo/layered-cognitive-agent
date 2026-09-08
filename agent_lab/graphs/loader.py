"""YAML -> InfoEdgeSpec loader.

Pure function. Reads a YAML file, returns a frozen InfoEdgeSpec.
All graph structure is data — this file contains zero business logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agent_lab.graph.spec import (
    ErrorRoute,
    InfoEdgeSpec,
    InfoGrant,
    InfoNode,
    NodeRegion,
    SubSpecLink,
)
from agent_lab.primitives.edge import Edge, EdgeKind
from agent_lab.primitives.port import PortRef

_CONFIG_DIR = Path(__file__).parent / "configs"


def _to_region(value: str) -> NodeRegion:
    """YAML uses strings like 'phase:think' or bare 'model_visible'."""
    if value.startswith("phase:"):
        return NodeRegion.PHASE
    mapping = {r.value: r for r in NodeRegion}
    return mapping.get(value, NodeRegion.DIGEST)


def _to_edge_kind(value: str) -> EdgeKind:
    mapping = {e.value: e for e in EdgeKind}
    return mapping.get(value, EdgeKind.DATA)


def _to_error_route(value: str) -> ErrorRoute:
    mapping = {e.value: e for e in ErrorRoute}
    return mapping.get(value, ErrorRoute.FAIL)


def _parse_node(raw: dict[str, Any]) -> InfoNode:
    return InfoNode(
        id=raw["id"],
        region=_to_region(raw.get("region", "digest")),
        factory=raw.get("factory", "identity"),
        config=raw.get("config", {}) or {},
        ins=list(raw.get("ins", []) or []),
        outs=list(raw.get("outs", []) or []),
        on_error=_to_error_route(raw.get("on_error", "fail")),
        route_to=raw.get("route_to"),
        parallelism=int(raw.get("parallelism", 1) or 1),
    )


def _parse_edge(raw: dict[str, Any]) -> Edge:
    return Edge(
        id=raw["id"],
        from_ref=PortRef(
            spec_id=raw["from"]["spec"],
            node_id=raw["from"]["node"],
            port_id=raw["from"]["port"],
        ),
        to_ref=PortRef(
            spec_id=raw["to"]["spec"],
            node_id=raw["to"]["node"],
            port_id=raw["to"]["port"],
        ),
        kind=_to_edge_kind(raw.get("kind", "data")),
        required=bool(raw.get("required", True)),
    )


def _parse_sub_spec(raw: dict[str, Any]) -> SubSpecLink:
    return SubSpecLink(
        node_id=raw["node"],
        sub_spec_id=raw["sub_spec"],
        input_map=dict(raw.get("input_map", {}) or {}),
        output_map=dict(raw.get("output_map", {}) or {}),
    )


def _parse_grant(raw: dict[str, Any]) -> InfoGrant:
    return InfoGrant(
        id=raw["id"],
        from_spec=raw["from_spec"],
        to_spec=raw["to_spec"],
        ports=list(raw.get("ports", []) or []),
        mode=raw.get("mode", "read"),
        max_bytes=int(raw.get("max_bytes", 0) or 0),
        redact=list(raw.get("redact", []) or []),
    )


def load_spec(path: str | Path) -> InfoEdgeSpec:
    """Read a YAML graph and return an InfoEdgeSpec. Pure data in/out."""
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return InfoEdgeSpec(
        id=raw["id"],
        version=str(raw.get("version", "0.1.0")),
        region=_to_region(raw.get("region", "digest")),
        description=str(raw.get("description", "")),
        nodes=[_parse_node(n) for n in raw.get("nodes", []) or []],
        edges=[_parse_edge(e) for e in raw.get("edges", []) or []],
        grants=[_parse_grant(g) for g in raw.get("grants", []) or []],
        sub_specs=[_parse_sub_spec(s) for s in raw.get("sub_specs", []) or []],
        discard_sink=raw.get("discard_sink"),
        mv_feed=raw.get("mv_feed"),
    )


def load_registry(*ids: str) -> dict[str, InfoEdgeSpec]:
    """Load a set of named graphs from configs/. ids are file stems.

    Example: load_registry("agent_loop", "mv_assemble", "effect_dispatch")
    """
    out: dict[str, InfoEdgeSpec] = {}
    for stem in ids:
        spec = load_spec(_CONFIG_DIR / f"{stem}.yaml")
        out[spec.id] = spec
    return out
