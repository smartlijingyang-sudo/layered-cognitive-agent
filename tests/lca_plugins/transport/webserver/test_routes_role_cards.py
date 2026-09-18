"""routes_role_cards unit tests — /v1/role-cards REST surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.contracts.protocols.assistant.role_resolver import (
    DepartmentSummary,
    RoleCard,
    RoleIndexEntry,
    RoleNotFoundError,
)
from lca.plugins.transport.webserver.routes_1.routes_role_cards import (
    get_role_card,
    list_role_card_departments,
    list_role_cards_by_department,
    search_role_cards,
)


@dataclass
class _StubResolver:
    _cards: dict[str, RoleCard]
    _index: list[RoleIndexEntry]

    def resolve(self, role_id: str) -> RoleCard:
        if role_id not in self._cards:
            raise RoleNotFoundError(role_id)
        return self._cards[role_id]

    def list_available(self) -> tuple[str, ...]:
        return tuple(self._cards)

    def list_departments(self) -> tuple[DepartmentSummary, ...]:
        return (
            DepartmentSummary("design", "设计", 1),
            DepartmentSummary("engineering", "工程技术", 2),
        )

    def list_by_department(self, department_id: str) -> tuple[RoleIndexEntry, ...]:
        return tuple(e for e in self._index if e.department == department_id)

    def search(self, keyword: str) -> tuple[RoleIndexEntry, ...]:
        kw = keyword.lower()
        return tuple(
            e for e in self._index
            if kw in e.title.lower() or kw in e.summary.lower()
        )


def _make_request(
    resolver: Any | None,
    *,
    path_params: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
) -> Any:
    class _State:
        role_card_resolver = resolver

    class _App:
        state = _State()

    class _Request:
        app = _App()
        method = "GET"

    req = _Request()
    req.path_params = path_params or {}
    req.query_params = query_params or {}
    return req


_STUB_CARDS = {
    "engineering/arch": RoleCard(
        role_id="engineering/arch",
        title="架构师",
        department="engineering",
        summary="系统设计",
        backstory="# 架构师\n\n你是系统设计专家。",
        emoji="⚙️",
    ),
    "engineering/sre": RoleCard(
        role_id="engineering/sre",
        title="SRE",
        department="engineering",
        summary="可靠性工程",
        backstory="# SRE\n\n你保障系统可靠性。",
        emoji="🔧",
    ),
    "design/ux": RoleCard(
        role_id="design/ux",
        title="UX 设计师",
        department="design",
        summary="用户体验",
        backstory="# UX\n\n你关注用户体验。",
        emoji="🎨",
    ),
}

_STUB_INDEX = [
    RoleIndexEntry(role_id="design/ux", title="UX 设计师", department="design", summary="用户体验", emoji="🎨"),
    RoleIndexEntry(role_id="engineering/arch", title="架构师", department="engineering", summary="系统设计", emoji="⚙️"),
    RoleIndexEntry(role_id="engineering/sre", title="SRE", department="engineering", summary="可靠性工程", emoji="🔧"),
]


@pytest.fixture
def resolver() -> _StubResolver:
    return _StubResolver(_cards=_STUB_CARDS, _index=_STUB_INDEX)


class TestListDepartments:
    @pytest.mark.anyio
    async def test_returns_departments(self, resolver: _StubResolver) -> None:
        req = _make_request(resolver)
        resp = await list_role_card_departments(req)
        assert resp.status_code == 200
        body = resp.body
        import json
        data = json.loads(body)
        assert data["total_roles"] == 3
        assert len(data["departments"]) == 2
        assert data["departments"][0]["department_id"] == "design"

    @pytest.mark.anyio
    async def test_503_without_resolver(self) -> None:
        req = _make_request(None)
        resp = await list_role_card_departments(req)
        assert resp.status_code == 503


class TestListByDepartment:
    @pytest.mark.anyio
    async def test_engineering_has_two_roles(self, resolver: _StubResolver) -> None:
        req = _make_request(resolver, path_params={"department_id": "engineering"})
        resp = await list_role_cards_by_department(req)
        assert resp.status_code == 200
        import json
        data = json.loads(resp.body)
        assert data["count"] == 2
        assert data["roles"][0]["title"] == "架构师"

    @pytest.mark.anyio
    async def test_unknown_department_returns_empty(self, resolver: _StubResolver) -> None:
        req = _make_request(resolver, path_params={"department_id": "nonexistent"})
        resp = await list_role_cards_by_department(req)
        assert resp.status_code == 200
        import json
        data = json.loads(resp.body)
        assert data["count"] == 0


class TestGetRoleCard:
    @pytest.mark.anyio
    async def test_returns_full_card(self, resolver: _StubResolver) -> None:
        req = _make_request(resolver, path_params={"role_id": "engineering/arch"})
        resp = await get_role_card(req)
        assert resp.status_code == 200
        import json
        data = json.loads(resp.body)
        assert data["role_id"] == "engineering/arch"
        assert data["title"] == "架构师"
        assert "系统设计专家" in data["backstory"]
        assert data["emoji"] == "⚙️"

    @pytest.mark.anyio
    async def test_unknown_role_returns_404(self, resolver: _StubResolver) -> None:
        req = _make_request(resolver, path_params={"role_id": "nonexistent/role"})
        resp = await get_role_card(req)
        assert resp.status_code == 404


class TestSearch:
    @pytest.mark.anyio
    async def test_search_by_title(self, resolver: _StubResolver) -> None:
        req = _make_request(resolver, query_params={"q": "架构"})
        resp = await search_role_cards(req)
        assert resp.status_code == 200
        import json
        data = json.loads(resp.body)
        assert data["count"] >= 1
        assert any(r["title"] == "架构师" for r in data["roles"])

    @pytest.mark.anyio
    async def test_search_empty_query_returns_400(self, resolver: _StubResolver) -> None:
        req = _make_request(resolver, query_params={})
        resp = await search_role_cards(req)
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_search_no_match_returns_empty(self, resolver: _StubResolver) -> None:
        req = _make_request(resolver, query_params={"q": "xyznonexistent"})
        resp = await search_role_cards(req)
        assert resp.status_code == 200
        import json
        data = json.loads(resp.body)
        assert data["count"] == 0
