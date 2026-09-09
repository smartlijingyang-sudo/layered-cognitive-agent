"""Skeleton owns graph mechanics only — business lives in plugins.

Acceptance:
  - compile.py / runner.py do not import lca.contracts and do not hardcode
    ControlSlot wiring or decision/observation/reflection schema routing.
  - control mounts are parent-YAML sibling graph.call hosts, not a plugin insert.
  - observation hooks must not rewrite worker outputs (N6); semantic_router gone.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

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


_ALLOWED_LCA_PREFIXES = (
    "lca.plugins.lab.internal.hooks",
    "lca.plugins.lab.internal.loader",
)


def test_skeleton_modules_do_not_import_lca() -> None:
    """Skeleton may only touch the PR-A.3 hook/loader seam — not lca.contracts."""

    def _forbidden(mod: str) -> bool:
        if not mod.startswith("lca"):
            return False
        return not any(mod == p or mod.startswith(p + ".") for p in _ALLOWED_LCA_PREFIXES)

    for path in _SKELETON_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not _forbidden(alias.name), path
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not _forbidden(mod), path


def test_compile_without_control_slots_plugin_does_not_insert() -> None:
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.graphs.loader import load_closure

    specs = load_closure("agent_loop")
    stripped = [p for p in specs["agent_loop"].plugins if p.kind != "control_slots"]
    specs["agent_loop"] = specs["agent_loop"].model_copy(update={"plugins": stripped})
    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)
    calls = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    assert "stop_decide" in calls
    assert "think_guard" in calls
    by_host: dict[str, list[str]] = {}
    for x in bundle.subgraph_calls:
        by_host.setdefault(x["node_id"], []).append(x["sub_spec_id"])
    assert by_host["remember"] == ["remember"]
    assert by_host["stop_decide"] == ["stop_decide"]
    assert "act_authorize" not in calls
    expected = {
        "perceive",
        "think",
        "act",
        "reflect",
        "remember",
        "perceive_context",
        "think_guard",
        "remember_admit",
        "stop_decide",
        "stop_focus",
    }
    assert calls == expected


def test_control_slots_plugin_inserts_on_before_compile() -> None:
    """Control hosts are YAML siblings; stripping the retired plugin keeps them."""
    from agent_lab.graph.compile import compile as compile_spec
    from agent_lab.graphs.loader import load_closure

    specs = load_closure("agent_loop")
    kinds = {p.kind for p in specs["agent_loop"].plugins}
    assert "control_slots" not in kinds

    bundle = compile_spec(specs["agent_loop"], sub_registry=specs)
    inserted = {x["sub_spec_id"] for x in bundle.subgraph_calls}
    expected = {
        "perceive_context",
        "think_guard",
        "remember_admit",
        "stop_decide",
        "stop_focus",
    }
    for name in expected:
        assert name in inserted, f"agent_loop yaml missed sibling host {name}"
    for removed in (
        "act_authorize",
        "act_budget",
        "act_constrain",
        "act_execute",
        "act_safe_boundary",
        "observe_checkpoint",
        "observe_wildcard",
    ):
        assert removed not in inserted, f"{removed} must not auto-insert"


def test_semantic_router_plugin_fans_out_on_schema_ref() -> None:
    """Inverted (N6): semantic_router rewrite path is gone."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("agent_lab.plugins.semantic_router")

    import agent_lab.plugins as pl

    assert "SemanticRouterPlugin" not in pl.__all__
    assert not hasattr(pl, "SemanticRouterPlugin")


def test_compile_api_has_no_auto_insert_kwarg() -> None:
    import inspect

    compile_mod = importlib.import_module("agent_lab.graph.compile")
    sig = inspect.signature(compile_mod.compile)
    assert "auto_insert_control_slots" not in sig.parameters
