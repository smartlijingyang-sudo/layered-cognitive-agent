"""AssistantOwnership Protocol —— 用户↔助理归属关系（ADR-0252 D2/D3）。

归属关系由 LCA 自有数据库控制（开发默认 SQLite ``~/.lca/lca.sqlite3``，
生产可选独立 Postgres 库经 ``LCA_DATABASE_URL`` 注入），LobeHub 后端
不读不写这些表。该域是 REST/run 归属隔离的运行时 SSOT：

- ``bind`` —— 幂等 upsert（``(user_id, assistant_id)`` 主键；同
  ``(user_id, client_id)`` 重复返回既有记录）；
- ``owner_of`` —— 供路由层判断 404/403（读 404 不泄露存在性，写 403）；
- ``assistant_ids_for`` —— ``GET /v1/assistants`` 的列表过滤；
- ``set_agent_id`` —— bridge 注册 LobeHub ``agents`` 行后回填；
- ``set_onboarding_state`` / ``get_onboarding_state`` —— onboarding 状态机。

``manifest.json.user_id`` 是磁盘侧镜像（归属元数据，不进配置面 digest），
查询以本域为 SSOT。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

_ONBOARDING_PENDING = "pending"
_ONBOARDING_AGENT_CREATED = "agent_created"
_ONBOARDING_COMPLETED = "completed"

ONBOARDING_STATES: frozenset[str] = frozenset(
    (_ONBOARDING_PENDING, _ONBOARDING_AGENT_CREATED, _ONBOARDING_COMPLETED)
)


@dataclass(frozen=True)
class UserAssistantBinding:
    """一条用户↔助理归属记录。"""

    user_id: str
    """LobeHub ``users.id``（身份 SSOT），来自可信头，不来自 body。"""

    assistant_id: str
    """LCA 磁盘 Home id（``asst_*``）。"""

    client_id: str
    """前端幂等键；``UNIQUE(user_id, client_id)``。"""

    role_id: str | None = None
    """角色卡 id（``from_role``）。"""

    initial_skills: tuple[str, ...] = ()
    """创建时勾选的 skill_id 列表。"""

    agent_id: str | None = None
    """LobeHub ``agents.id``（``agt_*``），bridge 注册后回填。"""

    status: str = "pending"
    """pending|active|failed；列表只展示 active。"""

    created_at: str = ""
    """ISO-8601；空 = store 落库时生成。"""


@runtime_checkable
class AssistantOwnership(Protocol):
    """用户↔助理归属关系的持久化面。"""

    def ensure_user(
        self,
        user_id: str,
        *,
        username: str | None = None,
        email: str | None = None,
    ) -> None:
        """确保 ``lca_users`` 有该用户行（幂等）。"""

    def bind(self, binding: UserAssistantBinding) -> None:
        """幂等 upsert 归属记录。

        同 ``(user_id, assistant_id)`` 或同 ``(user_id, client_id)`` 的
        重复调用不抛错、不产生第二行。
        """

    def owner_of(self, assistant_id: str) -> str | None:
        """返回 ``assistant_id`` 的 owner；未知返回 ``None``。"""

    def assistant_ids_for(self, user_id: str) -> tuple[str, ...]:
        """返回用户拥有的全部 ``asst_*`` id（已排序）。"""

    def set_agent_id(self, assistant_id: str, agent_id: str) -> None:
        """bridge 注册成功后回填 LobeHub agent id。"""

    def set_onboarding_state(self, user_id: str, state: str) -> None:
        """更新用户 onboarding 状态（pending|agent_created|completed）。"""

    def get_onboarding_state(self, user_id: str) -> str:
        """读取用户 onboarding 状态；未知用户返回 ``pending``。"""


__all__ = [
    "ONBOARDING_STATES",
    "AssistantOwnership",
    "UserAssistantBinding",
]
