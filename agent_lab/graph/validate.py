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


def _check_emits_against_edges(spec: InfoEdgeSpec) -> list[str]:
    """C2/C11: each effect edge source should declare an emit.

    Surfaces a non-fatal-style error if the node forgot to declare what
    it emits. Compile-time fails to find these means runtime has no
    permission / capability basis.
    """
    errs: list[str] = []
    for e in spec.edges:
        if e.kind.value != "effect":
            continue
        try:
            src_node = spec.node(e.from_ref.node_id)
        except KeyError:
            continue
        from agent_lab.nodes.base import NodeRegistry

        try:
            manifest = NodeRegistry.describe(src_node.factory)
        except KeyError:
            continue
        if not manifest.emits:
            errs.append(
                f"C2: effect edge {e.id} originates from {src_node.id} "
                f"({src_node.factory}) which declares no emits"
            )
    return errs


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
            if nk not in declared and ref_key.node_id in node_ids and not cross_spec:
                errs.append(f"C6: edge {e.id} {ref_label} port {ref_key.label()} is not declared")
            elif ref_key.node_id not in node_ids and not (
                cross_spec and e.kind == EdgeKind.PROJECT
            ):
                errs.append(
                    f"C6: edge {e.id} {ref_label} references missing node {ref_key.node_id}"
                )
            elif cross_spec and e.kind != EdgeKind.PROJECT:
                errs.append(
                    f"C1: edge {e.id} {ref_label} crosses spec boundary but is not a project edge"
                )
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

    # C6.1: on_error=route must target an existing node with an IN port
    # that can receive an EXCEPTION artifact (ADR-0206 §5.6).
    for n in spec.nodes:
        if n.on_error.value != "route":
            continue
        if not n.route_to:
            errs.append(f"C6.1: node {n.id} has on_error=route but route_to is unset")
            continue
        try:
            target = spec.node(n.route_to)
        except KeyError:
            errs.append(f"C6.1: node {n.id} on_error=route references missing node {n.route_to}")
            continue
        if not target.ins:
            errs.append(
                f"C6.1: node {n.id} on_error=route targets {n.route_to} "
                f"which has no IN port to receive the EXCEPTION artifact"
            )

    # C6.2: on_error=retry requires the node to declare max_retries (or
    # rely on the runtime default of 3). We allow implicit default; the
    # only static constraint here is "on_error must be a known enum value"
    # which Pydantic already enforces via the InfoNode model.

    # Emit declarations must align with effect edges (C2/C11)
    errs.extend(_check_emits_against_edges(spec))

    # C15: data/project edge wiring must respect the port kinds declared
    # by the source/target node manifests. We only check when BOTH ends
    # actually declared the corresponding PortInfo; missing manifests are
    # silently skipped so legacy specs without manifest annotations don't
    # regress.
    errs.extend(_check_port_kind_compatibility(spec))

    return errs


def _port_infos_by_factory() -> dict[str, dict[str, dict[str, str]]]:
    """{factory_name: {port_id: {"dir": "in"|"out", "kind": "<PortKind>", "schema_ref": "..."}}}.

    Imported lazily because agent_lab.nodes pulls in adapters.
    """
    try:
        from agent_lab.nodes.base import NodeRegistry
    except Exception:  # pragma: no cover - adapter import failures
        return {}
    out: dict[str, dict[str, dict[str, str]]] = {}
    for factory in NodeRegistry.known():
        try:
            manifest = NodeRegistry.describe(factory)
        except KeyError:
            continue
        ports: dict[str, dict[str, str]] = {}
        for p in manifest.inputs:
            ports[p.id] = {"dir": "in", "kind": p.kind.value, "schema_ref": p.schema_ref}
        for p in manifest.outputs:
            ports[p.id] = {"dir": "out", "kind": p.kind.value, "schema_ref": p.schema_ref}
        out[factory] = ports
    return out


