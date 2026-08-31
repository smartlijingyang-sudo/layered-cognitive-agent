"""当前 run 用户附件 id 的 ambient 作用域。

CreateRun / 入口把本轮 ``attachment_ids`` 绑到 contextvar；沙箱工具
合并 ambient 与工具参数后挂载到沙箱工作根 ``<原文件名>``，避免依赖模型
再传一遍 id（ADR-0046 意图：上传 → CreateRun → 沙箱挂载）。
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token

_run_attachment_ids: ContextVar[tuple[str, ...]] = ContextVar(
    "lca_run_attachment_ids",
    default=(),
)


def get_current_run_attachment_ids() -> tuple[str, ...]:
    """读取本 run 绑定的附件 id；未 bind 时返回空元组。"""
    return _run_attachment_ids.get()


def merge_attachment_ids(
    explicit: Sequence[str] | None,
    *,
    ambient: Sequence[str] | None = None,
) -> list[str]:
    """合并 ambient 与显式 id，去重且保持顺序（ambient 先，explicit 后）。"""
    ambient_ids = ambient if ambient is not None else get_current_run_attachment_ids()
    merged: list[str] = []
    seen: set[str] = set()
    for raw in (*ambient_ids, *(explicit or ())):
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return merged


@contextmanager
def run_attachment_scope(
    attachment_ids: str | Sequence[str],
) -> Iterator[tuple[str, ...]]:
    """绑定本 run 的用户附件 id,供沙箱工具自动挂载。

    A single :class:`str` is accepted for ergonomic call sites but wrapped in a
    one-element tuple so it is not iterated character-by-character (which is
    what :func:`list` does to a bare string).
    """
    if isinstance(attachment_ids, str):
        normalized: Sequence[str] = (attachment_ids,)
    else:
        normalized = attachment_ids
    cleaned = tuple(merge_attachment_ids(list(normalized), ambient=()))
    token: Token[tuple[str, ...]] = _run_attachment_ids.set(cleaned)
    try:
        yield cleaned
    finally:
        _run_attachment_ids.reset(token)
