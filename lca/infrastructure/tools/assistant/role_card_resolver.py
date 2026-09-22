"""FileRoleCardResolver —— 从 roles/ 目录加载角色卡片供助理创建和 REST API 使用。

薄适配器：把既有 ``FileRoleLibrary``（ADR-0042）桥接到助理域
``RoleCardResolver`` Protocol。不引入新解析逻辑，不平行新机制。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from lca.agent.role_library import FileRoleLibrary
from lca.contracts.protocols.assistant.role_resolver import (
    DepartmentSummary,
    RoleCard,
    RoleCardResolver,
    RoleIndexEntry,
)

__all__ = ["FileRoleCardResolver"]

DEPARTMENT_LABELS: dict[str, str] = {
    "academic": "学术研究",
    "architecture": "系统架构",
    "design": "设计",
    "engineering": "工程技术",
    "finance": "金融财务",
    "game-development": "游戏开发",
    "gis": "地理信息",
    "hr": "人力资源",
    "legal": "法务合规",
    "marketing": "市场营销",
    "paid-media": "广告投放",
    "product": "产品",
    "project-management": "项目管理",
    "sales": "销售",
    "security": "安全",
    "spatial-computing": "空间计算",
    "specialized": "综合专业",
    "supply-chain": "供应链",
    "support": "客户支持",
    "testing": "测试",
}


class FileRoleCardResolver(RoleCardResolver):
    """从 ``roles/`` 目录解析角色卡片。

    内部持有 ``FileRoleLibrary`` 实例（扫描一次，缓存全部卡片）。
    所有查询方法委托给库的 ``get`` / ``index``。
    """

    def __init__(self, root: Path | None = None) -> None:
        self._library = FileRoleLibrary(root=root)

    def resolve(self, role_id: str) -> RoleCard:
        return self._library.get(role_id)

    def list_available(self) -> tuple[str, ...]:
        return tuple(entry.role_id for entry in self._library.index())

    def list_departments(self) -> tuple[DepartmentSummary, ...]:
        counts: dict[str, int] = defaultdict(int)
        for entry in self._library.index():
            counts[entry.department] += 1
        return tuple(
            DepartmentSummary(
                department_id=dept_id,
                label=DEPARTMENT_LABELS.get(dept_id, dept_id),
                count=count,
            )
            for dept_id, count in sorted(counts.items())
        )

    def list_by_department(self, department_id: str) -> tuple[RoleIndexEntry, ...]:
        return tuple(
            entry
            for entry in self._library.index()
            if entry.department == department_id
        )

    def search(self, keyword: str) -> tuple[RoleIndexEntry, ...]:
        kw = keyword.lower()
        return tuple(
            entry
            for entry in self._library.index()
            if kw in entry.title.lower() or kw in entry.summary.lower()
        )
