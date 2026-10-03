"""当前 run 绑定的 assistant id 的 ambient 作用域。

CreateRun / HIL resume 入口把本轮 ``assistant_id`` 绑到 contextvar；
workspace SSOT（``assistant_workspace_root()``）按 run 解析所属 assistant
的 workspace，避免全局 env 把所有 assistant 指到同一个目录。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_run_assistant_id: ContextVar[str] = ContextVar(
    "lca_run_assistant_id",
    default="",
)


def get_current_assistant_id() -> str:
    """读取本 run 绑定的 assistant id；未 bind 时返回空字符串。"""
    return _run_assistant_id.get()


@contextmanager
def run_assistant_scope(assistant_id: str | None) -> Iterator[str]:
    """绑定本 run 的 assistant id，供 workspace SSOT 按 run 解析。"""
    cleaned = (assistant_id or "").strip()
    token: Token[str] = _run_assistant_id.set(cleaned)
    try:
        yield cleaned
    finally:
        _run_assistant_id.reset(token)