# Conservative compatibility: artifact.kind (ArtifactKind) drives the
# source side; the target side's declared PortKind is what the node expects.
# We accept any source kind the target allows. Specific mappings:
_ALLOWED_SOURCES_FOR_TARGET: dict[str, frozenset[str]] = {
    "text": frozenset({"text"}),
    "message": frozenset({"message", "text"}),
    "manifest": frozenset({"manifest", "text"}),
    "intent": frozenset({"intent", "artifact", "text"}),
    "receipt": frozenset({"receipt", "artifact", "text"}),
    "fact": frozenset({"fact", "artifact", "text"}),
    "digest": frozenset({"digest", "artifact", "text"}),
    "verdict": frozenset({"verdict", "artifact", "text"}),
    # artifact = generic; accepts everything including itself
    "artifact": frozenset(
        {"artifact", "text", "message", "manifest", "intent", "receipt", "fact", "digest", "verdict"}
    ),
}


def _check_port_kind_compatibility(spec: InfoEdgeSpec) -> list[str]:
    """C15: edge wiring must respect source/target port kind declarations.

    Walks every data/project edge. For each, looks up the source node's
    declared OUT port kind and the target node's declared IN port kind
    via the NodeRegistry's PortInfo. Both ends must be declared; if
    either is absent, the check is skipped (manifest is optional).
    """
    port_infos = _port_infos_by_factory()
    errs: list[str] = []
    for e in spec.edges:
        if e.kind.value not in ("data", "project"):
            continue
        if e.from_ref.node_id == "_initial":
            continue  # external input — caller supplies the artifact
        if e.from_ref.spec_id != spec.id or e.to_ref.spec_id != spec.id:
            continue  # cross-spec wiring checked separately
        try:
            src_node = spec.node(e.from_ref.node_id)
            dst_node = spec.node(e.to_ref.node_id)
        except KeyError:
            continue
        src_info = port_infos.get(src_node.factory, {}).get(e.from_ref.port_id)
        dst_info = port_infos.get(dst_node.factory, {}).get(e.to_ref.port_id)
        if src_info is None or dst_info is None:
            continue  # one or both ends didn't declare — skip
        if src_info["dir"] != "out" or dst_info["dir"] != "in":
            continue  # port dir sanity is already C6
        # We know src_info["kind"] is a NodeLayer PortKind string. The
        # runtime Artifact.kind lives in ArtifactKind. The PortKind enum
        # already mirrors ArtifactKind 1:1 except "artifact" is a generic
        # catch-all. So we accept direct equality + the artifact fallback.
        allowed = _ALLOWED_SOURCES_FOR_TARGET.get(dst_info["kind"])
        if allowed is None:
            continue  # unknown target kind — don't reject
        if src_info["kind"] not in allowed:
            errs.append(
                f"C15: edge {e.id} wires {src_node.factory}.{e.from_ref.port_id} "
                f"(kind={src_info['kind']}) -> {dst_node.factory}.{e.to_ref.port_id} "
                f"(expected kind={dst_info['kind']})"
            )
    return errs


def validate_or_raise(
    spec: InfoEdgeSpec, registry: dict[str, dict[str, str]] | None = None
) -> None:
    errs = validate(spec, registry)
    if errs:
        raise ValidationError(errs)


# ---------------------------------------------------------------------------
# ADR-0210 §3 — C14 region validation (reads profile.regions_declare)
# ---------------------------------------------------------------------------

