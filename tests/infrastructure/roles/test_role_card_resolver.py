"""Tests for ``FileRoleCardResolver``, the assistant-domain role-card adapter.

The resolver bridges ``FileRoleLibrary`` (now in infrastructure) to the
``RoleCardResolver`` protocol used by assistant creation and the REST API.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.infrastructure.roles.role_library import FileRoleLibrary
from lca.infrastructure.tools.assistant.role_card_resolver import FileRoleCardResolver

_CARD_TEMPLATE = """---
name: {name}
description: {desc}
emoji: 🧪
---

# {name}

{name} 的角色卡正文。
"""


def _write_card(root: Path, rel: str, name: str, desc: str) -> None:
    path = root / f"{rel}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_CARD_TEMPLATE.format(name=name, desc=desc), encoding="utf-8")


@pytest.fixture()
def roles_dir(tmp_path: Path) -> Path:
    _write_card(tmp_path, "product/pm", "产品经理", "需求分析与方案设计")
    _write_card(tmp_path, "product/designer", "产品设计师", "交互视觉设计")
    _write_card(tmp_path, "engineering/eng", "后端工程师", "服务端实现")
    return tmp_path


def test_resolve_returns_role_card(roles_dir: Path) -> None:
    resolver = FileRoleCardResolver(roles_dir)
    card = resolver.resolve("product/pm")
    assert card.title == "产品经理"
    assert card.department == "product"


def test_list_available_returns_sorted_ids(roles_dir: Path) -> None:
    resolver = FileRoleCardResolver(roles_dir)
    assert resolver.list_available() == (
        "engineering/eng",
        "product/designer",
        "product/pm",
    )


def test_list_departments_aggregates_counts(roles_dir: Path) -> None:
    resolver = FileRoleCardResolver(roles_dir)
    departments = resolver.list_departments()
    by_id = {d.department_id: d for d in departments}
    assert by_id["product"].count == 2
    assert by_id["engineering"].count == 1
    # Chinese labels are applied where known.
    assert by_id["product"].label == "产品"


def test_list_by_department_filters(roles_dir: Path) -> None:
    resolver = FileRoleCardResolver(roles_dir)
    product_roles = resolver.list_by_department("product")
    assert [e.role_id for e in product_roles] == ["product/designer", "product/pm"]
    assert resolver.list_by_department("finance") == ()


def test_search_matches_title_and_summary(roles_dir: Path) -> None:
    resolver = FileRoleCardResolver(roles_dir)
    by_title = resolver.search("设计师")
    assert [e.role_id for e in by_title] == ["product/designer"]
    by_summary = resolver.search("服务端")
    assert [e.role_id for e in by_summary] == ["engineering/eng"]


def test_resolver_delegates_to_file_role_library(roles_dir: Path) -> None:
    resolver = FileRoleCardResolver(roles_dir)
    library = FileRoleLibrary(roles_dir)
    assert resolver.list_available() == tuple(e.role_id for e in library.index())
