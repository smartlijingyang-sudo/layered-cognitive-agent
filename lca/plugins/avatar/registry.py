"""Avatar 服务注册表（ADR-0269）。

模块级单例 ``avatar_service_registry`` 维护 assistant_id -> AvatarService 映射：

- ``register`` —— 插件装配（Task 10）注册服务；
- ``get`` —— REST 路由按 assistant_id 解析服务（未注册抛 KeyError → 404）；
- ``current`` / ``current_assistant_id`` —— agent 工具（Task 9）从 run 运行时
  解析当前助理的服务。

``current_assistant_id`` 与 ``lca/plugins/prompts/sections/context.py`` 同源：
两者都消费 run 绑定的 assistant 上下文。本实现委托
``lca.infrastructure.observability.facade.run.ambit.current_assistant_id``
（RunAmbit.assistant_id 来自 session.assistant_id，即 role_profile.extra 中
``assistant_id`` / ``assistant_home_path`` 的同一真值）。未绑定 run 时返回
空串，``current`` 抛 ``RuntimeError("no current assistant")``。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.plugins.avatar.service import AvatarService


class AvatarServiceRegistry:
    """按 assistant_id 注册/解析 AvatarService 的进程内注册表。"""

    def __init__(self) -> None:
        self._services: dict[str, AvatarService] = {}
        self._resolver: Callable[[str], AvatarService] | None = None

    def register(self, assistant_id: str, service: AvatarService) -> None:
        """注册 assistant_id 的 AvatarService（插件装配调用）。"""
        self._services[assistant_id] = service

    def set_resolver(self, resolver: Callable[[str], AvatarService] | None) -> None:
        """设置懒解析器：``get`` 对未注册 assistant_id 回调并缓存结果。

        插件装配（Task 10）用它按任意 assistant_id 懒构造 AvatarService；
        传 ``None`` 清除解析器（测试与插件卸载）。
        """
        self._resolver = resolver

    def get(self, assistant_id: str) -> AvatarService:
        """按 assistant_id 解析服务。

        已注册服务优先；未注册时若存在 resolver，构造并缓存后返回；
        两者都缺时抛 ``KeyError``（REST 路由映射 404）。
        """
        try:
            return self._services[assistant_id]
        except KeyError:
            pass
        if self._resolver is not None:
            service = self._resolver(assistant_id)
            self._services[assistant_id] = service
            return service
        raise KeyError(f"no avatar service registered for assistant: {assistant_id}") from None

    def current_assistant_id(self) -> str:
        """返回当前 run 绑定的 assistant_id；未绑定返回空串。"""
        from lca.infrastructure.observability.facade.run.ambit import (
            current_assistant_id,
        )

        return current_assistant_id()

    def current(self) -> AvatarService:
        """返回当前 run 助理的 AvatarService；未绑定抛 RuntimeError。"""
        assistant_id = self.current_assistant_id()
        if not assistant_id:
            raise RuntimeError("no current assistant")
        return self.get(assistant_id)

    def clear(self) -> None:
        """清空注册表与解析器（测试与插件卸载用）。"""
        self._services.clear()
        self._resolver = None


avatar_service_registry = AvatarServiceRegistry()

__all__ = ["AvatarServiceRegistry", "avatar_service_registry"]
