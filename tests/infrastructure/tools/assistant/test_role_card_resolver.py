"""FileRoleCardResolver integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.protocols.assistant.role_resolver import (
    RoleCardResolver,
    RoleNotFoundError,
)
from lca.infrastructure.tools.assistant.role_card_resolver import FileRoleCardResolver

_ROLES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "roles"


@pytest.mark.skipif(not _ROLES_DIR.is_dir(), reason="roles/ not present")
class TestFileRoleCardResolver:
    def test_implements_protocol(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        assert isinstance(resolver, RoleCardResolver)

    def test_resolve_known_role(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        available = resolver.list_available()
        assert len(available) > 100, f"expected 100+ roles, got {len(available)}"

        first_id = available[0]
        card = resolver.resolve(first_id)
        assert card.role_id == first_id
        assert card.title.strip()
        assert card.backstory.strip()

    def test_resolve_unknown_raises(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        with pytest.raises(RoleNotFoundError):
            resolver.resolve("nonexistent/fake-role")

    def test_list_available_sorted(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        ids = resolver.list_available()
        assert ids == tuple(sorted(ids))

    def test_engineering_role_backstory_has_content(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        ids = resolver.list_available()
        eng_ids = [rid for rid in ids if rid.startswith("engineering/")]
        assert len(eng_ids) > 10
        card = resolver.resolve(eng_ids[0])
        assert card.department == "engineering"
        assert len(card.backstory) > 50

    def test_list_departments_returns_summaries(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        departments = resolver.list_departments()
        assert len(departments) >= 15
        eng = next(d for d in departments if d.department_id == "engineering")
        assert eng.label == "工程技术"
        assert eng.count >= 30

    def test_list_by_department_returns_entries(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        entries = resolver.list_by_department("engineering")
        assert len(entries) >= 30
        assert all(e.department == "engineering" for e in entries)

    def test_list_by_unknown_department_returns_empty(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        entries = resolver.list_by_department("nonexistent")
        assert entries == ()

    def test_search_matches_title(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        results = resolver.search("架构")
        assert len(results) >= 3

    def test_search_no_match_returns_empty(self) -> None:
        resolver = FileRoleCardResolver(root=_ROLES_DIR)
        results = resolver.search("xyznonexistent")
        assert results == ()
