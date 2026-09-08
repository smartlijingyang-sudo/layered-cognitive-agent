"""Runner — recursive interpreter over CompiledGraphBundle.

Single source of execution truth. Same interpreter runs the root graph
and every nested sub-graph (ADR-0206 C11: one graph kind, one runner).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agent_lab.graph.compile import CompiledGraphBundle
from agent_lab.graph.spec import InfoEdgeSpec, InfoNode, SubSpecLink
from agent_lab.nodes import invoke as invoke_node
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_exception


@dataclass
class TraceEvent:
    kind: str  # edge_fire | node_start | node_end | subgraph_enter | subgraph_exit
    subgraph_path: str
    node_id: str | None = None
    edge_id: str | None = None
    artifact_digest: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    ts_ms: float = 0.0


class _NonRetryableError(Exception):
    """Marker: deterministic failure. on_error=retry will not retry past this.

    Nodes raise this to signal "I failed and retrying is pointless — propagate
    via on_error=fail or on_error=route." Per ADR-0206 §5.6, ValueError /
    TypeError / contract errors are deterministic; transient errors (Timeout,
    ConnectionError) are retryable by default.
    """


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
        inherited_plugins: list | None = None,
    ):
        self.spec = spec
        self.bundle = bundle
        self.initial = dict(initial)
        self.sub_registry = sub_registry
        self.trace = trace
        self.subgraph_path = subgraph_path
        # Per-node artifact store keyed by (node_id, port_id)
        self.store: dict[tuple[str, str], Artifact] = {}
        # Plugins inherited from the root runner. Sub-graph runners don't
        # re-compile plugins themselves — they receive the root's plugin
        # list so node-level events inside the sub-graph flow through the
        # same hooks the root declared.
        self._inherited_plugins: list = list(inherited_plugins or [])
        # Set of node ids already invoked (used by on_error=route to skip
        # a second visit when route_to lands in the same topological
        # layer as the failing node).
        self._executed: set[str] = set()

    def _plugins(self) -> list:
        """Return the live plugin instances for this runner.

        Sub-graph runners use the inherited plugin list (from the root);
        the root runner uses its own bundle's plugin_instances plus any
        plugins declared on the immediate spec.
        """
        if self._inherited_plugins:
            return list(self._inherited_plugins)
        from agent_lab.plugins.base import GraphPlugin

        bundle_plugins: list[GraphPlugin] = list(getattr(self.bundle, "plugin_instances", []) or [])
        own_plugins: list[GraphPlugin] = []
        try:
            from agent_lab.plugins import resolve_plugin as _resolve

            for ref in getattr(self.spec, "plugins", []) or []:
                inst = _resolve(ref)
                if inst is not None:
                    own_plugins.append(inst)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).debug("runner plugin discovery: %s", exc)
        return bundle_plugins + own_plugins

    def _emit(self, ev: TraceEvent) -> None:
        ev.ts_ms = time.time() * 1000.0
        self.trace.events.append(ev)
        # Fanout to plugins. Map TraceEvent.kind -> HookEvent + HookContext.
        from agent_lab.plugins import fanout_hooks
        from agent_lab.plugins.base import HookContext, HookEvent

        kind_to_event = {
            "node_start": HookEvent.NODE_START,
            "node_end": HookEvent.NODE_END,
            "edge_fire": HookEvent.EDGE_FIRE,
            "subgraph_enter": HookEvent.SUBGRAPH_ENTER,
            "subgraph_exit": HookEvent.SUBGRAPH_EXIT,
        }
        hook_event = kind_to_event.get(ev.kind)
        if hook_event is None:
            return
        ctx = HookContext(
            event=hook_event,
            spec_id=self.spec.id,
            subgraph_path=ev.subgraph_path,
            node_id=ev.node_id or "",
            edge_id=ev.edge_id or "",
            node_factory=(ev.payload or {}).get("factory", ""),
            edge_kind=(ev.payload or {}).get("kind", ""),
            artifact_digest=ev.artifact_digest or "",
            payload=dict(ev.payload or {}),
        )
        fanout_hooks(self._plugins(), hook_event, ctx)

    def _apply_output_hooks(
        self, node_id: str, outputs: dict[str, Artifact]
    ) -> dict[str, Artifact]:
        """Fan AFTER_NODE_EXECUTE so plugins may rewrite outputs.

        The skeleton does not interpret schema_ref or cognitive event
        names; a business plugin (e.g. semantic_router) owns that map.
        """
        from agent_lab.plugins import fanout_hooks
        from agent_lab.plugins.base import HookContext, HookEvent

        plugins = self._plugins()
        ctx = HookContext(
            event=HookEvent.AFTER_NODE_EXECUTE,
            spec_id=self.spec.id,
            subgraph_path=self.subgraph_path,
            node_id=node_id,
            payload={"outputs": dict(outputs), "plugins": plugins},
        )
        new_ctx = fanout_hooks(plugins, HookEvent.AFTER_NODE_EXECUTE, ctx)
        rewritten = new_ctx.payload.get("outputs", outputs)
        return rewritten if isinstance(rewritten, dict) else outputs

    def run(self) -> dict[str, Artifact]:
        # Seed: copy initial artifacts into per-node store for any node whose IN port
        # matches an initial key.
        for node in self.spec.nodes:
            for port_id in node.ins:
                if port_id in self.initial:
                    self.store[(node.id, port_id)] = self.initial[port_id]

        for layer in self.bundle.layers:
            for node_id in layer:
                if node_id in self._executed:
                    continue
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
        if node_id in self._executed:
            return
        self._executed.add(node_id)
        node = self.spec.node(node_id)
        self._emit(
            TraceEvent(
                kind="node_start",
                subgraph_path=self.subgraph_path,
                node_id=node_id,
                payload={"factory": node.factory, "region": node.region.value},
            )
        )

        # Collect inputs: every IN port of this node. Missing port -> empty TEXT artifact.
        empty = Artifact(kind=ArtifactKind.TEXT, content="")
        inputs: dict[str, Artifact] = {
            port_id: self.store.get((node_id, port_id), empty) for port_id in node.ins
        }

        # Sub-spec link handling: enter nested sub-graph BEFORE invoking the
        # node factory. Stub identity nodes host a sub-spec call; their factory
        # runs after the subgraph has populated inputs via output_map.
        for link in self.spec.sub_specs:
            if link.node_id == node_id:
                self._run_subgraph(link, inputs)
                # Later sub_specs on the same host (e.g. control slots) may
                # read OUT ports written by earlier ones — refresh the full
                # host store into the input map, not only declared IN ports.
                for (nid, port_id), art in list(self.store.items()):
                    if nid == node_id:
                        inputs[port_id] = art

        # Invoke the node factory and dispatch via on_error policy.
        # ADR-0206 §5.6: errors are routed edges, not try/catch. The runner
        # does not swallow exceptions; it hands each failure to one of three
        # handlers keyed by node.on_error.
        outputs, status, error_info = self._invoke_with_policy(node, inputs)

        output_rewrites: dict[str, str] = {}
        if status == "ok":
            before = {pid: art.short_id() for pid, art in outputs.items()}
            outputs = self._apply_output_hooks(node_id, outputs)
            for port_id, artifact in outputs.items():
                self.store[(node_id, port_id)] = artifact
                if before.get(port_id) != artifact.short_id():
                    output_rewrites[port_id] = artifact.short_id()
        elif status == "routed":
            # on_error=route: the route_to target's first IN port received the
            # exception artifact. Re-enter normal propagation from there.
            for port_id, artifact in outputs.items():
                self.store[(node_id, port_id)] = artifact
        # status == "failed" already raised; we never get here.

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
            self._emit(
                TraceEvent(
                    kind="edge_fire",
                    subgraph_path=self.subgraph_path,
                    edge_id=edge.id,
                    artifact_digest=src_a.short_id(),
                    payload={
                        "kind": edge.kind.value,
                        "from": edge.from_ref.label(),
                        "to": edge.to_ref.label(),
                    },
                )
            )

        node_end_payload: dict[str, Any] = {
            "status": "ok" if status == "ok" else status,
            **error_info,
        }
        if output_rewrites:
            node_end_payload["output_rewrites"] = output_rewrites
        self._emit(
            TraceEvent(
                kind="node_end",
                subgraph_path=self.subgraph_path,
                node_id=node_id,
                payload=node_end_payload,
            )
        )

    def _invoke_with_policy(
        self, node: InfoNode, inputs: dict[str, Artifact]
    ) -> tuple[dict[str, Artifact], str, dict[str, Any]]:
        """Invoke node factory with on_error policy.

        Returns (outputs, status, error_info):
          - status="ok"      — outputs hold the node's normal outputs
          - status="routed"  — outputs contain the route_to target's outputs;
                               the route target was invoked with the EXCEPTION
                               artifact on its first IN port
          - status="failed"  — unrecoverable; raises (never returns)

        on_error policy:
          - fail     — re-raise (deterministic default)
          - retry    — re-invoke up to config.max_retries (default 3);
                       transient failures get a backoff; deterministic
                       failures are NOT retried (per ADR-0206 §5.6)
          - route    — invoke the node referenced by route_to with the
                       EXCEPTION artifact; the route target's outputs are
                       forwarded as this node's outputs
        """
        error_info: dict[str, Any] = {}
        # on_error=route: handled by short-circuit before invocation, since
        # we want the route target (not this node) to be the one that runs.
        if node.on_error.value == "route":
            target_id = node.route_to
            if not target_id:
                raise RuntimeError(f"node {node.id}: on_error=route requires route_to to be set")
            try:
                target = self.spec.node(target_id)
            except KeyError as exc:
                raise RuntimeError(
                    f"node {node.id}: on_error=route targets missing node {target_id}"
                ) from exc
            if not target.ins:
                raise RuntimeError(
                    f"node {node.id}: route_to={target_id} has no IN port to receive"
                    " the EXCEPTION artifact"
                )
            exception_port = target.ins[0]
            exc_artifact = make_exception(
                error_class="node.skipped",
                message=f"upstream node {node.id} failed before invocation",
                node_id=node.id,
                transient=False,
            )
            # Eagerly invoke the route target. Reason: route_to may land
            # in the SAME topological layer as the failing node (no edge
            # connects them), and the layer loop iterates by sorted node
            # id — so we can't rely on order. Invoke it here, before
            # _run_node returns to the layer loop.
            self.store[(target_id, exception_port)] = exc_artifact
            target_inputs: dict[str, Artifact] = {
                port_id: self.store.get(
                    (target_id, port_id),
                    Artifact(kind=ArtifactKind.TEXT, content=""),
                )
                for port_id in target.ins
            }
            target_outputs = invoke_node(target, target_inputs)
            for port_id, artifact in target_outputs.items():
                self.store[(target_id, port_id)] = artifact
            self._executed.add(target_id)
            error_info["status"] = "routed"
            error_info["route_to"] = target_id
            return target_outputs, "routed", error_info

        # Retry / fail policies run the node itself.
        max_attempts = 1
        if node.on_error.value == "retry":
            max_attempts = max(1, int(node.config.get("max_retries", 3)))

        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                outputs = invoke_node(node, inputs)
                if attempt > 1:
                    error_info["retried_attempts"] = attempt - 1
                return outputs, "ok", error_info
            except Exception as exc:
                last_exc = exc
                # ADR-0206 §5.6: deterministic errors are never retried.
                # The caller signals determinism by raising a non-transient
                # exception; transient=True on the artifact (if it surfaces
                # as one) gates retry. We honour `transient` on EXCEPTION
                # artifacts; anything else is treated as deterministic.
                if isinstance(exc, _NonRetryableError):
                    break
                if attempt == max_attempts:
                    break
        if last_exc is None:
            # Unreachable: the loop either returned successfully above or
            # raised and recorded an exception in last_exc. Reaching here
            # means max_attempts was 0, which the constructor rejects.
            raise RuntimeError(f"node {node.id}: retry loop exited without exception")
        error_info["status"] = "error"
        error_info["error"] = str(last_exc)
        self._emit(
            TraceEvent(
                kind="node_end",
                subgraph_path=self.subgraph_path,
                node_id=node.id,
                payload={"status": "error", "error": str(last_exc)},
            )
        )
        raise last_exc

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
        self._emit(
            TraceEvent(
                kind="subgraph_enter",
                subgraph_path=self.subgraph_path,
                node_id=link.node_id,
                payload={
                    "sub_spec_id": link.sub_spec_id,
                    "subgraph_path_child": f"{self.subgraph_path}/{link.sub_spec_id}",
                },
            )
        )
        child = _Runner(
            spec=self._effective_spec(sub_spec, sub_bundle),
            bundle=sub_bundle,
            initial=initial,
            sub_registry=self.sub_registry,
            trace=self.trace,
            subgraph_path=f"{self.subgraph_path}/{link.sub_spec_id}",
            inherited_plugins=self._plugins(),
        )
        child_outputs = child.run()
        # Write child outputs back to parent node's IN ports (via output_map reverse).
        for sub_port, parent_port in link.output_map.items():
            if sub_port in child_outputs:
                self.store[(link.node_id, parent_port)] = child_outputs[sub_port]
        self._emit(
            TraceEvent(
                kind="subgraph_exit",
                subgraph_path=self.subgraph_path,
                node_id=link.node_id,
                payload={"sub_spec_id": link.sub_spec_id, "outputs": list(child_outputs.keys())},
            )
        )

    def _bundle_for(self, spec: InfoEdgeSpec) -> CompiledGraphBundle:
        from agent_lab.graph.compile import compile as _compile

        return _compile(spec, self.sub_registry)

    def _effective_spec(self, spec: InfoEdgeSpec, bundle: CompiledGraphBundle) -> InfoEdgeSpec:
        """Rebuild the post-before_compile spec from the bundle dump."""
        return InfoEdgeSpec.model_validate(bundle.spec_dump)


def run(
    spec: InfoEdgeSpec,
    initial: dict[str, Artifact] | None = None,
    sub_registry: dict[str, InfoEdgeSpec] | None = None,
) -> ExecutionTrace:
    """Compile + execute a root spec (with optional sub-spec registry).

    Uses the post-``before_compile`` rewritten spec from the bundle so
    plugins that insert sub_specs (e.g. control_slots) actually execute.

    Returns an ExecutionTrace containing every node_start / node_end /
    edge_fire / subgraph_enter / subgraph_exit event plus final artifacts.
    """
    sub_registry = sub_registry or {}
    bundle = _compile_or_raise(spec, sub_registry)
    effective = InfoEdgeSpec.model_validate(bundle.spec_dump)
    trace = ExecutionTrace()
    runner = _Runner(
        spec=effective,
        bundle=bundle,
        initial=initial or {},
        sub_registry=sub_registry,
        trace=trace,
        subgraph_path=effective.id,
    )
    # Ensure the framework-emit bridge (session_log_emitter) is loaded
    # so every node_start / node_end / edge_fire / subgraph_* / *_compile
    # is routed into the Session. The plugin itself is auto-discovered
    # via plugins.discover(); the runner only ensures an instance exists
    # in the runner's inherited_plugins list if the spec didn't declare one.
    _ensure_framework_emitter(runner)
    trace.final_artifacts = runner.run()
    return trace


def _ensure_framework_emitter(runner: "_Runner") -> None:
    """Make sure session_log_emitter is in the runner's plugin chain.

    The runner has no knowledge of session_log specifically — it just
    ensures that *some* framework-emit plugin is attached. The
    session_log_emitter plugin class is discovered via
    plugins.discover(); if it's the registered framework-emit handler,
    an instance is added to the runner's inherited_plugins.
    """
    from agent_lab.plugins.base import HookEvent, get_plugin_class
    # Look for the canonical framework-emit kind. If the plugin library
    # exposes one under "session_log_emitter", use it.
    plugin_cls = get_plugin_class("session_log_emitter")
    if plugin_cls is None:
        return
    # Check whether it's already present in the runner's plugin chain
    for p in runner._inherited_plugins:
        if isinstance(p, plugin_cls):
            return
    # Add a default instance at the head of the chain (runs early).
    instance = plugin_cls(name="default_session_log_emitter",
                          kind="session_log_emitter",
                          binds=(), config={})
    runner._inherited_plugins.insert(0, instance)


def _compile_or_raise(
    spec: InfoEdgeSpec, sub_registry: dict[str, InfoEdgeSpec]
) -> CompiledGraphBundle:
    from agent_lab.graph.compile import compile as _compile

    return _compile(spec, sub_registry)
