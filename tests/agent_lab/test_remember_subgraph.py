"""remember sub-graph: admit → commit → snapshot.

Covers:
  - remember.yaml loads + compiles as a three-node chain
  - admit filters memory_candidates via admit policy
  - LcaRememberJournalProvider appends turn fact including admitted
  - LcaRememberStateStoreProvider saves state + remember_signal
  - full sub-graph runs via agent_lab's runner
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_remember_subgraph_loads_and_compiles() -> None:
    specs = load_registry("remember")
    assert "remember" in specs
    spec = specs["remember"]
    assert {n.id for n in spec.nodes} == {"admit", "commit", "snapshot"}
    assert {n.factory for n in spec.nodes} == {
        "remember.admit",
        "remember.commit",
        "remember.snapshot",
    }
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "remember"
    flat = [nid for layer in bundle.layers for nid in layer]
    assert flat.index("admit") < flat.index("commit")
    assert flat.index("commit") < flat.index("snapshot")


# ---------------------------------------------------------------------------
# (2) admit node — filter candidates
# ---------------------------------------------------------------------------


def test_remember_admit_passes_candidates_when_policy_allows() -> None:
    from agent_lab.graph.spec import InfoNode, NodeRegion
    from agent_lab.nodes.base import NodeRegistry

    factory = NodeRegistry.get("remember.admit")
    node = InfoNode(
        id="admit",
        region=NodeRegion.PHASE,
        factory="remember.admit",
        config={},
        ins=["in_candidates", "in_observation"],
        outs=["admitted"],
    )
    out = factory().execute(
        node,
        {
            "in_candidates": Artifact(
                kind=ArtifactKind.FACT,
                content={"items": [{"kind": "lesson", "text": "keep it"}]},
                schema_ref="memory.candidates.v1",
            ),
            "in_observation": Artifact(
                kind=ArtifactKind.FACT,
                content={"observation_id": "obs_1", "success": True},
            ),
        },
    )
    assert out["admitted"].schema_ref == "memory.admitted.v1"
    assert out["admitted"].content["admitted"] is True
    assert out["admitted"].content["items"] == [{"kind": "lesson", "text": "keep it"}]


def test_remember_admit_drops_candidates_when_policy_denies() -> None:
    from agent_lab.adapters.lca_control import (
        register_fixture_remember_admit,
        unregister_fixture_remember_admit,
    )
    from agent_lab.graph.spec import InfoNode, NodeRegion
    from agent_lab.nodes.base import NodeRegistry

    name = "test-remember-admit-deny"
    register_fixture_remember_admit(name, lambda _obs: False)
    try:
        factory = NodeRegistry.get("remember.admit")
        node = InfoNode(
            id="admit",
            region=NodeRegion.PHASE,
            factory="remember.admit",
            config={"provider_config": {"fixture_remember_admit_name": name}},
            ins=["in_candidates", "in_observation"],
            outs=["admitted"],
        )
        out = factory().execute(
            node,
            {
                "in_candidates": Artifact(
                    kind=ArtifactKind.FACT,
                    content={"items": [{"kind": "lesson", "text": "drop me"}]},
                    schema_ref="memory.candidates.v1",
                ),
            },
        )
        assert out["admitted"].content["admitted"] is False
        assert out["admitted"].content["items"] == []
    finally:
        unregister_fixture_remember_admit(name)


# ---------------------------------------------------------------------------
# (3) journal provider
# ---------------------------------------------------------------------------


def test_lca_remember_journal_provider_with_fixture() -> None:
    """Register a fixture Session; assert append receives turn fact + admitted."""
    from agent_lab.adapters.lca_memory import (
        LcaRememberJournalProvider,
        register_fixture_session,
        unregister_fixture_session,
    )

    appended: list[tuple[str, dict]] = []

    class _FakeEvent:
        def __init__(self, seq, id):
            self.seq = seq
            self.id = id

    class _RecordingSession:
        def append(self, event_type, data, **kwargs):
            appended.append((event_type, data))
            return _FakeEvent(seq=len(appended) - 1, id=f"evt_{len(appended)}")

    session = _RecordingSession()
    name = "test-remember-session"
    register_fixture_session(name, session)
    try:
        provider = LcaRememberJournalProvider.from_node_config(
            {"provider_config": {"fixture_session_name": name}}
        )
        reflection = Artifact(
            kind=ArtifactKind.FACT,
            content={"topic": "self_assessment", "score": 0.8},
        )
        observation = Artifact(
            kind=ArtifactKind.FACT,
            content={"tool": "bash", "result": "ok"},
        )
        decision = Artifact(
            kind=ArtifactKind.FACT,
            content={"decision_id": "dec_01", "action_type": "respond"},
        )
        admitted = Artifact(
            kind=ArtifactKind.FACT,
            content={"admitted": True, "items": [{"kind": "lesson", "text": "ok"}]},
            schema_ref="memory.admitted.v1",
        )
        out = provider.append_journal(
            reflection_artifact=reflection,
            observation_artifact=observation,
            decision_artifact=decision,
            admitted_artifact=admitted,
        )
        assert "journal_fact" in out
        fact = out["journal_fact"]
        assert fact.kind == ArtifactKind.FACT
        assert fact.schema_ref == "journal.fact.v1"
        assert len(appended) == 1
        event_type, data = appended[0]
        assert event_type == "remember.turn_fact"
        assert data["reflection"]["topic"] == "self_assessment"
        assert data["observation"]["tool"] == "bash"
        assert data["decision"]["decision_id"] == "dec_01"
        assert data["admitted"]["items"][0]["text"] == "ok"
        assert fact.content["seq"] == 0
        assert fact.content["id"] == "evt_1"
    finally:
        unregister_fixture_session(name)


def test_lca_remember_journal_provider_real_session_event_id() -> None:
    """Real SessionEvent has no .id; journal_fact.id must be session_id:seq."""
    from agent_lab.adapters.lca_memory import LcaRememberJournalProvider
    from agent_lab.nodes.session_log._sink import get_session

    session = get_session()
    before = session.event_count
    provider = LcaRememberJournalProvider(_session=session)
    out = provider.append_journal(
        reflection_artifact=Artifact(
            kind=ArtifactKind.FACT,
            content={"verdict": "on_track"},
        ),
        observation_artifact=Artifact(
            kind=ArtifactKind.FACT,
            content={"tool": "bash", "status": "ok", "success": True},
        ),
        decision_artifact=Artifact(
            kind=ArtifactKind.FACT,
            content={"decision_id": "dec_real", "action_type": "call_tool"},
        ),
    )
    fact = out["journal_fact"]
    assert fact.digest, "journal_fact artifact must carry a non-empty digest"
    assert fact.content["seq"] == before
    assert fact.content["id"] == f"{session.id}:{before}"
    assert session.event_count == before + 1
    types = {session.event_at(i).type for i in range(session.event_count)}
    assert "remember.turn_fact" in types


# ---------------------------------------------------------------------------
# (4) state store provider
# ---------------------------------------------------------------------------


def test_lca_remember_state_store_provider_with_fixture() -> None:
    """Register a fixture StateStore; assert save receives correct state."""
    from agent_lab.adapters.lca_memory import (
        LcaRememberStateStoreProvider,
        register_fixture_state_store,
        unregister_fixture_state_store,
    )

    saved_states: list[dict] = []

    class _RecordingStateStore:
        async def save(self, state):
            saved_states.append(state)
            return f"ref_{len(saved_states)}"

    store = _RecordingStateStore()
    name = "test-remember-store"
    register_fixture_state_store(name, store)
    try:
        provider = LcaRememberStateStoreProvider.from_node_config(
            {"provider_config": {"fixture_state_store_name": name}}
        )
        journal_fact = Artifact(
            kind=ArtifactKind.FACT,
            content={"seq": 42, "id": "evt_7"},
            schema_ref="journal.fact.v1",
        )
        out = provider.save_state(journal_fact_artifact=journal_fact)
        assert "state_ref" in out
        assert "remember_signal" in out
        ref = out["state_ref"]
        assert ref.kind == ArtifactKind.FACT
        assert ref.schema_ref == "state.ref.v1"
        assert ref.content["state_ref"] == "ref_1"
        signal = out["remember_signal"]
        assert signal.schema_ref == "remember.signal.v1"
        assert signal.content["phase"] == "remember"
        assert len(saved_states) == 1
        state = saved_states[0]
        assert state["journal_seq"] == 42
        assert state["journal_id"] == "evt_7"
    finally:
        unregister_fixture_state_store(name)


# ---------------------------------------------------------------------------
# (5) runner integration
# ---------------------------------------------------------------------------


def test_remember_subgraph_runs_via_runner() -> None:
    """The remember sub-graph runs end-to-end through agent_lab's runner."""
    from agent_lab.adapters.lca_memory import (
        register_fixture_session,
        register_fixture_state_store,
        unregister_fixture_session,
        unregister_fixture_state_store,
    )
    from agent_lab.runtime.runner import run as run_graph

    specs = load_registry("remember")
    remember_spec = specs["remember"]

    appended: list[tuple[str, dict]] = []

    class _FakeEvent:
        def __init__(self, seq, id):
            self.seq = seq
            self.id = id

    class _FixtureSession:
        def append(self, event_type, data, **kwargs):
            appended.append((event_type, data))
            return _FakeEvent(seq=len(appended) - 1, id=f"evt_{len(appended)}")

    class _FixtureStateStore:
        async def save(self, state):
            return "state_ref_001"

    session_name = "runner-session"
    store_name = "runner-store"
    register_fixture_session(session_name, _FixtureSession())
    register_fixture_state_store(store_name, _FixtureStateStore())
    try:
        for n in remember_spec.nodes:
            if n.id == "commit":
                n.config["provider_config"] = {
                    "fixture_session_name": session_name,
                }
            if n.id == "snapshot":
                n.config["provider_config"] = {
                    "fixture_state_store_name": store_name,
                }

        initial = {
            "in_reflection": Artifact(
                kind=ArtifactKind.FACT,
                content={"topic": "turn_review", "insight": "ok"},
            ),
            "in_observation": Artifact(
                kind=ArtifactKind.FACT,
                content={"tool": "read_file", "status": "success"},
            ),
            "in_decision": Artifact(
                kind=ArtifactKind.FACT,
                content={"decision_id": "dec_42", "action_type": "call_tool"},
            ),
            "in_candidates": Artifact(
                kind=ArtifactKind.FACT,
                content={"items": [{"kind": "lesson", "text": "persist this"}]},
                schema_ref="memory.candidates.v1",
            ),
        }
        trace = run_graph(remember_spec, initial=initial, sub_registry=specs)

        assert "journal_fact" in trace.final_artifacts, (
            f"remember must emit journal_fact; got {sorted(trace.final_artifacts)}"
        )
        assert "state_ref" in trace.final_artifacts
        assert "remember_signal" in trace.final_artifacts

        journal = trace.final_artifacts["journal_fact"]
        assert journal.kind == ArtifactKind.FACT
        assert journal.content["seq"] == 0

        assert len(appended) == 1
        _, data = appended[0]
        assert data["admitted"]["items"][0]["text"] == "persist this"

        state = trace.final_artifacts["state_ref"]
        assert state.content["state_ref"] == "state_ref_001"

        signal = trace.final_artifacts["remember_signal"]
        assert signal.content["phase"] == "remember"
    finally:
        unregister_fixture_session(session_name)
        unregister_fixture_state_store(store_name)
