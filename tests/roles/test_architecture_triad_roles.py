from pathlib import Path

import yaml

from lca.agent.role_library import FileRoleLibrary


def test_architecture_triad_role_cards_exist_and_valid():
    roles_dir = Path("roles/architecture")
    expected_roles = {"guanlan", "hengyue", "jingchuan"}

    for role_id in expected_roles:
        card_path = roles_dir / f"{role_id}.md"
        assert card_path.exists(), f"Role card missing: {card_path}"
        content = card_path.read_text(encoding="utf-8")
        assert content.startswith("---"), f"Role card must have YAML frontmatter: {card_path}"
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"Invalid frontmatter format: {card_path}"

        meta = yaml.safe_load(parts[1])
        assert "name" in meta
        assert meta["department"] == "architecture"
        assert "description" in meta
        assert "capabilities" in meta
        assert len(parts[2].strip()) > 100, f"Role card backstory/prompt too short: {card_path}"


def test_file_role_library_indexes_triad():
    library = FileRoleLibrary()
    triad_ids = {"architecture/guanlan", "architecture/hengyue", "architecture/jingchuan"}
    indexed_ids = {entry.role_id for entry in library.index()}
    assert triad_ids.issubset(indexed_ids), (
        f"Triad missing from role library: {triad_ids - indexed_ids}"
    )

    # 检验每一张卡片解析细节
    guanlan = library.get("architecture/guanlan")
    assert guanlan.title == "观澜"
    assert guanlan.department == "architecture"
    assert "边界" in guanlan.summary or "契约" in guanlan.summary

    hengyue = library.get("architecture/hengyue")
    assert hengyue.title == "衡岳"
    assert hengyue.department == "architecture"
    assert "不变量" in hengyue.summary or "状态" in hengyue.summary

    jingchuan = library.get("architecture/jingchuan")
    assert jingchuan.title == "镜川"
    assert jingchuan.department == "architecture"
    assert "审计" in jingchuan.summary or "反模式" in jingchuan.summary


def test_file_role_card_resolver_architecture_department():
    from lca.infrastructure.tools.assistant.role_card_resolver import (
        FileRoleCardResolver,
    )

    resolver = FileRoleCardResolver()
    depts = {d.department_id: d.label for d in resolver.list_departments()}
    assert "architecture" in depts
    assert depts["architecture"] == "系统架构"
