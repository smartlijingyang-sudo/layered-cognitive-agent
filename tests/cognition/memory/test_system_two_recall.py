"""认知层测试：极简冷启动装配与 System 2 内部多跳追忆引擎 (Task 4)。"""

from __future__ import annotations

from pathlib import Path

from lca.cognition.memory.recall import (
    InternalRecallTool,
    RecallResult,
    SystemTwoRecallEngine,
)
from lca.infrastructure.memory.entities.store import EntityGraphStore


def _setup_demo_graph(tmp_path: Path) -> EntityGraphStore:
    store = EntityGraphStore(tmp_path)
    store.write_entity(
        domain="people",
        slug="me",
        content="当前用户本人，软件系统架构师",
        relations={"xiaojie": "cousin"},
    )
    store.write_entity(
        domain="people",
        slug="xiaojie",
        content="表弟小杰，在深圳做程序员",
        tags=("family", "cousin"),
        aliases=("表弟",),
        relations={"xiaowen": "sister_of_girlfriend"},
    )
    store.write_entity(
        domain="people",
        slug="xiaowen",
        content="晓雯，小杰女朋友的姐姐，在外企做人事",
        tags=("relative", "indirect"),
        aliases=("晓雯姐",),
    )
    return store


def test_system_two_recall_multi_hop_traversal(tmp_path: Path) -> None:
    store = _setup_demo_graph(tmp_path)
    engine = SystemTwoRecallEngine(store)

    # 追忆晓雯及与本人的关系（2跳扩散）
    res: RecallResult = engine.recall(query="晓雯 人际关系", start_slug="me", max_hops=2)

    assert res.has_recalled is True
    assert res.hops_count <= 2
    assert len(res.relation_chains) >= 1
    # 路径验证：me -> xiaojie (cousin) -> xiaowen (sister_of_girlfriend)
    assert res.relation_chains[0] == (
        ("me", "xiaojie", "cousin"),
        ("xiaojie", "xiaowen", "sister_of_girlfriend"),
    )
    # 实体内容召回
    assert any("小杰女朋友的姐姐" in claim for claim in res.recalled_claims)


def test_system_two_recall_honest_no_hallucination_on_missing(tmp_path: Path) -> None:
    store = _setup_demo_graph(tmp_path)
    engine = SystemTwoRecallEngine(store)

    # 检索完全不存在的虚构信息
    res: RecallResult = engine.recall(query="火星殖民地密码箱钥匙", max_hops=2)

    assert res.has_recalled is False
    assert res.hops_count == 0
    assert len(res.recalled_claims) == 0
    assert "未检索到" in res.uncertainty_note


def test_internal_recall_tool_call(tmp_path: Path) -> None:
    store = _setup_demo_graph(tmp_path)
    engine = SystemTwoRecallEngine(store)
    tool = InternalRecallTool(engine)

    assert tool.name == "internal_recall"

    # 执行工具调用
    output = tool.run(query="深圳表弟", max_hops=2)
    assert output["has_recalled"] is True
    assert "小杰" in str(output["recalled_claims"])


def test_cold_start_horizon_budget_under_500_tokens(tmp_path: Path) -> None:
    store = _setup_demo_graph(tmp_path)
    graph_index = store.get_active_graph_index()

    # GRAPH.md 应当非常紧凑 (< 500 字符，远低于 100 Token)
    assert len(graph_index) < 500
    assert "people/xiaojie" in graph_index
