"""event_log graph wiring + adapter + node tests.

Covers:
  - event_log.yaml loads + compiles without validation errors
  - LcaEventEmitProvider writes to a fixture Session and returns event_fact
  - LcaEventTailProvider reads from a fixture Session with pre-appended events
  - The full graph runs via agent_lab's runner on the emit sub-graph
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_event_log_graph_loads_and_compiles() -> None:
    specs = load_registry("event_log")
    assert "event_log" in specs
    spec = specs["event_log"]
    assert {n.id for n in spec.nodes} == {"emit", "tail"}
    bundle = compile_spec(spec)
    assert bundle.spec_id == "event_log"


# ---------------------------------------------------------------------------
# (2) emit provider with fixture Session
# ---------------------------------------------------------------------------


def test_lca_event_emit_provider_with_fixture() -> None:
    """Register a stub Session; emit; assert Session.append received the
    right event_type + data; returned event_fact has seq/id."""
    from agent_lab.adapters.lca_event import (
        LcaEventEmitProvider,
        _NoopSession,
        register_fixture_session,
        unregister_fixture_session,
    )

    name = "test-event-emit-fixture"
    session = _NoopSession(session_id="test-session-emit")
    register_fixture_session(name, session)
    try:
        provider = LcaEventEmitProvider.from_node_config(
            {"provider_config": {"fixture_session_name": name}}
        )
        event_type_artifact = make_text("test/event")
        event_data_artifact = Artifact(
            kind=ArtifactKind.FACT,
            content={"key": "value", "count": 42},
            schema_ref="test.data.v1",
        )
        result = provider.emit(event_type_artifact, event_data_artifact)
        assert "event_fact" in result
        event_fact = result["event_fact"]
        assert event_fact.kind == ArtifactKind.FACT
        assert event_fact.content["seq"] == 0
        assert event_fact.content["id"] == "test-session-emit"
        assert event_fact.content["type"] == "test/event"
        # Verify the Session received the right data
        assert len(session._log) == 1
        logged = session._log[0]
        assert logged.type == "test/event"
        assert logged.data == {"key": "value", "count": 42}
    finally:
        unregister_fixture_session(name)


# ---------------------------------------------------------------------------
# (3) tail provider with fixture Session
# ---------------------------------------------------------------------------


def test_lca_event_tail_provider_with_fixture() -> None:
    """Register a Session with 3 pre-appended events; tail; assert the
    events list is returned."""
    from agent_lab.adapters.lca_event import (
        LcaEventTailProvider,
        _NoopSession,
        register_fixture_session,
        unregister_fixture_session,
    )

    name = "test-event-tail-fixture"
    session = _NoopSession(session_id="test-session-tail")
    # Pre-append 3 events
    session.append("event/a", {"a": 1})
    session.append("event/b", {"b": 2})
    session.append("event/c", {"c": 3})
    register_fixture_session(name, session)
    try:
        provider = LcaEventTailProvider.from_node_config(
            {"provider_config": {"fixture_session_name": name}}
        )
        from_seq_artifact = Artifact(kind=ArtifactKind.FACT, content={"value": 0})
        limit_artifact = Artifact(kind=ArtifactKind.FACT, content={"value": 100})
        result = provider.tail(from_seq_artifact, limit_artifact)
        assert "events" in result
        events_artifact = result["events"]
        assert events_artifact.kind == ArtifactKind.FACT
        events_list = events_artifact.content
        assert isinstance(events_list, list)
        assert len(events_list) == 3
        assert events_list[0]["type"] == "event/a"
        assert events_list[1]["type"] == "event/b"
        assert events_list[2]["type"] == "event/c"
        assert events_list[0]["seq"] == 0
        assert events_list[1]["seq"] == 1
        assert events_list[2]["seq"] == 2
    finally:
        unregister_fixture_session(name)


# ---------------------------------------------------------------------------
# (4) runner integration — emit sub-graph
# ---------------------------------------------------------------------------


def test_event_log_graph_runs_via_runner() -> None:
    """Run the emit node through the runner with a fixture Session;
    assert event_fact artifact is produced."""
    from agent_lab.adapters.lca_event import (
        _NoopSession,
        register_fixture_session,
        unregister_fixture_session,
    )
    from agent_lab.runtime.runner import run as run_graph

    name = "test-event-runner-fixture"
    session = _NoopSession(session_id="test-session-runner")
    register_fixture_session(name, session)
    try:
        specs = load_registry("event_log")
        spec = specs["event_log"]
        # Configure the emit node to use our fixture session
        for n in spec.nodes:
            if n.id == "emit":
                n.config["provider_config"] = {"fixture_session_name": name}

        initial = {
            "event_type": make_text("runner/test_event"),
            "event_data": Artifact(
                kind=ArtifactKind.FACT,
                content={"source": "runner", "step": 1},
                schema_ref="test.data.v1",
            ),
        }
        trace = run_graph(spec, initial=initial)
        assert "event_fact" in trace.final_artifacts, (
            f"event_log must emit event_fact; got {sorted(trace.final_artifacts)}"
        )
        event_fact = trace.final_artifacts["event_fact"]
        assert event_fact.kind == ArtifactKind.FACT
        assert event_fact.content["seq"] == 0
        assert event_fact.content["type"] == "runner/test_event"
    finally:
        unregister_fixture_session(name)