def _check_regions(
    spec: InfoEdgeSpec,
    profile_regions: "set[str] | None" = None,
) -> list[str]:
    """C14 region label validation (ADR-0210 §3 P7-I-1 / P7-I-4).

    The spec-level region label (region.value + phase) must be in the
    closed set:
      - 6-stage recommended: phase:{perceive,think,act,reflect,remember,stop}
      - bare enum: model_visible, effect, lineage, digest, control
      - profile.regions.declare (custom set, optional)

    Sub-specs (InfoEdgeSpec.sub_specs) get validated independently by
    the GenericPlanInterpreter's recursive walk (per ADR-0206 §5.2).

    Unbound region = compile error (matches C14 fail-loud behaviour).
    region labels are NOT a capability gate (P7-I-2).
    """
    # Imported here to avoid a circular import at module load.
    from agent_lab.profile_loader import build_region_closed_set

    closed = build_region_closed_set(profile_regions)
    errs: list[str] = []

    # Spec-level region label
    region_enum = spec.region.value if hasattr(spec.region, "value") else str(spec.region)
    phase_name = getattr(spec, "phase", "") or ""
    if region_enum == "phase":
        spec_label = f"phase:{phase_name}" if phase_name else "phase:<unnamed>"
    else:
        spec_label = region_enum

    if spec_label not in closed:
        errs.append(
            f"C14: spec {spec.id!r} region {spec_label!r} not in closed set "
            f"(builtin 6-stage + bare enum + profile.regions.declare)"
        )

    return errs


def validate_with_profile(
    spec: InfoEdgeSpec,
    profile_regions: "set[str] | None" = None,
    registry: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """Validate with an optional profile regions overlay.

    Combines the standard validate() (C1-C13) with the C14 region check.
    Pass profile_regions=None to use only the 6-stage + bare-enum closed set.
    """
    errs = validate(spec, registry)
    errs.extend(_check_regions(spec, profile_regions))
    return errs


def validate_with_profile_or_raise(
    spec: InfoEdgeSpec,
    profile_regions: "set[str] | None" = None,
    registry: dict[str, dict[str, str]] | None = None,
) -> None:
    """Raise ValidationError if validate_with_profile finds any errors."""
    errs = validate_with_profile(spec, profile_regions, registry)
    if errs:
        raise ValidationError(errs)


# ---------------------------------------------------------------------------
# ADR-0210 §6.3 — recursive region validation (per nested sub_spec)
# ---------------------------------------------------------------------------

def validate_subgraph_with_profile(
    root: "InfoEdgeSpec",
    profile_regions: "set[str] | None" = None,
    registry: "dict[str, InfoEdgeSpec] | None" = None,
) -> list[str]:
    """C14 region validation over the entire nested sub_spec graph.

    Per ADR-0210 §3 P7-I-4 + §5.2: region tags are part of the
    GenericPlanInterpreter's recursive walk. Each nested sub_spec's
    region label is independently validated against the profile's
    regions.declare set + the 6-stage recommended set.

    The walker is depth-first iterative (see agent_lab.graph.spec.walk_sub_specs);
    a sub_spec whose id is not in ``registry`` is skipped (the
    C6 port check during the parent's compile() would have caught it).

    Returns a list of "C14: spec <id> region <label> not in closed set"
    error strings (one per offending sub_spec). The root spec is also
    validated.
    """
    from agent_lab.graph.spec import current_region_label, walk_sub_specs

    all_specs = walk_sub_specs(root)
    if not all_specs:
        # Empty graph (no nodes) — nothing to validate.
        return []
    errs: list[str] = []
    for spec in all_specs:
        label = current_region_label(spec)
        errs.extend(_check_regions(spec, profile_regions))
        # Defensive: empty region label → flag
        if label == "phase:<unnamed>":
            errs.append(
                f"C14: spec {spec.id!r} has region=PHASE but no phase name "
                f"(set region: phase:<name> in YAML or spec.phase = '<name>')"
            )
    return errs


def validate_subgraph_with_profile_or_raise(
    root: "InfoEdgeSpec",
    profile_regions: "set[str] | None" = None,
    registry: "dict[str, InfoEdgeSpec] | None" = None,
) -> None:
    """Raise ValidationError if any spec in the sub_spec graph fails C14."""
    errs = validate_subgraph_with_profile(root, profile_regions, registry)
    if errs:
        raise ValidationError(errs)
