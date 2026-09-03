"""事件总线错误（ADR-0183 / ADR-0183 PR-7 收口）。

机制在以下情况 fail-fast：
- E1：plugin 调 publish 时未在 yaml publishers 白名单 → UnauthorizedPublishError
- E2：plugin 调 subscribe 时未在 yaml subscribers 白名单 → UnauthorizedSubscribeError
- E3：plugin manifest 声明的 event_publishes/event_subscribes 与 yaml 不一致 → AuthMatrixMismatchError
- E4：yaml 中 category 与 contracts Category 闭集不一致 → UnknownCategoryError
- E5：plugin 调 publish/subscribe 时未传 plugin_id → MissingPluginIdentityError
- E6：持久 category 零挂载 sink 且投递策略为 strict（ADR-0184 I2）→ EventNoSinkError

PR-7：EventMechanism 已删除，但 ``EventMechanismError`` 类名保留作为
公开错误基类（业务方已 import 该名）；新错误请直接继承该类。
"""

from __future__ import annotations


class EventMechanismError(Exception):
    """事件总线错误基类（保留旧名以兼容 import）。"""


class UnauthorizedPublishError(EventMechanismError):
    """plugin 未在 yaml publishers 白名单，试图 send 该 category。"""

    def __init__(self, plugin_id: str, category: str) -> None:
        super().__init__(f"plugin {plugin_id!r} 未授权 publish category={category!r}")
        self.plugin_id = plugin_id
        self.category = category


class UnauthorizedSubscribeError(EventMechanismError):
    """plugin 未在 yaml subscribers 白名单，试图 subscribe 该 category。"""

    def __init__(self, plugin_id: str, category: str) -> None:
        super().__init__(f"plugin {plugin_id!r} 未授权 subscribe category={category!r}")
        self.plugin_id = plugin_id
        self.category = category


class AuthMatrixMismatchError(EventMechanismError):
    """plugin manifest 声明的 event_publishes/subscribes 与 yaml SSOT 不一致。"""

    def __init__(
        self, plugin_id: str, *, missing_publish: set[str], missing_subscribe: set[str]
    ) -> None:
        msg_parts: list[str] = [f"plugin {plugin_id!r} manifest 与 yaml SSOT 不一致"]
        if missing_publish:
            msg_parts.append(f"manifest 声明 publish 但 yaml 未授权: {sorted(missing_publish)}")
        if missing_subscribe:
            msg_parts.append(f"manifest 声明 subscribe 但 yaml 未授权: {sorted(missing_subscribe)}")
        super().__init__("; ".join(msg_parts))
        self.plugin_id = plugin_id
        self.missing_publish = missing_publish
        self.missing_subscribe = missing_subscribe


class UnknownCategoryError(EventMechanismError):
    """yaml 中 category 与 contracts Category 闭集不一致。"""

    def __init__(self, category: str, source: str) -> None:
        super().__init__(
            f"未知 category={category!r}（来源 {source!r}）；未在 contracts Category 闭集登记"
        )
        self.category = category
        self.source = source


class UnknownPluginIdError(EventMechanismError):
    """PR-5：yaml token 是 id-form 但不在 EventRegistry catalog。

    双轨迁移期错误面之一：token 既不是可 import 的 class-path，又不在
    已注册的 plugin catalog（id → marker class）内 → 机制 fail-fast，
    不允许"未登记的 id 静默通过"。delete-when 详见
    ``2026-09-04-plugin-universe-single-entry`` PR-5。
    """

    def __init__(self, plugin_id: str, source: str) -> None:
        super().__init__(
            f"未知 plugin id={plugin_id!r}（来源 {source!r}）；"
            "id 不在 EventRegistry catalog，且 class-path 形态 import 失败"
        )
        self.plugin_id = plugin_id
        self.source = source


class MissingPluginIdentityError(EventMechanismError):
    """调 send/subscribe 时未传 plugin_id。"""

    def __init__(self, op: str) -> None:
        super().__init__(f"{op} 必须传 plugin_id；机制按 plugin_id 鉴权")


class EventNoSinkError(EventMechanismError):
    """持久 category 零挂载 sink，且投递策略为 strict（ADR-0184 I2 发送必落）。

    由 ``EventBus._dispatch_sinks`` 上抛：对注册表标记持久（``plane:
    OBSERVABILITY``）的 category，零落盘不是合法终态。发送方收到错误后
    自行决定重试或修复装配；事件不进入 ``_fanout``。
    """

    def __init__(self, category: str) -> None:
        super().__init__(f"持久 category={category!r} 零挂载 sink；I2 发送必落，拒绝静默丢弃")
        self.category = category


__all__ = [
    "AuthMatrixMismatchError",
    "EventMechanismError",
    "EventNoSinkError",
    "MissingPluginIdentityError",
    "UnauthorizedPublishError",
    "UnauthorizedSubscribeError",
    "UnknownCategoryError",
    "UnknownPluginIdError",
]
