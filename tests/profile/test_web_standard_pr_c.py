"""ADR-0214 §6 PR-C: ``profiles/web-standard.yaml`` v1 拓扑契约(已退役、现锁住退役状态)。

历史:本文件曾锁定 v1 契约 —— ``phase.topology.standard`` patch 给
``perceive.main`` 加 ``precondition``/``terminal_predicate``、6 个 phase 节点
结构、``compiled_plan.phase_graph`` 的 entry/terminal 拓扑、
``lca.harness.graph.predicates`` 的注册表。

退役(ADR-0221 P3):outer-plan 切流 + topology-provider 退役后 ——
- profile 不再携带 ``phase.topology.standard`` patch(见
  ``profiles/web-standard.yaml`` 注释);
- v2 编译器 ``compile_plan`` 明确输出 ``phase_graph=None``
  (``lca_kernel/plan/plan_compile.py`` 模块 docstring);
- ``lca.harness.graph`` 整包(含 predicates)已删除。

PR-C 契约的 v2 形态落在 ``tests/contracts/test_phase_node_pr_c.py``
(typed-port 切流:所有 edge ``when:`` 谓词 typed)。本文件只锁住
"v1 表面已退役"的事实(防僵尸回归)+对 v2 表面的
entry/terminal 拓扑锁定(继承原文件"锁拓扑"的意图)。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lca_kernel.plan.plan_compile import compile_plan
from lca.harness.profile.resolve.resolve import resolve_profile

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "profiles" / "web-standard.yaml"


@pytest.fixture(scope="module")
def compiled_plan():
    return compile_plan(resolve_profile(str(PROFILE_PATH)))


@pytest.fixture(scope="module")
def v2_nodes(compiled_plan):
    """v2 graph_spec 节点字典(id -> node dict)。"""
    nodes = (compiled_plan.graph_spec or {}).get("nodes") or []
    return {n["id"]: n for n in nodes if isinstance(n, dict)}


def test_v2_plan_carries_no_phase_graph(compiled_plan) -> None:
    """v2 编译产物不再携带 declarative phase graph(ADR-0221 P3 故意设计):
    CompiledRunPlan 已不内含 phase_graph 字段(比模块 docstring 写的
    "phase_graph=None" 更彻底——docstring 已过期,记 arch 补)。"""
    with pytest.raises(AttributeError):
        compiled_plan.phase_graph


def test_profile_carries_no_legacy_topology_patch() -> None:
    """profile 不再携带已退役的 ``phase.topology.standard`` patch(拓扑已切到 bundles/outer)。"""
    raw = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    patch = raw.get("patch") or []
    ids = [p.get("id") for p in patch if isinstance(p, dict)]
    assert "phase.topology.standard" not in ids


def test_v1_predicates_module_retired() -> None:
    """v1 的 ``lca.harness.graph.predicates`` 已删除(连父包一起没了),不应僵尸复活。"""
    with pytest.raises(ImportError):
        import lca.harness.graph.predicates  # noqa: F401


def test_v2_entry_still_perceive(v2_nodes) -> None:
    """v2 表面:``perceive.main`` 仍是 entry(原 test_perceive_node_terminal_flag_unchanged 的意图)。"""
    assert v2_nodes["perceive.main"].get("entry") is True


def test_v2_terminal_node_flag(v2_nodes) -> None:
    """v2 表面:terminal 节点仍带 terminal 标记(现为 ``terminal.commit``,stop.main 已退役)。"""
    assert v2_nodes["terminal.commit"].get("terminal") is True
