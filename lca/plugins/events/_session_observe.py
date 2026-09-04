"""Session.observe 注册接缝 —— 事件 consumer plugin 迁移（ADR-0186 PR-3f）。

事件 consumer plugin（sinks / subscribers）把 callback 登记进本模块的
进程级观察者目录；当前 Session 在场时立即 ``observe``，缺席时（plugin
boot 常见）只入目录，等 :func:`set_session`（run bind）把目录整表挂上。

生产装配：``profiles/web-standard.yaml`` 固定引入 ``session-runtime``；
per-run Session 由 RunSessionBuilder 经 :func:`set_session` 装载。consumer
boot **不再** 因 Session 缺席而 ``mount_sink`` / ``bus.subscribe``。

所有权：``_current_session`` 与 ``_observer_catalog`` 均由本模块持有；
机制方（per-run Session owner）是 ``set_session`` 唯一调用方。本接缝只做
注册路由，不做鉴权与落盘。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from lca.contracts.event import EventPayload
from lca_kernel.events import EventRef

__all__ = [
    "EventObserverCallback",
    "SessionObserverTarget",
    "clear_observer_catalog",
    "current_session",
    "observer_catalog",
    "register_as_session_observer",
    "set_session",
]

EventObserverCallback = Callable[[EventPayload, EventRef], None]
"""观察者回调签名 —— 与 ``EventBus.subscribe`` 的 ``on_event`` 契约同源。"""


@runtime_checkable
class SessionObserverTarget(Protocol):
    """Session 机制提供的观察面接缝。

    ``observe`` 把 ``callback`` 以 ``plugin`` 名义注册；派发时序、失败
    语义与注销由 Session 机制定义，本 Protocol 只约束注册入口形状。
    """

    def observe(self, plugin: type, callback: EventObserverCallback) -> object: ...


_current_session: SessionObserverTarget | None = None
# plugin marker → callback；boot 写入，set_session 整表挂到当前 Session。
_observer_catalog: dict[type, EventObserverCallback] = {}


def set_session(session: object | None) -> None:
    """装载 / 清空进程级 Session 观察目标，并挂上目录中的全部观察者。

    所有权：机制方（per-run Session owner）是唯一调用方 —— Session 构造
    时装载，teardown 时传 ``None`` 清空。传入不带 ``observe`` 的对象抛
    :class:`TypeError`（fail-loud，禁止静默降级成无观察态）。
    runtime :class:`~lca.plugins.session.runtime.session.Session` 自动包成
    bus Protocol facade（``observe(plugin, callback)``）；已是该形态的对象
    原样装载。

    时序：装载后立即把 :func:`observer_catalog` 中每条挂到新 Session；
    清空只卸当前目标，**不**清目录（下一 run bind 再挂）。
    """
    global _current_session
    if session is None:
        _current_session = None
        return
    from lca.plugins.session.runtime.bus_facade import as_bus_facade

    bound = as_bus_facade(session)
    if not isinstance(bound, SessionObserverTarget):
        msg = f"Session 观察目标必须提供 observe()；got {type(session).__name__}"
        raise TypeError(msg)
    _current_session = bound
    for plugin, callback in tuple(_observer_catalog.items()):
        bound.observe(plugin, callback)


def current_session() -> SessionObserverTarget | None:
    """读进程级 Session 观察目标；未装载返回 ``None``。"""
    return _current_session


def observer_catalog() -> dict[type, EventObserverCallback]:
    """进程级观察者目录快照（plugin → callback）；供测试与诊断。"""
    return dict(_observer_catalog)


def clear_observer_catalog() -> None:
    """清空观察者目录。测试隔离用；生产 boot 后不应调用。"""
    _observer_catalog.clear()


def register_as_session_observer(plugin: type, callback: EventObserverCallback) -> bool:
    """把事件观察者写入目录；Session 在场则立即 observe。

    返回 ``True`` = 当前 Session 在场且已 ``observe``；
    返回 ``False`` = 仅入目录，等下次 :func:`set_session` 挂上。
    同一 ``plugin`` 重复登记覆盖旧 callback（幂等按 marker class）。

    Session 在场时禁止调用方再走 ``mount_sink`` / ``bus.subscribe``。
    Session 在场但 ``observe`` 抛错时上抛（fail-loud）。

    precondition：``plugin`` 是 plugin marker class；``callback`` 符合
    :data:`EventObserverCallback` 签名。
    """
    if not callable(callback):
        raise TypeError(f"observe callback 必须可调用；got {type(callback).__name__}")
    _observer_catalog[plugin] = callback
    session = _current_session
    if session is None:
        return False
    session.observe(plugin, callback)
    return True
