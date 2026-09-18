"""RoleCardResolver Protocol —— 助理域角色档案解析（助理创建链路 + REST API）。

把 ``roles/`` 中的角色卡片解析成 ``RoleCard``，供 ``AssistantCatalog.create``
在 ``from_role`` 路径下填充 SOUL.md / profile.json，以及 ``/v1/role-cards``
REST API 的前端消费面。

与组队域 ``RoleLibrary``（``lca.contracts.protocols.collaboration.casting``）
的关系：同一数据源（``roles/`` 目录），同一 ``RoleCard`` 数据类。本 Protocol
是助理域的消费面，不引入新数据形状，不平行新机制。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.contracts.protocols.collaboration.casting.casting import (
    RoleCard,
    RoleIndexEntry,
    RoleNotFoundError,
)

__all__ = [
    "DepartmentSummary",
    "RoleCard",
    "RoleCardResolver",
    "RoleIndexEntry",
    "RoleNotFoundError",
]


@dataclass(frozen=True)
class DepartmentSummary:
    """部门摘要：id + 中文标签 + 角色数量。"""

    department_id: str
    label: str
    count: int


@runtime_checkable
class RoleCardResolver(Protocol):
    """角色档案解析抽象：role_id → RoleCard + 部门/搜索查询。

    实现者从 ``roles/`` 目录加载 Markdown 卡片（复用既有 ``FileRoleLibrary``
    的解析逻辑）。失败语义：未知 role_id 抛 ``RoleNotFoundError``。
    """

    def resolve(self, role_id: str) -> RoleCard:
        """按 role_id 解析角色卡片；不存在抛 ``RoleNotFoundError``。"""
        ...

    def list_available(self) -> tuple[str, ...]:
        """可用 role_id 列表（供前端菜单 / 工具描述使用）。"""
        ...

    def list_departments(self) -> tuple[DepartmentSummary, ...]:
        """按部门聚合的角色摘要（部门 id 升序）。"""
        ...

    def list_by_department(self, department_id: str) -> tuple[RoleIndexEntry, ...]:
        """指定部门下的角色索引（role_id 升序）；未知部门返回空元组。"""
        ...

    def search(self, keyword: str) -> tuple[RoleIndexEntry, ...]:
        """按关键词搜索角色（name / summary 模糊匹配，role_id 升序）。"""
        ...
