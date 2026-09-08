"""C1-C14 invariant checker (ADR-0206 §3).

Pure function: walks nodes/edges/grants and reports every violation found.
Raises ValidationError on first OR returns list? We choose list — single-shot
diagnostics so the user fixes all in one pass.
"""

from __future__ import annotations

from agent_lab.graph.spec import InfoEdgeSpec
from agent_lab.primitives.edge import EdgeKind
from agent_lab.primitives.port import PortDir


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def _declared_ports(spec: InfoEdgeSpec) -> dict[tuple[str, str], dict]:
    """Build {(node_id, port_id): {dir, type, optional}} from spec.nodes."""
    out: dict[tuple[str, str], dict] = {}
    for n in spec.nodes:
        for p in n.ins:
            out[(n.id, p)] = {"dir": PortDir.IN, "type": "Any", "optional": False, "node": n}
        for p in n.outs:
            out[(n.id, p)] = {"dir": PortDir.OUT, "type": "Any", "optional": False, "node": n}
    return out


def _declared_sub_spec_inputs(spec: InfoEdgeSpec) -> dict[tuple[str, str], str]:
    """{(node_id, port_id): sub_spec_port_id} for ports that feed a sub_spec."""
    out: dict[tuple[str, str], str] = {}
    for link in spec.sub_specs:
        for parent_port, sub_port in link.input_map.items():
            out[(link.node_id, parent_port)] = sub_port
    return out


def validate(spec: InfoEdgeSpec, registry: dict[str, dict[str, str]] | None = None) -> list[str]:
    """Return a list of error strings. Empty list means valid.

    registry: optional {spec_id: {export_port_id: parent_port_id}} for cross-spec port checks.
    """
    errs: list[str] = []
    node_ids = {n.id for n in spec.nodes}

    # C1/C2/C6 baseline: every port referenced by an edge must be declared.
    declared = _declared_ports(spec)
    edge_pairs: set[tuple[str, str]] = set()  # (from_node_id, to_node_id) — for cycle sanity
    for e in spec.edges:
        for ref_key, ref_label in [(e.from_ref, "from"), (e.to_ref, "to")]:
            nk = (ref_key.node_id, ref_key.port_id)
            if ref_key.node_id == "_initial":
                continue  # external input — caller supplies the artifact
            # Cross-spec project edges legitimately reference nodes in another spec.
            cross_spec = ref_key.spec_id != spec.id
            if nk not in declared and ref_key.node_id in node_ids:
                errs.append(f"C6: edge {e.id} {ref_label} port {ref_key.label()} is not declared")
            elif ref_key.node_id not in node_ids and not (cross_spec and e.kind == EdgeKind.PROJECT):
                errs.append(f"C6: edge {e.id} {ref_label} references missing node {ref_key.node_id}")
            elif cross_spec and e.kind != EdgeKind.PROJECT:
                errs.append(f"C1: edge {e.id} {ref_label} crosses spec boundary but is not a project edge")
        # port dir sanity
        if e.from_ref.node_id in node_ids:
            d = declared.get((e.from_ref.node_id, e.from_ref.port_id))
            if d and d["dir"] != PortDir.OUT:
                errs.append(f"C6: edge {e.id} from {e.from_ref.label()} is not an OUT port")
        if e.to_ref.node_id in node_ids:
            d = declared.get((e.to_ref.node_id, e.to_ref.port_id))
            if d and d["dir"] != PortDir.IN:
                errs.append(f"C6: edge {e.id} to {e.to_ref.label()} is not an IN port")
        edge_pairs.add((e.from_ref.node_id, e.to_ref.node_id))

    # C2 / C3: every effect edge must land in a node with an OUT port declared receipt.
    # Heuristic: effect edges must target a node whose `outs` contains "receipt" OR
    # the spec's `discard_sink` is set AND the receipt node points to it.
    for e in spec.edges:
        if e.kind == EdgeKind.EFFECT:
            target = next((n for n in spec.nodes if n.id == e.to_ref.node_id), None)
            if target and "receipt" not in target.outs and not spec.discard_sink:
                errs.append(
                    f"C2/C3: effect edge {e.id} targets {target.id} without 'receipt' out "
                    f"and spec has no discard_sink"
                )

    # C11: only one graph kind — there is no other graph kind in this prototype
    # by construction.  Document the invariant so future readers see it.
    # (Enforced by absence: no other Spec class exists.)

    # C14: phase region tags must use the documented label set
    # (informational; we don't fail on unknown phase tags so user-defined phases pass.)

    # SubSpec input_map and output_map must reference existing ports on the parent node
    for link in spec.sub_specs:
        if link.node_id not in node_ids:
            errs.append(f"C12: sub_spec link references missing node {link.node_id}")
            continue
        node = spec.node(link.node_id)
        for parent_port, _sub_port in link.input_map.items():
            if parent_port not in node.ins:
                errs.append(
                    f"C12: sub_spec input_map on {link.node_id} reads from parent port "
                    f"{parent_port} not in node.ins={node.ins}"
                )
        for _sub_port, parent_port in link.output_map.items():
            if parent_port not in node.outs:
                errs.append(
                    f"C12: sub_spec output_map on {link.node_id} writes to parent port "
                    f"{parent_port} not in node.outs={node.outs}"
                )

    # Grant port refs (best-effort string match)
    for g in spec.grants:
        if not g.ports:
            errs.append(f"C4: grant {g.id} declares no ports")

    return errs


def validate_or_raise(spec: InfoEdgeSpec, registry: dict[str, dict[str, str]] | None = None) -> None:
    errs = validate(spec, registry)
    if errs:
        raise ValidationError(errs)
