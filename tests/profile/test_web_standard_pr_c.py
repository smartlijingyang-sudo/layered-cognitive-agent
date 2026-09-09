"""ADR-0214 §6 PR-C: ``profiles/web-standard.yaml`` 三件套字段契约。

锁定:
1. ``perceive.main.precondition`` == ``perceive.has_minimum_context``
2. ``perceive.main.terminal_predicate`` == ``perceive.context_complete``
3. 既有 6 个 phase 节点结构不破(id / phase / max_visits 与历史一致)。
4. YAML 解析通过 Pydantic Config 严格校验(extra=forbid)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.harness.composition.plan_compiler import compile_plan
from lca.harness.profile.resolve.resolve import resolve_profile

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "profiles" / "web-standard.yaml"


@pytest.fixture(scope="module")
def compiled_plan():
    return compile_plan(resolve_profile(str(PROFILE_PATH)))


@pytest.fixture(scope="module")
def perceive_node(compiled_plan):
    """Return the ``perceive.main`` PhaseNode from the compiled plan."""
    assert compiled_plan.phase_graph is not None
    nodes = {node.id: node for node in compiled_plan.phase_graph.nodes}
    assert "perceive.main" in nodes, "perceive.main missing from web-standard phase graph"
    return nodes["perceive.main"]


def test_perceive_node_has_precondition_field(perceive_node) -> None:
    """``perceive.main.precondition`` 在编译后等于声明的 callable 名字。"""
    assert perceive_node.precondition == "perceive.has_minimum_context"


def test_perceive_node_has_terminal_predicate_field(perceive_node) -> None:
    """``perceive.main.terminal_predicate`` 在编译后等于声明的 callable 名字。"""
    assert perceive_node.terminal_predicate == "perceive.context_complete"


def test_perceive_node_referenced_predicates_are_registered(perceive_node) -> None:
    """YAML 中声明的 predicate 名字必须在 harness 注册表里 resolve 得到。"""
    from lca.harness.graph import predicates

    assert predicates.resolve(perceive_node.precondition) is not None  # type: ignore[arg-type]
    assert predicates.resolve(perceive_node.terminal_predicate) is not None  # type: ignore[arg-type]


def test_web_standard_has_six_phase_nodes(compiled_plan) -> None:
    """web-standard 仍持有 6 个 phase 节点(PG-007 三件套不破坏既有结构)。"""
    assert compiled_plan.phase_graph is not None
    assert len(compiled_plan.phase_graph.nodes) == 6


def test_web_standard_six_phase_node_ids_unchanged(compiled_plan) -> None:
    """6 个节点 id 与 patch 前一致(锁回归)。"""
    assert compiled_plan.phase_graph is not None
    node_ids = sorted(node.id for node in compiled_plan.phase_graph.nodes)
    assert node_ids == [
        "act.main",
        "perceive.main",
        "reflect.main",
        "remember.main",
        "stop.main",
        "think.main",
    ]


def test_non_perceive_nodes_have_no_predicate_fields(compiled_plan) -> None:
    """think/act/reflect/remember/stop 节点不强行加 predicate(范围受控)。

    注释 PR-C 仅在 perceive.main 上扩,避免 PR 范围爆炸。
    """
    assert compiled_plan.phase_graph is not None
    for node in compiled_plan.phase_graph.nodes:
        if node.id == "perceive.main":
            continue
        assert node.precondition is None, f"{node.id}.precondition must stay None"
        assert node.terminal_predicate is None, f"{node.id}.terminal_predicate must stay None"


def test_perceive_node_max_visits_unchanged(perceive_node) -> None:
    """``perceive.main.max_visits`` 仍是 8(锁 PG-007 兜底语义)。"""
    assert perceive_node.max_visits == 8


def test_perceive_node_terminal_flag_unchanged(compiled_plan) -> None:
    """``perceive.main`` 仍是 entry, ``stop.main`` 仍是 terminal(锁拓扑)。"""
    assert compiled_plan.phase_graph is not None
    nodes = {node.id: node for node in compiled_plan.phase_graph.nodes}
    assert nodes["perceive.main"].terminal is False
    assert nodes["stop.main"].terminal is True
    assert compiled_plan.phase_graph.entry == "perceive.main"


def test_raw_yaml_contains_three_kit_fields() -> None:
    """YAML 源文本含 ``precondition`` / ``terminal_predicate`` 字段(防退化)。"""
    import yaml

    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    patch = raw.get("patch") or []
    topology_patch = next(
        (p for p in patch if isinstance(p, dict) and p.get("id") == "phase.topology.standard"),
        None,
    )
    assert topology_patch is not None, "phase.topology.standard patch missing"
    nodes = topology_patch["config"]["nodes"]
    perceive = next(n for n in nodes if n["id"] == "perceive.main")
    assert perceive.get("precondition") == "perceive.has_minimum_context"
    assert perceive.get("terminal_predicate") == "perceive.context_complete"


def test_predicates_module_exports_required_names() -> None:
    """predicates 模块 export 包含 PR-C 用到的全部名字。"""
    from lca.harness.graph.predicates import (
        Predicate,
        known_predicates,
        perceive_context_complete,
        perceive_has_minimum_context,
        register,
        resolve,
    )

    assert Predicate is not None
    assert callable(register)
    assert callable(resolve)
    assert callable(known_predicates)
    assert callable(perceive_has_minimum_context)
    assert callable(perceive_context_complete)
