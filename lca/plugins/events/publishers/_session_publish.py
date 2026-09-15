"""Session-required publish helper(ADR-0183 / spec section H).

publisher 单点入口走 ``Session.append``;调用方必须先经
:func:`set_publish_session` / run bind 绑定 Session。无 active Session
时 fail-loud(``MissingPublishSessionError``),不走 EventBus.publish。

设计边界:
- helper 只承载入口路由(Session.append);payload/producer 语义由调用方
  负责,本模块不重写。
- Session.append 接受 ``payload`` 与 ``producer``;返回 :class:`EventRef`
  (ref.category / ref.event_id)。
- Session 与 EventBus 共用 ``EventRegistry.can_publish``(S1);在
  ``session.append`` 前鉴权,避免 active Session 绕过授权。
- 绑定状态:本模块采用 module-level 变量承载 active Session(SPEC section H
  删除 ``_current_session`` ContextVar 后;Task 5 删除该 ContextVar,后续 Task
  把 binding 边界迁到 Body / Run 启动显式注入)。set/reset 仍可调,但仅
  用于 in-process 测试;生产 run 边界走 Body 注入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from lca_kernel.events.bus.bus import EventRef


def _authorize_producer(payload: Any, producer: Any) -> None:
    """Run EventBus S1 authorization before Session.append.

    Uses the same ``EventBus.default().registry.can_publish`` matrix as
    ``EventBus.publish``. Raises ``UnauthorizedPublishError`` on deny.
    Missing plugin identity / category defers to EnvelopeBus / schema checks.
    """
    from lca_kernel.events.bus.bus import EventBus
    from lca_kernel.events.errors.errors import UnauthorizedPublishError

    bus: EventBus[Any] = EventBus.default()  # type: ignore[assignment]
    coerce = getattr(bus, "_coerce_producer", None)
    producer_cls = coerce(producer) if callable(coerce) else producer
    category = getattr(payload, "category", None)
    if category is None or producer_cls is None:
        return
    registry = bus.registry
    if not registry.can_publish(producer_cls, category):
        identifier = getattr(producer_cls, "__name__", str(producer_cls))
        cat_value = getattr(category, "value", category)
        raise UnauthorizedPublishError(identifier, cat_value)


class _PublishSession(Protocol):
    """publisher 单点 Session 接口(协议形态)。

    实现方可以是 session_service、SessionStore、或后续合入的 Session
    facade;只要提供 ``append(payload, *, producer)`` 即可。

    该 Protocol 是 helper 与 Session 实现方的契约;并非 plugin manifest
    的 capability key——避免与现有 yaml 注册路径重复定义。
    """

    def append(
        self,
        payload: Any,
        *,
        producer: Any,
    ) -> EventRef: ...


# Module-level state (SPEC section H: replaced ContextVar ``_current_session``).
# 在 Task 7 Body 注入完成后,本 binding 转为 deprecated;目前保留以让现有测试
# fixture (``set_publish_session(session)``) 仍可调,不留空白失败。
_ACTIVE_SESSION: _PublishSession | None = None


def set_publish_session(
    session: object | None,
) -> Any:
    """设置当前上下文的 active Session。

    SPEC section H:_current_session ContextVar 已删除;本函数保留 module-level
    binding 以兼容现有 ``tests/transport/`` 等 fixture;调用方需自行保证
    单 run 单上下文语义。返回 ``None``(不再返回 reset token,因无 ContextVar)。
    """
    from lca.plugins.session.runtime.bus.facade import as_bus_facade

    global _ACTIVE_SESSION
    _ACTIVE_SESSION = as_bus_facade(session)
    return None


def reset_publish_session(
    token: Any,
) -> None:
    """释放 ``set_publish_session`` 绑定的 Session(token 参数 deprecated)。"""
    del token
    global _ACTIVE_SESSION
    _ACTIVE_SESSION = None


def current_publish_session() -> _PublishSession | None:
    """读取当前 active Session;未绑定返回 ``None``。

    唯一合法的读取入口:``_ACTIVE_SESSION`` 由 :func:`set_publish_session`
    重新赋值,消费方若 ``from ... import _ACTIVE_SESSION`` 只会在 import 时
    取到 ``None`` 快照,永远看不到后续绑定(run bind 在 import 之后)。
    """
    return _ACTIVE_SESSION


def publish_via_session(
    payload: Any,
    *,
    producer: Any,
) -> EventRef:
    """Session.append after S1 auth; require active Session(fail-loud)。

    参数:
    - ``payload``:typed 事件 payload(SpineEventPayload 或其它 EventPayload 子类);
      与 ``EventBus.publish(payload, producer=...)`` 形态一致。
    - ``producer``:publisher plugin class(EventBus 鉴权用)。

    返回:
    :class:`EventRef``——``Session.append`` 回执(runtime Session 由 bus
    facade 从 SessionEvent 合成)。

    抛出:
    ``MissingPublishSessionError``——未绑定 Session(须先
    :func:`set_publish_session` / run bind)。属 ``EventMechanismError``
    族:装饰性 transport emit 可吞;业务 publish 仍 fail-loud。
    ``UnauthorizedPublishError``——S1 registry 拒绝该 producer/category。
    """
    from lca_kernel.events.errors.errors import MissingPublishSessionError

    session = _ACTIVE_SESSION
    if session is None:
        raise MissingPublishSessionError()
    _authorize_producer(payload, producer)
    return session.append(payload, producer=producer)


__all__ = [
    "current_publish_session",
    "publish_via_session",
    "reset_publish_session",
    "set_publish_session",
]
