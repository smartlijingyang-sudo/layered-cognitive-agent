"""RoleCardResolver protocol tests."""

from __future__ import annotations

import pytest

from lca.contracts.protocols.assistant.role_resolver import (
    DepartmentSummary,
    RoleCard,
    RoleCardResolver,
    RoleNotFoundError,
)


class _StubResolver:
    """Test double: resolves two hardcoded role_ids."""

    _CARDS = {
        "engineering/architect": RoleCard(
            role_id="engineering/architect",
            title="软件架构师",
            department="engineering",
            summary="系统设计专家",
            backstory="# 软件架构师\n\n你是系统架构专家。",
            emoji="🏛️",
        ),
        "design/ux": RoleCard(
            role_id="design/ux",
            title="UX 设计师",
            department="design",
            summary="用户体验设计",
            backstory="# UX 设计师\n\n你关注用户体验。",
            emoji="🎨",
        ),
    }

    def resolve(self, role_id: str) -> RoleCard:
        if role_id not in self._CARDS:
            raise RoleNotFoundError(f"unknown: {role_id}")
        return self._CARDS[role_id]

    def list_available(self) -> tuple[str, ...]:
        return tuple(sorted(self._CARDS))

    def list_departments(self) -> tuple[DepartmentSummary, ...]:
        return (
            DepartmentSummary("design", "设计", 1),
            DepartmentSummary("engineering", "工程技术", 1),
        )

    def list_by_department(self, department_id: str) -> tuple:
        from lca.contracts.protocols.collaboration.casting.casting import RoleIndexEntry

        return tuple(
            RoleIndexEntry(
                role_id=c.role_id,
                title=c.title,
                department=c.department,
                summary=c.summary,
                emoji=c.emoji,
            )
            for c in self._CARDS.values()
            if c.department == department_id
        )

    def search(self, keyword: str) -> tuple:
        from lca.contracts.protocols.collaboration.casting.casting import RoleIndexEntry

        kw = keyword.lower()
        return tuple(
            RoleIndexEntry(
                role_id=c.role_id,
                title=c.title,
                department=c.department,
                summary=c.summary,
                emoji=c.emoji,
            )
            for c in self._CARDS.values()
            if kw in c.title.lower() or kw in c.summary.lower()
        )


class TestRoleCardResolver:
    def test_protocol_is_runtime_checkable(self) -> None:
        assert isinstance(_StubResolver(), RoleCardResolver)

    def test_resolve_returns_card(self) -> None:
        resolver = _StubResolver()
        card = resolver.resolve("engineering/architect")
        assert card.title == "软件架构师"
        assert card.department == "engineering"
        assert "系统架构" in card.backstory
        assert card.emoji == "🏛️"

    def test_resolve_unknown_raises(self) -> None:
        resolver = _StubResolver()
        with pytest.raises(RoleNotFoundError):
            resolver.resolve("nonexistent/role")

    def test_list_available_returns_sorted_ids(self) -> None:
        resolver = _StubResolver()
        ids = resolver.list_available()
        assert ids == ("design/ux", "engineering/architect")

    def test_role_card_fields_complete(self) -> None:
        card = RoleCard(
            role_id="test/id",
            title="T",
            department="d",
            summary="s",
            backstory="b",
            emoji="e",
        )
        assert card.role_id == "test/id"
        assert card.title == "T"
        assert card.backstory == "b"
