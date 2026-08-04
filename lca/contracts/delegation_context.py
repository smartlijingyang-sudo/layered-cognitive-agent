"""跨异步边界传递"当前委派者角色"的显式上下文原语。
背景：AgentTransport.send_task(agent_card, subtask, context_refs) 的签名要与
Google A2A 的 AgentCard 模型保持一致，不能塞入 LCA 内部专用的委派身份字段；
同时 send_task 内部用 asyncio.create_task 异步调度、poll/receive 分离，
调用点与 handler 执行点不在同一次 await 里，无法用普通参数直接传递。
因此选择 contextvars：asyncio.create_task 会拷贝调用时的 Context，
handler 在被调度执行时读到的是"发起 delegate 那一刻"的委派者身份。
这是一个刻意的设计选择，而非遗留副作用——见本文件替代裸 ContextVar 直接 import 的做法，
使其成为可发现、可文档化、可单独测试的公共 API。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_delegator: ContextVar[str] = ContextVar("current_delegator", default="")


def get_current_delegator() -> str:
    """读取当前委派链路里最近一次 set 的委派者角色，无则返回空串。"""
    return _delegator.get()


@contextmanager
def delegator_scope(role: str) -> Iterator[None]:
    """在委派发起点包裹此上下文，确保 asyncio.create_task 拷贝到正确的委派者身份。"""
    token = _delegator.set(role)
    try:
        yield
    finally:
        _delegator.reset(token)
