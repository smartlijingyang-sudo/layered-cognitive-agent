"""RA-075: one frontmatter parser yields the complete dict (incl. list values).

Regression pins:
- block scalar containing a 'references:' line (+ '- ' items) is not mis-parsed
- install_package calls the parser once; fail-loud on missing references stays
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.memory.operational_skills import SkillContractError
from lca.infrastructure.skills.disk.store import DiskSkillPackageStore
from lca.infrastructure.skills.frontmatter.frontmatter import (
    parse_references_field,
    skill_title,
    split_frontmatter,
)
from lca.infrastructure.skills.settings.settings import SkillSettings


def test_inline_list_value() -> None:
    meta, body = split_frontmatter("---\nname: x\nreferences: [a.md, b.md]\n---\nbody\n")
    assert meta["references"] == ["a.md", "b.md"]
    assert body == "body"


def test_multiline_list_value() -> None:
    text = "---\nname: x\nreferences:\n  - a.md\n  - b.md\ndescription: d\n---\nbody\n"
    meta, _ = split_frontmatter(text)
    assert meta["references"] == ["a.md", "b.md"]
    assert meta["description"] == "d"


def test_empty_inline_list() -> None:
    meta, _ = split_frontmatter("---\nname: x\nreferences: []\n---\nbody\n")
    assert meta["references"] == []


def test_empty_value_without_items_stays_empty_string() -> None:
    # 旧行为: 空值 key 进 dict 为 "";fail-loud 只看 key 是否存在
    meta, _ = split_frontmatter("---\nname: x\nreferences:\n---\nbody\n")
    assert meta["references"] == ""


def test_no_frontmatter() -> None:
    meta, body = split_frontmatter("just body")
    assert meta == {}
    assert body == "just body"


def test_block_scalar_containing_references_line_is_not_misparsed() -> None:
    # 回归 pin: block scalar 体内的 "references:" + "- fake.md" 行
    # 必须被当作 description 的一部分,不得污染真正的 references 字段。
    # 旧的 parse_references_field 会逐行扫描 raw 文本,把 fake.md 捡出来。
    text = (
        "---\n"
        "name: trap\n"
        "description: |\n"
        "  see below\n"
        "  references:\n"
        "    - fake.md\n"
        "references:\n"
        "  - real.md\n"
        "---\n"
        "body\n"
    )
    meta, _ = split_frontmatter(text)
    assert meta["description"] == "see below\nreferences:\n  - fake.md"
    assert meta["references"] == ["real.md"]
    assert parse_references_field(text) == ["real.md"]


def test_parse_references_field_wrapper_keeps_old_contract() -> None:
    assert parse_references_field("---\nname: x\nreferences: [a.md]\n---\nb") == ["a.md"]
    assert parse_references_field("---\nname: x\nreferences:\n  - a.md\n---\nb") == ["a.md"]
    assert parse_references_field("---\nname: x\nreferences: []\n---\nb") == []
    assert parse_references_field("---\nname: x\n---\nb") == []
    # 标量写法沿用旧行为:视为未声明
    assert parse_references_field("---\nname: x\nreferences: a.md\n---\nb") == []


def test_skill_title_with_list_name_falls_back() -> None:
    assert skill_title({"name": ["a", "b"]}, "fb") == "fb"
    assert skill_title({"name": "n"}, "fb") == "n"
    assert skill_title({}, "fb") == "fb"


def test_install_package_single_parse_keeps_fail_loud(tmp_path: Path) -> None:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "root"))
    with pytest.raises(SkillContractError):
        store.install_package(
            skill_id="no-refs",
            skill_md_text="---\nname: no-refs\ndescription: d\n---\nbody",
            resource_files={},
            source_url="u",
        )


def test_install_package_accepts_declared_references(tmp_path: Path) -> None:
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "root"))
    package = store.install_package(
        skill_id="with-refs",
        skill_md_text="---\nname: with-refs\ndescription: d\nreferences: [resources/r.md]\n---\nbody",
        resource_files={"resources/r.md": b"x"},
        source_url="u",
    )
    assert package.skill_id == "with-refs"
