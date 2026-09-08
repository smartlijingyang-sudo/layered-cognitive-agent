"""Act sub-graph: shape → authorize → execute → observe.

Covers:
  - act.yaml loads + compiles (with project edge into model_eye)
  - call_tool allow → observation with status=ok (or tool result)
  - authorize deny → no tool side effect; observation.status=denied
  - respond / refuse → no_effect observation without tool call
  - no parallel effect_dispatch SSOT / no act stub factories
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind
from agent_lab.primitives.edge import EdgeKind
from agent_lab.runtime.runner import run as run_graph

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _decision(
    *,
    action_type: str,
    tool_calls: list[dict] | None = None,
    response_text: str | None = None,
) -> Artifact:
    return Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_test",
            "action_type": action_type,
            "tool_calls": tool_calls or [],
            "response_text": response_text,
            "rationale": "test",
            "confidence": 1.0,
        },
        schema_ref="decision.v1",
    )


def test_act_subgraph_loads_and_compiles() -> None:
    specs = load_registry("act", "model_eye", "perceive", "agent_loop")
    assert "act" in specs
    assert "effect_dispatch" not in specs
    spec = specs["act"]
    assert {n.id for n in spec.nodes} == {"shape", "authorize", "execute", "observe"}
    project_edges = [e for e in spec.edges if e.kind == EdgeKind.PROJECT]
    assert len(project_edges) == 1
    assert project_edges[0].to_ref.spec_id == "model_eye"
    assert project_edges[0].to_ref.node_id == "see"
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "act"


def test_act_declares_decision_initial_port() -> None:
    specs = load_registry("act")
    assert "decision" in specs["act"].initial_ports()


def test_call_tool_allow_produces_ok_observation() -> None:
    from agent_lab.nodes.act.execute import plugin as execute_plugin
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    execute_plugin.configure_registry(registry)

    specs = load_registry("act", "model_eye")
    # Restrict allowlist still includes read_file (default in act.yaml).
    demo = str(Path(__file__).resolve())
    initial = {
        "decision": _decision(
            action_type="call_tool",
            tool_calls=[
                {
                    "call_id": "c1",
                    "name": "read_file",
                    "arguments": {"path": demo, "max_bytes": 64},
                }
            ],
        )
    }
    trace = run_graph(specs["act"], initial=initial, sub_registry=specs)
    obs = trace.final_artifacts.get("observation")
    assert obs is not None
    assert obs.schema_ref == "observation.v1"
    assert obs.content.get("status") == "ok"
    assert obs.content.get("tool") == "read_file"


def test_authorize_deny_skips_executor() -> None:
    specs = load_registry("act", "model_eye")
    # Patch SafeExecutor so any accidental call fails the test loudly.
    with patch("agent_lab.nodes.act.execute.plugin.SimpleSafeExecutor") as mock_exec:
        mock_exec.side_effect = AssertionError("execute must not run on deny")
        initial = {
            "decision": _decision(
                action_type="call_tool",
                tool_calls=[
                    {
                        "call_id": "c1",
                        "name": "not_allowed_tool",
                        "arguments": {},
                    }
                ],
            )
        }
        trace = run_graph(specs["act"], initial=initial, sub_registry=specs)

    obs = trace.final_artifacts["observation"]
    assert obs.content.get("status") == "denied"
    mock_exec.assert_not_called()


def test_respond_is_no_effect() -> None:
    specs = load_registry("act", "model_eye")
    with patch("agent_lab.nodes.act.execute.plugin.SimpleSafeExecutor") as mock_exec:
        mock_exec.side_effect = AssertionError("respond must not touch the world")
        initial = {
            "decision": _decision(
                action_type="respond",
                response_text="hello",
            )
        }
        trace = run_graph(specs["act"], initial=initial, sub_registry=specs)

    obs = trace.final_artifacts["observation"]
    assert obs.content.get("status") == "no_effect"
    assert obs.content.get("action_type") == "respond"
    mock_exec.assert_not_called()


def test_refuse_is_no_effect() -> None:
    specs = load_registry("act", "model_eye")
    initial = {"decision": _decision(action_type="refuse")}
    trace = run_graph(specs["act"], initial=initial, sub_registry=specs)
    obs = trace.final_artifacts["observation"]
    assert obs.content.get("status") == "no_effect"
    assert obs.content.get("action_type") == "refuse"


def test_shape_unit_extracts_first_tool_call() -> None:
    from agent_lab.nodes.act.shape.plugin import ActShape

    node = ActShape.__new__(ActShape)
    node.config = {"from": "decision", "to": "intent"}
    node.outs = ["intent"]
    out = node.execute(
        node,
        {
            "decision": _decision(
                action_type="call_tool",
                tool_calls=[
                    {"call_id": "a", "name": "bash", "arguments": {"cmd": "echo"}},
                    {"call_id": "b", "name": "read_file", "arguments": {}},
                ],
            )
        },
    )
    intent = out["intent"]
    assert intent.content["effect_kind"] == "call_tool"
    assert intent.content["tool"] == "bash"
    assert intent.content["args"] == {"cmd": "echo"}


def test_no_act_stub_factories_registered() -> None:
    # Importing nodes package registers factories.
    import agent_lab.nodes  # noqa: F401
    from agent_lab.nodes import NodeRegistry

    for stub in (
        "act__decision_to_intent",
        "act__intent_allow",
        "act__intent_dispatch",
        "act__receipt_to_text",
    ):
        assert stub not in NodeRegistry.known(), f"stub factory still registered: {stub}"
    for real in ("act.shape", "act.authorize", "act.execute", "act.observe"):
        assert real in NodeRegistry.known(), f"missing act factory: {real}"


def test_agent_loop_mounts_act_not_effect_dispatch() -> None:
    specs = load_registry(
        "perceive",
        "think",
        "act",
        "reflect",
        "remember",
        "model_eye",
        "agent_loop",
    )
    links = {link.sub_spec_id: link for link in specs["agent_loop"].sub_specs}
    assert "act" in links
    assert "effect_dispatch" not in links
    assert links["act"].input_map.get("in_decision") == "decision"
