"""基础设施测试：开放实体知识图谱与 File-as-SSOT 存储适配器 (Task 2)。"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.entities.store import EntityGraphStore


def test_entity_graph_open_taxonomy_and_file_as_ssot(tmp_path: Path) -> None:
    store = EntityGraphStore(tmp_path)

    # 1. Agent 自主创建全新领域目录 (如 health, projects)，无需硬编码枚举
    store.write_entity(
        domain="health",
        slug="medication",
        content="每日早晨服用维生素D与辅酶Q10",
        tags=("health", "daily"),
        aliases=("维D", "补剂"),
    )

    entity_file = tmp_path / "memory/entities/health/medication.md"
    assert entity_file.is_file()
    text = entity_file.read_text(encoding="utf-8")
    assert "每日早晨服用维生素D" in text
    assert "tags: health, daily" in text

    # 2. 检查 GRAPH.md 微索引自动生成
    graph_file = tmp_path / "memory/entities/GRAPH.md"
    assert graph_file.is_file()
    graph_md = graph_file.read_text(encoding="utf-8")
    assert "health/medication" in graph_md


def test_entity_graph_derived_index_rebuild_and_fts_search(tmp_path: Path) -> None:
    store = EntityGraphStore(tmp_path)
    store.write_entity(
        domain="health",
        slug="medication",
        content="每日早晨服用维生素D与辅酶Q10",
        tags=("health", "daily"),
        aliases=("维D",),
    )
    store.write_entity(
        domain="people",
        slug="xiaowen",
        content="小杰女朋友的姐姐，在深圳外企工作",
        tags=("family", "relative"),
        aliases=("晓雯",),
        relations={"xiaojie": "sister_of_girlfriend"},
    )

    # 派生检索
    results = store.search_entities("维生素")
    assert len(results) == 1
    assert results[0].domain == "health"
    assert results[0].slug == "medication"

    # 删除派生索引并重建（验证纯派生性与秒级恢复）
    db_file = tmp_path / "index/memory.sqlite3"
    assert db_file.is_file()
    db_file.unlink()
    assert not db_file.exists()

    store.rebuild_derived_index()
    assert db_file.is_file()

    results_after = store.search_entities("深圳")
    assert len(results_after) == 1
    assert results_after[0].slug == "xiaowen"


def test_entity_graph_budget_and_gc(tmp_path: Path) -> None:
    # 设置活跃上限为 5 个
    store = EntityGraphStore(tmp_path, max_active_entities=5, max_graph_entries=3)

    for i in range(10):
        store.write_entity(
            domain="projects",
            slug=f"proj_{i}",
            content=f"这是第 {i} 个研发项目文档",
            tags=("work",),
        )

    # 验证活跃目录只有 5 个
    active_files = list((tmp_path / "memory/entities/projects").glob("*.md"))
    assert len(active_files) == 5

    # 验证旧实体自动沉降至 archives/entities/
    archived_file = tmp_path / "memory/archives/entities/projects/proj_0.md"
    assert archived_file.is_file()

    # 验证 GRAPH.md 只保留 Top 3 条（严格预算受控）
    graph_md = (tmp_path / "memory/entities/GRAPH.md").read_text(encoding="utf-8")
    lines = [line for line in graph_md.splitlines() if line.startswith("- ")]
    assert len(lines) <= 3

    # 验证派生索引包含归档实体（深层仍可被检索）
    results = store.search_entities("第 0 个研发项目")
    assert len(results) == 1
    assert results[0].slug == "proj_0"


def test_entity_graph_multi_hop_relations(tmp_path: Path) -> None:
    store = EntityGraphStore(tmp_path)
    # 我 -> 表弟小杰
    store.write_entity(
        domain="people",
        slug="me",
        content="本人",
        relations={"xiaojie": "cousin"},
    )
    # 小杰 -> 晓雯 (表弟女朋友的姐姐)
    store.write_entity(
        domain="people",
        slug="xiaojie",
        content="在深圳做程序员的表弟",
        relations={"xiaowen": "sister_of_girlfriend"},
    )
    # 晓雯
    store.write_entity(
        domain="people",
        slug="xiaowen",
        content="晓雯",
    )

    # 2 跳关系遍历
    chain = store.get_relation_path("me", "xiaowen", max_hops=2)
    assert chain is not None
    assert chain == [("me", "xiaojie", "cousin"), ("xiaojie", "xiaowen", "sister_of_girlfriend")]
