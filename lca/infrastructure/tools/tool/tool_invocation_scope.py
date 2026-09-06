"""当前工具调用 invocation_id 的 ambient 作用域。

SafeExecutor 在执行前分配 id 并 record(ToolStarted)；沙箱工具读取同一 id，
使 ToolStarted → SandboxOutputDelta → ToolInvoked 可关联（Journal-as-Truth）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_tool_invocation_id: ContextVar[str | None] = ContextVar("lca_tool_invocation_id", default=None)


def get_current_tool_invocation_id() -> str | None:
    """读取当前工具调用 id；未在 SafeExecutor 边界内返回 None。"""
    return _tool_invocation_id.get()


@contextmanager
def tool_invocation_scope(invocation_id: str) -> Iterator[str]:
    """绑定当前工具 invocation_id，供适配器/沙箱读取。"""
    token: Token[str | None] = _tool_invocation_id.set(invocation_id)
    try:
        yield invocation_id
    finally:
        _tool_invocation_id.reset(token)
