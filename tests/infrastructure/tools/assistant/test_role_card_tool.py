"""RoleCardListTool tests —— 角色卡目录枚举工具（创建助理向导工具面）。"""

from __future__ import annotations

import asyncio
from typing import Any

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.assistant.role_resolver import DepartmentSummary
from lca.contracts.protocols.collaboration.casting.casting import RoleIndexEntry
from lca.infrastructure.tools.assistant.role_card_tool import RoleCardListTool

_DEPTS = (
    DepartmentSummary(department_id="engineering", label="工程技术", count=30),
    DepartmentSummary(department_id="product", label="产品", count=10),
)

_ENG_ENTRIES = (
    RoleIndexEntry(
        role_id="engineering/engineering-software-architect",
        title="软件架构师",
        department="engineering",
        summary="负责系统架构设计",
        emoji="🏗️",
    ),
    RoleIndexEntry(
        role_id="engineering/engineering-backend-engineer",
        title="后端工程师",
        department="engineering",
        summary="负责后端服务开发",
        emoji="⚙️",
    ),
)

_PRODUCT_ENTRIES = (
    RoleIndexEntry(
        role_id="product/product-manager",
        title="产品经理",
        department="product",
        summary="负责产品规划",
        emoji="📦",
    ),
)

_SEARCH_RESULTS = (
    RoleIndexEntry(
        role_id="engineering/engineering-software-architect",
        title="软件架构师",
        department="engineering",
        summary="负责系统架构设计",
        emoji="🏗️",
    ),
    RoleIndexEntry(
        role_id="product/product-manager",
        title="产品经理",
        department="product",
        summary="负责产品架构规划",
        emoji="📦",
    ),
)


class _FakeResolver:
    """Duck-typing ``RoleCardResolver``：只实现 execute 用到的查询方法。"""

    def __init__(self) -> None:
        self._by_department = {"engineering": _ENG_ENTRIES, "product": _PRODUCT_ENTRIES}
        self._search_results = {"架构": _SEARCH_RESULTS}

    def list_departments(self) -> tuple[DepartmentSummary, ...]:
        return _DEPTS

    def list_by_department(self, department_id: str) -> tuple[RoleIndexEntry, ...]:
        return self._by_department.get(department_id, ())

    def search(self, keyword: str) -> tuple[RoleIndexEntry, ...]:
        return self._search_results.get(keyword, ())


def _execute(tool: RoleCardListTool, args: dict[str, Any]) -> Observation:
    return asyncio.run(tool.execute(args))


def test_no_args_returns_departments() -> None:
    tool = RoleCardListTool(resolver=_FakeResolver())
    obs = _execute(tool, {})
    assert obs.success is True
    departments = obs.payload["departments"]
    assert [d["department_id"] for d in departments] == ["engineering", "product"]
    assert departments[0]["label"] == "工程技术"
    assert departments[0]["count"] == 30


def test_department_returns_roles() -> None:
    tool = RoleCardListTool(resolver=_FakeResolver())
    obs = _execute(tool, {"department": "engineering"})
    assert obs.success is True
    roles = obs.payload["roles"]
    assert [r["role_id"] for r in roles] == [
        "engineering/engineering-software-architect",
        "engineering/engineering-backend-engineer",
    ]
    assert roles[0]["title"] == "软件架构师"
    assert roles[0]["emoji"] == "🏗️"


def test_keyword_searches() -> None:
    tool = RoleCardListTool(resolver=_FakeResolver())
    obs = _execute(tool, {"keyword": "架构"})
    assert obs.success is True
    roles = obs.payload["roles"]
    assert len(roles) == 2
    assert obs.payload["keyword"] == "架构"
    assert obs.payload["department"] is None


def test_keyword_with_department_filters() -> None:
    tool = RoleCardListTool(resolver=_FakeResolver())
    obs = _execute(tool, {"keyword": "架构", "department": "engineering"})
    assert obs.success is True
    roles = obs.payload["roles"]
    assert len(roles) == 1
    assert roles[0]["role_id"] == "engineering/engineering-software-architect"
    assert roles[0]["department"] == "engineering"


def test_unknown_department_returns_empty() -> None:
    tool = RoleCardListTool(resolver=_FakeResolver())
    obs = _execute(tool, {"department": "nonexistent"})
    assert obs.success is True
    assert obs.payload["roles"] == []


def test_resolver_none_returns_failure() -> None:
    tool = RoleCardListTool(resolver=None)
    obs = _execute(tool, {})
    assert obs.success is False
    assert obs.error == "角色卡库不可用（roles/ 缺失或解析失败）"


def test_validate_rejects_non_string_args() -> None:
    tool = RoleCardListTool(resolver=_FakeResolver())
    assert tool.validate({"department": 123}) == "department 必须是非空字符串"
    assert tool.validate({"keyword": 123}) == "keyword 必须是非空字符串"
    assert tool.validate({}) is None
    assert tool.validate({"department": "engineering", "keyword": "架构"}) is None
