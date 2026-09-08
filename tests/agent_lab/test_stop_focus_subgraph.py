"""stop_focus sub-graph tests.

Covers:
  - stop_focus.yaml loads + compiles without validation errors.
  - LcaControlStopFocusProvider default returns kind=allow, count=0.
  - LcaControlStopFocusProvider with stagnant history returns kind=stop
    when count >= max_consecutive_stagnant_turns.
  - Full sub-graph runs via agent_lab's runner.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the new control node is registered.
import agent_lab.nodes.control.stop_focus_node.plugin  # noqa: F401
from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_stop_focus_subgraph_loads_and_compiles() -> None:
    specs = load_registry("stop_focus")
    assert "stop_focus" in specs
    spec = specs["stop_focus"]
    assert {n.id for n in spec.nodes} == {"stop_focus_handler"}
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "stop_focus"


# ---------------------------------------------------------------------------
# (2) provider — default allow (count=0)
# ---------------------------------------------------------------------------


def test_lca_stop_focus_provider_default_allow() -> None:
    from agent_lab.adapters.lca_control import LcaControlStopFocusProvider

    provider = LcaControlStopFocusProvider.from_node_config({})
    out = provider.evaluate(
        state=Artifact(kind=ArtifactKind.FACT, content={"history": []}),
        decision=Artifact(
            kind=ArtifactKind.FACT,
            content={"decision_id": "dec_1", "action_type": "respond"},
        ),
    )
    assert "focus_verdict" in out
    result = out["focus_verdict"]
    assert result.kind == ArtifactKind.FACT
    assert result.schema_ref == "stop.focus.v1"
    assert result.content["kind"] == "allow"
    assert result.content["count"] == 0
    assert result.content["limit"] == 3


# ---------------------------------------------------------------------------
# (3) provider — stagnant history → stop when count >= limit
# ---------------------------------------------------------------------------


def test_lca_stop_focus_provider_stagnant_history_stops() -> None:
    """Three stagnant turns (limit=3) trip the focus policy."""
    from agent_lab.adapters.lca_control import LcaControlStopFocusProvider

    stagnant_turn = {
        "observation": {"success": False},
        "reflection": {"verdict": "needs_correction"},
        "decision": {
            "decision_id": "dec_x",
            "action_type": "call_tool",
            "tool_calls": [{"tool_name": "bash"}],
            "response_text": "",
        },
    }
    state = Artifact(
        kind=ArtifactKind.FACT,
        content={"history": [stagnant_turn, stagnant_turn, stagnant_turn]},
    )
    decision = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_x",
            "action_type": "call_tool",
            "tool_calls": [{"tool_name": "bash"}],
            "response_text": "",
        },
    )
    provider = LcaControlStopFocusProvider.from_node_config(
        {"provider_config": {"max_consecutive_stagnant_turns": 3}}
    )
    out = provider.evaluate(state=state, decision=decision)
    result = out["focus_verdict"]
    assert result.content["kind"] == "stop"
    assert result.content["count"] == 3
    assert result.content["limit"] == 3
    assert "stagnant" in result.content["detail"].lower()


def test_lca_stop_focus_provider_successful_history_allows() -> None:
    """Successful observation breaks the stagnation streak."""
    from agent_lab.adapters.lca_control import LcaControlStopFocusProvider

    state = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "history": [
                {"observation": {"success": False}, "reflection": {"verdict": "needs_correction"}},
                {"observation": {"success": True}, "reflection": {"verdict": "on_track"}},
            ]
        },
    )
    provider = LcaControlStopFocusProvider.from_node_config({})
    out = provider.evaluate(state=state, decision=None)
    result = out["focus_verdict"]
    assert result.content["kind"] == "allow"
    assert result.content["count"] == 0


# ---------------------------------------------------------------------------
# (4) runner integration
# ---------------------------------------------------------------------------


def test_stop_focus_subgraph_runs_via_runner() -> None:
    from agent_lab.runtime.runner import run as run_graph

    specs = load_registry("stop_focus")
    spec = specs["stop_focus"]

    stagnant_turn = {
        "observation": {"success": False},
        "reflection": {"verdict": "blocked"},
        "decision": {
            "decision_id": "dec_run",
            "action_type": "call_tool",
            "tool_calls": [{"tool_name": "bash"}],
            "response_text": "",
        },
    }
    initial = {
        "in_state": Artifact(
            kind=ArtifactKind.FACT,
            content={"history": [stagnant_turn, stagnant_turn, stagnant_turn]},
        ),
        "in_decision": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "decision_id": "dec_run",
                "action_type": "call_tool",
                "tool_calls": [{"tool_name": "bash"}],
            },
        ),
    }
    trace = run_graph(spec, initial=initial, sub_registry=specs)
    assert "focus_verdict" in trace.final_artifacts, (
        f"stop_focus must emit focus_verdict; got {sorted(trace.final_artifacts)}"
    )
    result = trace.final_artifacts["focus_verdict"]
    assert result.content["kind"] == "stop"
    assert result.content["count"] == 3
