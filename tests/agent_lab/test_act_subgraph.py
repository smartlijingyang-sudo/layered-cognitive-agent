"""Act sub-graph: shape → authorize → execute(SimpleBody.act) → observe.

Covers:
  - act.yaml loads + compiles (with project edge into model_eye)
  - use_tool → PipelineSafeExecutor mints CommandEnvelope under plan_ref
  - DecisionMade lands on shared Session when publish is bound
  - authorize deny → Body never called
  - respond / refuse → Body; ApprovalPendingError → waiting_input
  - delegate via InternalTransport echo
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


def test_use_tool_allow_produces_ok_observation() -> None:
    from agent_lab.nodes.act.execute import plugin as execute_plugin
    from agent_lab.nodes.session_log._sink import get_session
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    execute_plugin.configure_registry(registry)

    specs = load_registry("act", "model_eye")
    demo = str(Path(__file__).resolve())
    before = get_session().event_count
    initial = {
        "decision": _decision(
            action_type="use_tool",
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
    assert obs.content.get("success") is True
    # Receipt/observation boundary must be JSON-plain (no live Enums) and
    # Artifact digests must actually hash (Pydantic validate_default).
    assert obs.digest, "observation artifact digest must be non-empty"
    assert obs.short_id()
    extra = obs.content.get("extra") or {}
    result_kind = extra.get("result_kind")
    assert result_kind is None or isinstance(result_kind, str), (
        f"result_kind must be a plain str at the receipt boundary, got {result_kind!r}"
    )
    # PipelineSafeExecutor mints CommandEnvelope under plan_ref_scope.
    envelope = obs.content.get("command_envelope") or extra.get("command_envelope")
    assert envelope is not None
    assert envelope.get("plan_ref") == "agent_lab_act"
    # Shared Session received DecisionMade (and tool journal facts).
    assert get_session().event_count > before
    types = {get_session().event_at(i).type for i in range(get_session().event_count)}
    assert "decision.made.v1" in types


def test_call_tool_alias_maps_to_use_tool() -> None:
    from agent_lab.nodes.act.execute import plugin as execute_plugin
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    execute_plugin.configure_registry(registry)

    specs = load_registry("act", "model_eye")
    demo = str(Path(__file__).resolve())
    initial = {
        "decision": _decision(
            action_type="call_tool",
            tool_calls=[
                {
                    "call_id": "c1",
                    "name": "read_file",
                    "arguments": {"path": demo, "max_bytes": 32},
                }
            ],
        )
    }
    trace = run_graph(specs["act"], initial=initial, sub_registry=specs)
    assert trace.final_artifacts["observation"].content.get("status") == "ok"


def test_authorize_deny_skips_body() -> None:
    specs = load_registry("act", "model_eye")
    with patch("agent_lab.nodes.act.execute.body.run_body_act") as mock_body:
        mock_body.side_effect = AssertionError("Body must not run on deny")
        initial = {
            "decision": _decision(
                action_type="use_tool",
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
    mock_body.assert_not_called()


def test_respond_goes_through_body() -> None:
    from agent_lab.nodes.act.execute import plugin as execute_plugin
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    execute_plugin.configure_registry(registry)

    specs = load_registry("act", "model_eye")
    initial = {
        "decision": _decision(
            action_type="respond",
            response_text="hello",
        )
    }
    trace = run_graph(specs["act"], initial=initial, sub_registry=specs)
    obs = trace.final_artifacts["observation"]
    assert obs.content.get("status") == "ok"
    assert obs.content.get("action_type") == "respond"
    assert obs.content.get("result") == "hello"
    assert obs.content.get("success") is True


def test_refuse_maps_to_respond_via_body() -> None:
    from agent_lab.nodes.act.execute import plugin as execute_plugin
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    execute_plugin.configure_registry(registry)

    specs = load_registry("act", "model_eye")
    initial = {"decision": _decision(action_type="refuse", response_text="cannot help")}
    trace = run_graph(specs["act"], initial=initial, sub_registry=specs)
    obs = trace.final_artifacts["observation"]
    assert obs.content.get("status") == "ok"
    assert obs.content.get("action_type") == "respond"
    assert obs.content.get("result") == "cannot help"
    assert obs.content.get("degraded_from") == "refuse"


def test_shape_canonicalizes_call_tool_to_use_tool() -> None:
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
    assert intent.content["effect_kind"] == "use_tool"
    assert intent.content["action_type"] == "use_tool"
    assert intent.content["tool"] == "bash"
    assert intent.content["args"] == {"cmd": "echo"}
    assert len(intent.content["tool_calls"]) == 2


def test_no_act_stub_factories_registered() -> None:
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


def test_approval_pending_becomes_waiting_input() -> None:
    from agent_lab.nodes.act.execute import plugin as execute_plugin
    from agent_lab.tools.registry import ToolRegistry
    from lca.contracts.models.core.execution.result import ApprovalPendingError

    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    execute_plugin.configure_registry(registry)

    specs = load_registry("act", "model_eye")
    with patch(
        "agent_lab.nodes.act.execute.body.run_body_act",
        side_effect=ApprovalPendingError({"id": "apr_1", "tool": "askUserQuestion"}),
    ):
        initial = {
            "decision": _decision(
                action_type="use_tool",
                tool_calls=[
                    {
                        "call_id": "c1",
                        "name": "read_file",
                        "arguments": {"path": str(REPO_ROOT / "README.md")},
                    }
                ],
            )
        }
        trace = run_graph(specs["act"], initial=initial, sub_registry=specs)

    obs = trace.final_artifacts["observation"]
    assert obs.content.get("status") == "waiting_input"
    assert obs.content.get("approval_request", {}).get("id") == "apr_1"


def test_delegate_uses_internal_echo_transport() -> None:
    from agent_lab.nodes.act.execute import plugin as execute_plugin
    from agent_lab.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.load_from_yaml(REPO_ROOT / "agent_lab" / "tools" / "registry.yaml")
    execute_plugin.configure_registry(registry)

    specs = load_registry("act", "model_eye")
    initial = {
        "decision": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "decision_id": "dec_del",
                "action_type": "delegate",
                "tool_calls": [],
                "delegations": [
                    {
                        "subtask": "ping",
                        "target_role": "lab_echo",
                        "protocol": "internal",
                        "timeout_s": 2,
                    }
                ],
                "rationale": "team",
                "confidence": 1.0,
            },
            schema_ref="decision.v1",
        )
    }
    trace = run_graph(specs["act"], initial=initial, sub_registry=specs)
    obs = trace.final_artifacts["observation"]
    assert obs.content.get("status") == "ok"
    assert obs.content.get("action_type") == "delegate"
    assert obs.content.get("result") == "echo:ping"
