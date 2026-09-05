"""统一发射 helper —— typed session 事件对象 → ``Session.append`` 的唯一出口。

Session 平面只允许一个写入口(``Session.append``)。业务侧持有的 typed
dataclass 事件(:mod:`lca.contracts.harness.memory.events`)经本 helper
转换为 ``(event_type, data)`` 形态入日志:

- ``event_type`` 来自 ``@session_event`` 注册表(``event_type_of``),不手写字符串;
- ``visibility`` 来自事件类的注册档位,不在发射点重复声明;
- ``actor`` 写入事件信封元数据(审计投影)。

失败语义与 ``Session.append`` 一致:词表未注册 / 数据不可 JSON 序列化
在发射点抛错;observer 失败 contained。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from lca.contracts.harness.tasks.session import SessionEvent, event_type_of
from lca_kernel.events.session import SessionProtocol


def emit(
    session: SessionProtocol,
    event_data: Any,
    *,
    actor: str | None = None,
) -> SessionEvent:
    """把一个 typed session 事件对象提交进 Session 日志。

    ``event_data`` 必须是经 ``@session_event`` 注册的 frozen dataclass 实例;
    未注册类型由 ``event_type_of`` 抛错(fail-loud,禁止绕词表发射)。
    """
    event_type = event_type_of(event_data)
    visibility = getattr(type(event_data), "_visibility", "model")
    return session.append(event_type, asdict(event_data), actor=actor, visibility=visibility)


__all__ = ["emit"]
