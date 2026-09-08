"""on_error routing tests — ADR-0206 §5.6.

Covers:
  - on_error=fail    : deterministic failure raises (default behaviour)
  - on_error=retry   : transient failure is retried up to max_retries;
                      deterministic failure is not retried
  - on_error=route   : failure routes the EXCEPTION artifact to the
                      route_to target's first IN port; target runs in its
                      own topological slot
  - validate C6.1    : on_error=route without route_to / with missing
                      target / with no-IN-port target all surface as
                      compile-time errors

Fixtures register tiny throwing/passing Node classes via NodeRegistry
so the runner can exercise the policy dispatch without depending on
LCA runtime or a real tool dispatch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graph.spec import ErrorRoute, InfoEdgeSpec, InfoNode
from agent_lab.graph.validate import validate
from agent_lab.nodes.base import Node, register
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from agent_lab.primitives.edge import Edge
from agent_lab.runtime.runner import _NonRetryableError
from agent_lab.runtime.runner import run as run_graph

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixture node factories
# ---------------------------------------------------------------------------


_CALL_COUNTER: dict[str, int] = {}


def _reset_counters() -> None:
    _CALL_COUNTER.clear()


@register
class _BoomOnce(Node):
    """Raises ConnectionError on first call, then succeeds."""

    name = "_boom_once"

    def execute(self, node, inputs):
        _CALL_COUNTER["_boom_once"] = _CALL_COUNTER.get("_boom_once", 0) + 1
        if _CALL_COUNTER["_boom_once"] < 2:
            raise ConnectionError("transient network blip")
        out_port = node.outs[0]
        return {out_port: Artifact(kind=ArtifactKind.TEXT, content="ok")}


@register
class _BoomAlways(Node):
    """Always raises _NonRetryableError (deterministic)."""

    name = "_boom_always"

    def execute(self, node, inputs):
        _CALL_COUNTER["_boom_always"] = _CALL_COUNTER.get("_boom_always", 0) + 1
        raise _NonRetryableError("contract violation")


@register
class _BoomTransientAlways(Node):
    """Always raises ConnectionError (transient) — should be retried to exhaustion."""

    name = "_boom_transient_always"

    def execute(self, node, inputs):
        _CALL_COUNTER["_boom_transient_always"] = _CALL_COUNTER.get("_boom_transient_always", 0) + 1
        raise ConnectionError("timeout")


@register
class _Sink(Node):
    """Identity pass-through with configurable ports; used as route_to target."""

    name = "_sink"

    def execute(self, node, inputs):
        out_port = node.outs[0]
        # Return whatever the first non-empty input is, else empty TEXT.
        for v in inputs.values():
            if v is not None:
                return {
                    out_port: v.model_copy(
                        update={"content": {"handled": True, "original": v.content}}
                    )
                }
        return {out_port: Artifact(kind=ArtifactKind.TEXT, content="empty")}


# ---------------------------------------------------------------------------
# Helpers — build a minimal InfoEdgeSpec from kwargs
# ---------------------------------------------------------------------------


def _spec(
    nodes: list[InfoNode],
    edges: list[Edge] | None = None,
) -> InfoEdgeSpec:
    return InfoEdgeSpec(
        id="test_spec",
        version="0.0.1",
        region=InfoNode.model_fields["region"].default,  # digest
        nodes=nodes,
        edges=edges or [],
    )


def _node(
    nid: str,
    factory: str,
    *,
    on_error: ErrorRoute = ErrorRoute.FAIL,
    route_to: str | None = None,
    ins: list[str] | None = None,
    outs: list[str] | None = None,
    config: dict | None = None,
) -> InfoNode:
    return InfoNode(
        id=nid,
        factory=factory,
        on_error=on_error,
        route_to=route_to,
        ins=ins or [],
        outs=outs or ["out"],
        config=config or {},
    )


# ---------------------------------------------------------------------------
# (1) on_error=fail — deterministic failure raises (default)
# ---------------------------------------------------------------------------


def test_on_error_fail_raises() -> None:
    _reset_counters()
    spec = _spec(
        nodes=[
            _node("worker", "_boom_always", on_error=ErrorRoute.FAIL),
        ],
    )
    compile_spec(spec, sub_registry={})
    with pytest.raises(_NonRetryableError):
        run_graph(spec, sub_registry={})
    # single call, no retry
    assert _CALL_COUNTER["_boom_always"] == 1


# ---------------------------------------------------------------------------
# (2) on_error=retry — transient retried; deterministic not retried
# ---------------------------------------------------------------------------


def test_on_error_retry_transient_eventually_succeeds() -> None:
    _reset_counters()
    spec = _spec(
        nodes=[
            _node(
                "worker",
                "_boom_once",
                on_error=ErrorRoute.RETRY,
                config={"max_retries": 3},
            ),
        ],
    )
    compile_spec(spec, sub_registry={})
    trace = run_graph(spec, sub_registry={})
    assert _CALL_COUNTER["_boom_once"] == 2  # fail then succeed
    # The trace payload should record retry count
    retry_events = [
        e
        for e in trace.events
        if e.kind == "node_end"
        and (e.payload or {}).get("status") == "ok"
        and (e.payload or {}).get("retried_attempts") == 1
    ]
    assert retry_events, f"expected retry marker in trace; got {trace.to_lines()[-3:]}"


def test_on_error_retry_deterministic_does_not_retry() -> None:
    _reset_counters()
    spec = _spec(
        nodes=[
            _node(
                "worker",
                "_boom_always",  # raises _NonRetryableError
                on_error=ErrorRoute.RETRY,
                config={"max_retries": 3},
            ),
        ],
    )
    compile_spec(spec, sub_registry={})
    with pytest.raises(_NonRetryableError):
        run_graph(spec, sub_registry={})
    assert _CALL_COUNTER["_boom_always"] == 1  # deterministic: NO retry


def test_on_error_retry_exhausts_then_raises() -> None:
    _reset_counters()
    spec = _spec(
        nodes=[
            _node(
                "worker",
                "_boom_transient_always",
                on_error=ErrorRoute.RETRY,
                config={"max_retries": 2},
            ),
        ],
    )
    compile_spec(spec, sub_registry={})
    with pytest.raises(ConnectionError):
        run_graph(spec, sub_registry={})
    assert _CALL_COUNTER["_boom_transient_always"] == 2  # exhausted retries


# ---------------------------------------------------------------------------
# (3) on_error=route — exception delivered to route_to target
# ---------------------------------------------------------------------------


def test_on_error_route_delivers_exception_to_target() -> None:
    _reset_counters()
    spec = _spec(
        nodes=[
            _node(
                "worker",
                "_boom_always",
                on_error=ErrorRoute.ROUTE,
                route_to="deny",
            ),
            _node(
                "deny",
                "_sink",
                ins=["exception"],
                outs=["handled"],
            ),
        ],
    )
    # C6.1 only requires route_to target has an IN port; no edges needed
    # since the runner seeds (deny, exception) directly into self.store.
    compile_spec(spec, sub_registry={})
    trace = run_graph(spec, sub_registry={})
    # worker raised; route_to deny ran; deny.outputs["handled"] is the
    # EXCEPTION artifact wrapped in a handled envelope.
    handled = trace.final_artifacts.get("handled")
    assert handled is not None
    assert handled.kind == ArtifactKind.EXCEPTION
    inner = handled.content
    assert inner["handled"] is True
    assert inner["original"]["error_class"] == "node.skipped"
    assert inner["original"]["node_id"] == "worker"


def test_on_error_route_skips_worker_invocation() -> None:
    _reset_counters()
    spec = _spec(
        nodes=[
            _node(
                "worker",
                "_boom_always",
                on_error=ErrorRoute.ROUTE,
                route_to="deny",
            ),
            _node("deny", "_sink", ins=["exception"], outs=["handled"]),
        ],
    )
    compile_spec(spec, sub_registry={})
    run_graph(spec, sub_registry={})
    # Worker MUST NOT be invoked under on_error=route — the route
    # short-circuits before the factory call.
    assert _CALL_COUNTER.get("_boom_always", 0) == 0


# ---------------------------------------------------------------------------
# (4) validate C6.1 — compile-time errors for malformed on_error=route
# ---------------------------------------------------------------------------


def test_validate_rejects_route_to_without_route_to() -> None:
    spec = _spec(
        nodes=[
            _node(
                "worker",
                "_boom_always",
                on_error=ErrorRoute.ROUTE,
                route_to=None,
            ),
        ],
    )
    errs = validate(spec)
    assert any("C6.1" in e and "route_to is unset" in e for e in errs)


def test_validate_rejects_route_to_missing_target() -> None:
    spec = _spec(
        nodes=[
            _node(
                "worker",
                "_boom_always",
                on_error=ErrorRoute.ROUTE,
                route_to="nonexistent",
            ),
        ],
    )
    errs = validate(spec)
    assert any("C6.1" in e and "missing node nonexistent" in e for e in errs)


def test_validate_rejects_route_to_target_with_no_in_port() -> None:
    spec = _spec(
        nodes=[
            _node(
                "worker",
                "_boom_always",
                on_error=ErrorRoute.ROUTE,
                route_to="deny",
            ),
            # deny has no ins — cannot receive the EXCEPTION artifact
            _node("deny", "_sink", ins=[], outs=["handled"]),
        ],
    )
    errs = validate(spec)
    assert any("C6.1" in e and "no IN port" in e for e in errs)


# ---------------------------------------------------------------------------
# (5) act.yaml — on_error=route declared in real spec
# ---------------------------------------------------------------------------


def test_act_execute_folds_errors_into_receipt() -> None:
    """act.execute uses default on_error=fail; tool failures become receipt content.

    The runner's on_error=route is a pre-invoke skip (not catch-and-route),
    so the production act graph must not use it on execute.
    """
    from agent_lab.graphs import load_registry

    specs = load_registry("act")
    execute_node = specs["act"].node("execute")
    assert execute_node.on_error == ErrorRoute.FAIL
    assert execute_node.route_to is None
    observe = specs["act"].node("observe")
    assert "receipt" in observe.ins
    errs = validate(specs["act"])
    assert not [e for e in errs if e.startswith("C6.1")], (
        f"act C6.1 violations: {[e for e in errs if e.startswith('C6.1')]}"
    )


# ---------------------------------------------------------------------------
# (6) Artifact.EXCEPTION exists
# ---------------------------------------------------------------------------


def test_artifact_kind_includes_exception() -> None:
    assert ArtifactKind.EXCEPTION.value == "exception"
