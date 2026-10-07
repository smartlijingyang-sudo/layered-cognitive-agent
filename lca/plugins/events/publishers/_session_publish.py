"""Session-required publish helper(ADR-0183 / spec section H).

publisher 单点入口走 ``Session.append``;调用方必须先经
:func:`set_publish_session` / run bind 绑定 Session。无 active Session
时 fail-loud(``MissingPublishSessionError``),不走 EnvelopeBus.publish。

设计边界:
- helper 只承载入口路由(Session.append);payload/producer 语义由调用方
  负责,本模块不重写。
- Session.append 接受 ``payload`` 与 ``producer``;返回 :class:`EventRef`
  (ref.category / ref.event_id)。
- Session 与 EnvelopeBus 共用 ``EventRegistry.can_publish``(S1);在
  ``session.append`` 前鉴权,避免 active Session 绕过授权。
- 绑定状态:本模块采用 module-level 变量承载 active Session(SPEC section H
  删除 ``_current_session`` ContextVar 后;Task 5 删除该 ContextVar,后续 Task
  把 binding 边界迁到 Body / Run 启动显式注入)。set/reset 仍可调,但仅
  用于 in-process 测试;生产 run 边界走 Body 注入。
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Protocol, cast

if TYPE_CHECKING:
    from lca_kernel.events.bus.bus import EventRef

    _ACTIVE_SESSION: _PublishSession | None


def _authorize_producer(payload: Any, producer: Any) -> None:
    """Run EnvelopeBus S1 authorization before Session.append.

    Uses the same ``EnvelopeBus.default().registry.can_publish`` matrix as
    ``EnvelopeBus.publish``. Raises ``UnauthorizedPublishError`` on deny.
    Missing plugin identity / category defers to EnvelopeBus / schema checks.
    """
    from lca_kernel.events.bus.bus import EnvelopeBus
    from lca_kernel.events.errors.errors import UnauthorizedPublishError

    bus: EnvelopeBus[Any] = EnvelopeBus.default()
    coerce = getattr(bus, "_coerce_producer", None)
    producer_cls = coerce(producer) if callable(coerce) else producer
    category = getattr(payload, "category", None)
    if category is None or producer_cls is None:
        return
    registry = bus.registry
    # can_publish fail-closes on anything that is not a type/str (its
    # _coerce_plugin maps those to None -> deny). Spell the denial out
    # so the checker sees the declared ``type | str`` parameter.
    allowed = (
        registry.can_publish(producer_cls, category)
        if isinstance(producer_cls, (type, str))
        else False
    )
    if not allowed:
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


# Context-local state backed by ContextVar for true multi-run / asyncio task isolation.
_ACTIVE_SESSION_VAR: contextvars.ContextVar[_PublishSession | None] = contextvars.ContextVar(
    "lca_active_publish_session", default=None
)


def get_active_session() -> _PublishSession | None:
    """获取当前上下文 (asyncio.Task / 线程) 绑定的 active Session。"""
    return _ACTIVE_SESSION_VAR.get()


def set_publish_session(
    session: object | None,
) -> contextvars.Token[_PublishSession | None]:
    """设置当前上下文的 active Session。

    采用 contextvars.ContextVar 保证多协程/并发任务间 Session 隔离。
    返回 ContextVar token，可传给 :func:`reset_publish_session` 恢复上下文。
    """
    from lca.plugins.session.runtime.bus.facade import as_bus_facade

    bound = cast("_PublishSession | None", as_bus_facade(session))
    return _ACTIVE_SESSION_VAR.set(bound)


def reset_publish_session(
    token: Any = None,
) -> None:
    """释放 ``set_publish_session`` 绑定的 Session。

    若传入 token 则尝试 reset；否则将当前上下文重置为 None。
    """
    if isinstance(token, contextvars.Token):
        with contextlib.suppress(ValueError):
            _ACTIVE_SESSION_VAR.reset(token)
            return
    _ACTIVE_SESSION_VAR.set(None)


@contextmanager
def bound_session(session: object | None) -> Iterator[Any]:
    """上下文管理器：为代码块绑定 active publish session 并确保退出后安全重置。"""
    token = set_publish_session(session)
    try:
        yield session
    finally:
        reset_publish_session(token)


def publish_via_session(
    payload: Any,
    *,
    producer: Any,
) -> EventRef:
    """Session.append after S1 auth; require active Session(fail-loud)。

    参数:
    - ``payload``:typed 事件 payload(SpineEventPayload 或其它 EventPayload 子类);
      与 ``EnvelopeBus.publish(payload, producer=...)`` 形态一致。
    - ``producer``:publisher plugin class(EnvelopeBus 鉴权用)。

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

    session = get_active_session()
    if session is None:
        raise MissingPublishSessionError()
    _authorize_producer(payload, producer)
    return session.append(payload, producer=producer)


def __getattr__(name: str) -> Any:
    """兼容旧代码/单测通过 module._ACTIVE_SESSION 读取当前 active session。"""
    if name == "_ACTIVE_SESSION":
        return get_active_session()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "bound_session",
    "get_active_session",
    "publish_via_session",
    "reset_publish_session",
    "set_publish_session",
]
