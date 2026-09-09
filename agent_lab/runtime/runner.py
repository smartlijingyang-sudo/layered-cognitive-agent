"""Runner — recursive interpreter over CompiledGraphBundle.

Single source of execution truth. Same interpreter runs the root graph
and every nested sub-graph (ADR-0206 C11: one graph kind, one runner).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agent_lab.graph.compile import CompiledGraphBundle
from agent_lab.graph.spec import InfoEdgeSpec, InfoNode, SubSpecLink
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_exception
from agent_lab.primitives.edge import Edge
from agent_lab.runtime.invoke import invoke as invoke_node
from agent_lab.runtime.seams import Seams

_log = logging.getLogger(__name__)


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
        seams: "Seams | None" = None,
        runtime_registry: dict[str, type] | None = None,
        inherited_plugins: list | None = None,
    ):
        self.spec = spec
        self.bundle = bundle
        self.initial = dict(initial)
        self.sub_registry = sub_registry
        self.trace = trace
        self.subgraph_path = subgraph_path
        self.seams = seams
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

        PR-A.3 — resolution moved from ``agent_lab.plugins.resolve_plugin``
        to ``lca.plugins.lab.internal.loader.resolve_plugin``. The handler
        instance still satisfies the ``GraphPlugin`` hook-method contract
        (until PR-D rewrites the 9 hook subclasses).
        """
        if self._inherited_plugins:
            return list(self._inherited_plugins)

        from lca.plugins.lab.internal.loader import load_all, resolve_plugin

        load_all()

        bundle_plugins: list = list(getattr(self.bundle, "plugin_instances", []) or [])
        own_plugins: list = []
        try:
            for ref in getattr(self.spec, "plugins", []) or []:
                inst = resolve_plugin(ref)
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
        from lca.plugins.lab.internal.hooks import HookContext, HookEvent, fanout_hooks

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
        """Fan AFTER_NODE_EXECUTE for observation only; never replace artifacts.

        Hooks may read ``payload["outputs"]``. Per-port replacements
        (``id(new) != id(old)``) are ignored and logged; worker outputs
        remain the data plane (N6).
        """
        from lca.plugins.lab.internal.hooks import HookContext, HookEvent, fanout_hooks

        plugins = self._plugins()
        original = dict(outputs)
        ctx = HookContext(
            event=HookEvent.AFTER_NODE_EXECUTE,
            spec_id=self.spec.id,
            subgraph_path=self.subgraph_path,
            node_id=node_id,
            payload={"outputs": dict(outputs), "plugins": plugins},
        )
        new_ctx = fanout_hooks(plugins, HookEvent.AFTER_NODE_EXECUTE, ctx)
        candidate = new_ctx.payload.get("outputs", original)
        if not isinstance(candidate, dict):
            return original
        frozen: dict[str, Artifact] = {}
        for port_id, old_art in original.items():
            new_art = candidate.get(port_id, old_art)
            if new_art is old_art:
                frozen[port_id] = old_art
            else:
                _log.warning(
                    "node %s port %s: hook attempted to replace output; keeping original",
                    node_id,
                    port_id,
                )
                frozen[port_id] = old_art
        return frozen

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
        outputs, status, error_info = self._invoke_with_policy(node, inputs, self.seams)

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

        # Propagate to downstream IN ports via data/project/borrow edges.
        for edge in self.spec.edges:
            if edge.from_ref.node_id != node_id:
                continue
            if edge.kind.value not in ("data", "project", "borrow"):
                continue
            src_port = edge.from_ref.port_id
            dst_port = edge.to_ref.port_id
            src_a = self.store.get((node_id, src_port))
            if src_a is None:
                continue
            art = src_a
            if edge.kind.value == "borrow":
                art = self._apply_borrow_grant(edge, src_a)
            self.store[(edge.to_ref.node_id, dst_port)] = art
            self._emit(
                TraceEvent(
                    kind="edge_fire",
                    subgraph_path=self.subgraph_path,
                    edge_id=edge.id,
                    artifact_digest=art.short_id(),
                    payload={
                        "kind": edge.kind.value,
                        "from": edge.from_ref.label(),
                        "to": edge.to_ref.label(),
                        **({"grant_id": edge.grant_id} if edge.grant_id else {}),
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

    def _apply_borrow_grant(self, edge: Edge, art: Artifact) -> Artifact:
        """Copy a borrow edge under its InfoGrant; enforce max_bytes / redact."""
        if not edge.grant_id:
            raise _NonRetryableError(f"borrow edge {edge.id} has no grant_id")
        grant = next((g for g in self.spec.grants if g.id == edge.grant_id), None)
        if grant is None:
            raise _NonRetryableError(
                f"borrow edge {edge.id} references unknown grant {edge.grant_id!r}"
            )
        if grant.max_bytes:
            size = len(json.dumps(art.content))
            if size > grant.max_bytes:
                raise _NonRetryableError(
                    f"borrow edge {edge.id} exceeds grant.max_bytes={grant.max_bytes} (got {size})"
                )
        if grant.redact and isinstance(art.content, dict):
            redacted = {k: v for k, v in art.content.items() if k not in grant.redact}
            return Artifact(kind=art.kind, content=redacted, schema_ref=art.schema_ref)
        return art

    def _route_exception(
        self, node: InfoNode, exc: Exception
    ) -> tuple[dict[str, Artifact], str, dict[str, Any]]:
        """Deliver EXCEPTION to route_to's first IN, invoke target, mark both executed."""
        target_id = node.route_to
        if not target_id:
            raise RuntimeError(f"node {node.id}: on_error=route requires route_to to be set")
        try:
            target = self.spec.node(target_id)
        except KeyError as err:
            raise RuntimeError(
                f"node {node.id}: on_error=route targets missing node {target_id}"
            ) from err
        if not target.ins:
            raise RuntimeError(
                f"node {node.id}: route_to={target_id} has no IN port to receive"
                " the EXCEPTION artifact"
            )
        exception_port = target.ins[0]
        exc_artifact = make_exception(
            error_class=type(exc).__name__,
            message=str(exc),
            node_id=node.id,
            transient=False,
        )
        self.store[(target_id, exception_port)] = exc_artifact
        target_inputs: dict[str, Artifact] = {
            port_id: self.store.get(
                (target_id, port_id),
                Artifact(kind=ArtifactKind.TEXT, content=""),
            )
            for port_id in target.ins
        }
        target_outputs = invoke_node(target, target_inputs, self.seams)
        for port_id, artifact in target_outputs.items():
            self.store[(target_id, port_id)] = artifact
        self._executed.add(node.id)
        self._executed.add(target_id)
        return target_outputs, "routed", {"status": "routed", "route_to": target_id}

    def _invoke_with_policy(
        self, node: InfoNode, inputs: dict[str, Artifact], seams: "Seams | None" = None
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
          - route    — invoke the worker first; on exception, deliver
                       EXCEPTION to route_to and invoke that target
        """
        error_info: dict[str, Any] = {}
        max_attempts = 1
        if node.on_error.value == "retry":
            max_attempts = max(1, int(node.config.get("max_retries", 3)))

        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                outputs = invoke_node(node, inputs, seams)
                if attempt > 1:
                    error_info["retried_attempts"] = attempt - 1
                return outputs, "ok", error_info
            except Exception as exc:
                if node.on_error.value == "route":
                    return self._route_exception(node, exc)
                last_exc = exc
                # ADR-0206 §5.6: deterministic errors are never retried.
                if isinstance(exc, _NonRetryableError):
                    break
                if attempt == max_attempts:
                    break
        if last_exc is None:
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
            seams=self.seams,
            inherited_plugins=self._plugins(),
        )
        child_outputs = child.run()
        missing = [sub for sub in link.output_map if sub not in child_outputs]
        if missing:
            raise RuntimeError(f"sub_spec {link.sub_spec_id} missing exports {missing}")
        for sub_port, parent_port in link.output_map.items():
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

    Uses the post-``before_compile`` spec from the bundle dump.

    Returns an ExecutionTrace containing every node_start / node_end /
    edge_fire / subgraph_enter / subgraph_exit event plus final artifacts.
    """
    sub_registry = sub_registry or {}
    bundle = _compile_or_raise(spec, sub_registry)
    effective = InfoEdgeSpec.model_validate(bundle.spec_dump)
    trace = ExecutionTrace()
    # The runner is the single assembler of typed seam handles. Workers
    # never import framework modules; they only call methods on seams.
    # When seams is not provided by the caller, build the default body
    # handle from the lab body_provider so act.* workers get their
    # SimpleBody via seams.body.act(intent=...) instead of importing the
    # provider module themselves.
    runner = _Runner(
        spec=effective,
        bundle=bundle,
        initial=initial or {},
        sub_registry=sub_registry,
        trace=trace,
        subgraph_path=effective.id,
        seams=_default_seams(),
    )
    # Ensure the framework-emit bridge (session_log_emitter) is loaded
    # so every node_start / node_end / edge_fire / subgraph_* / *_compile
    # is routed into the Session. The plugin itself is auto-discovered
    # via plugins.discover(); the runner only ensures an instance exists
    # in the runner's inherited_plugins list if the spec didn't declare one.
    _ensure_framework_emitter(runner)
    trace.final_artifacts = runner.run()
    return trace


def _ensure_framework_emitter(runner: _Runner) -> None:
    """Make sure session_log_emitter is in the runner's plugin chain.

    The runner has no knowledge of session_log specifically — it just
    ensures that *some* framework-emit plugin is attached. The
    session_log_emitter plugin instance is loaded via
    lca.plugins.lab.internal.loader; if it exists, it is added to the
    runner's inherited_plugins if not already present.
    """
    from lca.plugins.lab.internal.loader import get_instance, load_all

    load_all()

    # Look for the canonical framework-emit handler in the loader registry.
    instance = get_instance("lab.hook.session_log_emitter")
    if instance is None:
        return

    # Check whether it's already present in the runner's plugin chain
    for p in runner._inherited_plugins:
        if p is instance:
            return
    # Add it at the head of the chain (runs early).
    runner._inherited_plugins.insert(0, instance)


def _compile_or_raise(
    spec: InfoEdgeSpec, sub_registry: dict[str, InfoEdgeSpec]
) -> CompiledGraphBundle:
    from agent_lab.graph.compile import compile as _compile

    return _compile(spec, sub_registry)


def _default_seams() -> "Seams":
    """Build the default Seams handle from the lab body_provider.

    Composition lives here (the runner), not in worker modules. Workers
    receive a typed handle and call seams.body.act(intent=...) only.
    """
    from lca.plugins.lab.act.body_provider.plugin import get_body, plan_ref_default
    from lca.plugins.lab.session.provider.plugin import PLAN_REF

    return Seams(body=get_body(), plan_ref=PLAN_REF or plan_ref_default())
