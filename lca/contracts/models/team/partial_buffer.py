"""Run partial text buffer — 成员 run 被 deadline 取消时的证据收割通道（ADR-0049）。

Stream 路径把可见文本写入 contextvar；cancel / timeout 时 drain 进 Observation，
不依赖 journal 投影反向当控制输入。
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_partial_chunks: ContextVar[list[str] | None] = ContextVar("lca_run_partial_chunks", default=None)


def begin_partial_buffer() -> Token[list[str] | None]:
    """开启本 run 的 partial 缓冲，返回 reset token。"""
    return _partial_chunks.set([])


def reset_partial_buffer(token: Token[list[str] | None]) -> None:
    """恢复进入 begin 前的 contextvar。"""
    _partial_chunks.reset(token)


def append_run_partial(text: str) -> None:
    """追加一段可见文本（无 active buffer 时静默忽略）。"""
    if not text:
        return
    buf = _partial_chunks.get()
    if buf is None:
        return
    buf.append(text)


def peek_run_partial() -> str:
    """查看当前缓冲（不清空）。"""
    buf = _partial_chunks.get()
    if not buf:
        return ""
    return "".join(buf)


def drain_run_partial() -> str:
    """取出并清空当前缓冲。"""
    buf = _partial_chunks.get()
    if not buf:
        return ""
    text = "".join(buf)
    buf.clear()
    return text
