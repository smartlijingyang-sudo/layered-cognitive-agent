"""MemoryPreFilter Protocol与FilterDecision契约定义。"""

from __future__ import annotations

from typing import NamedTuple, Protocol, runtime_checkable


class FilterDecision(NamedTuple):
    """前置记忆过滤判定结果。"""

    should_extract: bool
    reason: str
    source: str
    confidence: float


@runtime_checkable
class MemoryPreFilter(Protocol):
    """前置记忆过滤协议。"""

    async def evaluate(self, text: str) -> FilterDecision:
        """评估文本是否包含值得提炼沉淀的长期记忆事实。"""
        ...


__all__ = ["FilterDecision", "MemoryPreFilter"]
