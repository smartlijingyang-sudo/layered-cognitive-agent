"""Skeleton owns graph mechanics only — business lives in plugins.

Acceptance:
  - compile.py / runner.py do not import lca and do not hardcode ControlSlot
    wiring or decision/observation/reflection schema routing.
  - control slot insertion happens only when a control_slots plugin is present.
  - semantic schema→hook routing happens via semantic_router plugin.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SKELETON_FILES = (
    REPO_ROOT / "agent_lab" / "graph" / "compile.py",
    REPO_ROOT / "agent_lab" / "graph" / "spec.py",
    REPO_ROOT / "agent_lab" / "graph" / "validate.py",
    REPO_ROOT / "agent_lab" / "runtime" / "runner.py",
)

_FORBIDDEN_SUBSTRINGS = (
    "lca.contracts",
    "ControlSlot",
    "SLOT_PHASE_OWNER",
    "_CONTROL_SLOT_WIRING",
    "auto_insert_control_slots",
    "decision.v1",
    "observation.v1",
    "reflection.v1",
)


def test_skeleton_source_has_no_business_coupling() -> None:
    offenders: list[str] = []
    for path in _SKELETON_FILES:
        text = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_SUBSTRINGS:
            if needle in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: contains {needle!r}")
    assert not offenders, "skeleton leaked business: " + "; ".join(offenders)


def test_skeleton_modules_do_not_import_lca() -> None:
    for path in _SKELETON_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("lca"), path
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("lca"), path


def test_compile_without_control_slots_plugin_does_not_insert() -> None:
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.graphs import load_registry

    specs = load_registry(
        "perceive",
        "think",
        "reflect",
        "remember",
        "toolbox",
        "event_log",
        "model_eye",
        "act",
        "agent_loop",
    )
    # Strip business plugins; keep only observer so compile still resolves.
    stripped = [
        p for p in specs["agent_loop"].plugins if p.kind not in {"control_slots", "semantic_router"}
    ]
    specs["agent_loop"] = specs["agent_loop"].model_copy(update={"plugins": stripped})
    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)
    inserted = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    assert "think_guard" not in inserted
    assert "act_authorize" not in inserted
    assert len(bundle.subgraph_calls) == 5


def test_control_slots_plugin_inserts_on_before_compile() -> None:
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.graphs import load_registry

    specs = load_registry(
        "perceive",
        "think",
        "reflect",
        "remember",
        "toolbox",
        "event_log",
        "model_eye",
        "act",
        "agent_loop",
    )
    kinds = {p.kind for p in specs["agent_loop"].plugins}
    assert "control_slots" in kinds, "agent_loop must declare control_slots plugin"

    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)
    inserted = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    expected = {
        "perceive_context",
        "think_guard",
        "remember_admit",
        "stop_decide",
        "observe_checkpoint",
    }
    for name in expected:
        assert name in inserted, f"control_slots plugin missed {name}"
    for removed in (
        "act_authorize",
        "act_budget",
        "act_constrain",
        "act_execute",
        "act_safe_boundary",
    ):
        assert removed not in inserted, f"act control stub {removed} must not auto-insert"
    assert len(bundle.subgraph_calls) >= 5 + len(expected)


def test_semantic_router_plugin_fans_out_on_schema_ref() -> None:
    from agent_lab.plugins import ParseDecisionPlugin, SemanticRouterPlugin, fanout_hooks
    from agent_lab.plugins.base import HookContext, HookEvent
    from agent_lab.primitives.artifact import Artifact, ArtifactKind

    router = SemanticRouterPlugin(
        name="router",
        kind="semantic_router",
        config={
            "schema_hooks": {
                "decision.v1": "on_decision",
            }
        },
    )
    parser = ParseDecisionPlugin(
        name="parser",
        kind="parse_decision",
        binds=(),  # match all; semantic event still filters by method
    )
    artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_x",
            "action_type": "respond",
            "response_text": "",
            "tool_calls": [{"name": "bash", "arguments": {}}],
        },
        schema_ref="decision.v1",
    )
    ctx = HookContext(
        event=HookEvent.AFTER_NODE_EXECUTE,
        node_id="parse",
        payload={
            "outputs": {"decision": artifact},
            "plugins": [router, parser],
        },
    )
    new_ctx = fanout_hooks([router, parser], HookEvent.AFTER_NODE_EXECUTE, ctx)
    out = new_ctx.payload["outputs"]["decision"]
    assert out.content["action_type"] == "call_tool"


def test_compile_api_has_no_auto_insert_kwarg() -> None:
    import importlib
    import inspect

    # Prefer importlib: ``agent_lab.graph.compile`` is also re-exported as a
    # function attribute on the package, which shadows the submodule name.
    compile_mod = importlib.import_module("agent_lab.graph.compile")
    sig = inspect.signature(compile_mod.compile)
    assert "auto_insert_control_slots" not in sig.parameters
