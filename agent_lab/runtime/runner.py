"""Runner — recursive interpreter over CompiledGraphBundle.

Single source of execution truth. Same interpreter runs the root graph
and every nested sub-graph (ADR-0206 C11: one graph kind, one runner).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agent_lab.graph.compile import CompiledGraphBundle
from agent_lab.graph.spec import InfoEdgeSpec, SubSpecLink
from agent_lab.nodes import invoke as invoke_node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@dataclass
class TraceEvent:
    kind: str            # edge_fire | node_start | node_end | subgraph_enter | subgraph_exit
    subgraph_path: str
    node_id: str | None = None
    edge_id: str | None = None
    artifact_digest: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    ts_ms: float = 0.0


@dataclass
class ExecutionTrace:
    events: list[TraceEvent] = field(default_factory=list)
    final_artifacts: dict[str, Artifact] = field(default_factory=dict)

    def to_lines(self) -> list[dict[str, Any]]:
        return [
            {
                "kind": e.kind,
                "subgraph_path": e.subgraph_path,
                "node_id": e.node_id,
                "edge_id": e.edge_id,
                "artifact_digest": e.artifact_digest,
                "ts_ms": round(e.ts_ms, 3),
                **e.payload,
            }
            for e in self.events
        ]


class _Runner:
    def __init__(
        self,
        spec: InfoEdgeSpec,
        bundle: CompiledGraphBundle,
        initial: dict[str, Artifact],
        sub_registry: dict[str, InfoEdgeSpec],
        trace: ExecutionTrace,
        subgraph_path: str,
        runtime_registry: dict[str, type] | None = None,
    ):
        self.spec = spec
        self.bundle = bundle
        self.initial = dict(initial)
        self.sub_registry = sub_registry
        self.trace = trace
        self.subgraph_path = subgraph_path
        # Per-node artifact store keyed by (node_id, port_id)
        self.store: dict[tuple[str, str], Artifact] = {}

    def _emit(self, ev: TraceEvent) -> None:
        ev.ts_ms = time.time() * 1000.0
        self.trace.events.append(ev)

    def run(self) -> dict[str, Artifact]:
        # Seed: copy initial artifacts into per-node store for any node whose IN port
        # matches an initial key.
        for node in self.spec.nodes:
            for port_id in node.ins:
                if port_id in self.initial:
                    self.store[(node.id, port_id)] = self.initial[port_id]

        for layer in self.bundle.layers:
            for node_id in layer:
                self._run_node(node_id)

        # Collect final outputs: every node's OUT ports, last writer wins.
        finals: dict[str, Artifact] = {}
        for node in self.spec.nodes:
            for port_id in node.outs:
                key = (node.id, port_id)
                if key in self.store:
                    finals[port_id] = self.store[key]
        # Also include any initial artifacts that were never consumed.
        for k, v in self.initial.items():
            finals.setdefault(k, v)
        return finals

    def _run_node(self, node_id: str) -> None:
        node = self.spec.node(node_id)
        self._emit(TraceEvent(
            kind="node_start",
            subgraph_path=self.subgraph_path,
            node_id=node_id,
            payload={"factory": node.factory, "region": node.region.value},
        ))

        # Collect inputs: every IN port of this node. Missing port -> empty TEXT artifact.
        empty = Artifact(kind=ArtifactKind.TEXT, content="")
        inputs: dict[str, Artifact] = {
            port_id: self.store.get((node_id, port_id), empty)
            for port_id in node.ins
        }

        # Sub-spec link handling: enter nested sub-graph BEFORE invoking the
        # node factory. Stub identity nodes host a sub-spec call; their factory
        # runs after the subgraph has populated inputs via output_map.
        for link in self.spec.sub_specs:
            if link.node_id == node_id:
                self._run_subgraph(link, inputs)
                for port_id in node.ins:
                    if (node_id, port_id) in self.store:
                        inputs[port_id] = self.store[(node_id, port_id)]

        # Invoke the node factory.
        try:
            outputs = invoke_node(node, inputs)
        except Exception as exc:
            if node.on_error.value == "fail":
                self._emit(TraceEvent(
                    kind="node_end",
                    subgraph_path=self.subgraph_path,
                    node_id=node_id,
                    payload={"status": "error", "error": str(exc)},
                ))
                raise
            outputs = {}

        for port_id, artifact in outputs.items():
            self.store[(node_id, port_id)] = artifact

        # Propagate to downstream IN ports via data/project edges.
        for edge in self.spec.edges:
            if edge.from_ref.node_id != node_id:
                continue
            if edge.kind.value not in ("data", "project"):
                continue
            src_port = edge.from_ref.port_id
            dst_port = edge.to_ref.port_id
            src_a = self.store.get((node_id, src_port))
            if src_a is None:
                continue
            self.store[(edge.to_ref.node_id, dst_port)] = src_a
            self._emit(TraceEvent(
                kind="edge_fire",
                subgraph_path=self.subgraph_path,
                edge_id=edge.id,
                artifact_digest=src_a.short_id(),
                payload={"kind": edge.kind.value, "from": edge.from_ref.label(), "to": edge.to_ref.label()},
            ))

        self._emit(TraceEvent(
            kind="node_end",
            subgraph_path=self.subgraph_path,
            node_id=node_id,
            payload={"status": "ok"},
        ))

    def _run_subgraph(self, link: SubSpecLink, parent_inputs: dict[str, Artifact]) -> None:
        sub_spec = self.sub_registry.get(link.sub_spec_id)
        if sub_spec is None:
            raise KeyError(f"sub_spec not registered: {link.sub_spec_id}")
        sub_bundle = self._bundle_for(sub_spec)
        # Wire input_map: parent port -> sub_spec export port (we feed as initial)
        initial: dict[str, Artifact] = {}
        for parent_port, sub_port in link.input_map.items():
            src_a = parent_inputs.get(parent_port)
            if src_a is not None:
                initial[sub_port] = src_a
        self._emit(TraceEvent(
            kind="subgraph_enter",
            subgraph_path=self.subgraph_path,
            node_id=link.node_id,
            payload={"sub_spec_id": link.sub_spec_id, "subgraph_path_child": f"{self.subgraph_path}/{link.sub_spec_id}"},
        ))
        child = _Runner(
            spec=sub_spec,
            bundle=sub_bundle,
            initial=initial,
            sub_registry=self.sub_registry,
            trace=self.trace,
            subgraph_path=f"{self.subgraph_path}/{link.sub_spec_id}",
        )
        child_outputs = child.run()
        # Write child outputs back to parent node's IN ports (via output_map reverse).
        for sub_port, parent_port in link.output_map.items():
            if sub_port in child_outputs:
                self.store[(link.node_id, parent_port)] = child_outputs[sub_port]
        self._emit(TraceEvent(
            kind="subgraph_exit",
            subgraph_path=self.subgraph_path,
            node_id=link.node_id,
            payload={"sub_spec_id": link.sub_spec_id, "outputs": list(child_outputs.keys())},
        ))

    def _bundle_for(self, spec: InfoEdgeSpec) -> CompiledGraphBundle:
        # Reuse compile() if not cached — for simplicity always compile (this is a prototype).
        from agent_lab.graph.compile import compile as _compile
        return _compile(spec, self.sub_registry)


def run(
    spec: InfoEdgeSpec,
    initial: dict[str, Artifact] | None = None,
    sub_registry: dict[str, InfoEdgeSpec] | None = None,
) -> ExecutionTrace:
    """Compile + execute a root spec (with optional sub-spec registry).

    Returns an ExecutionTrace containing every node_start / node_end /
    edge_fire / subgraph_enter / subgraph_exit event plus final artifacts.
    """
    sub_registry = sub_registry or {}
    bundle = _compile_or_raise(spec, sub_registry)
    trace = ExecutionTrace()
    runner = _Runner(
        spec=spec,
        bundle=bundle,
        initial=initial or {},
        sub_registry=sub_registry,
        trace=trace,
        subgraph_path=spec.id,
    )
    trace.final_artifacts = runner.run()
    return trace


def _compile_or_raise(spec: InfoEdgeSpec, sub_registry: dict[str, InfoEdgeSpec]) -> CompiledGraphBundle:
    from agent_lab.graph.compile import compile as _compile
    bundle = _compile(spec, sub_registry)
    return bundle
