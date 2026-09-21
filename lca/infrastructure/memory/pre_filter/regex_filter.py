"""基于代词与偏好关键词的本地保底规则策略。"""

from __future__ import annotations

from collections.abc import Sequence

from lca.contracts.protocols.memory.filter import FilterDecision, MemoryPreFilter
from lca.infrastructure.memory.pre_filter.tokens import DEFAULT_MEMORY_TOKENS


class RegexMemoryFilter(MemoryPreFilter):
    """基于硬编码代词/动词元组的保底本地过滤策略。"""

    def __init__(self, tokens: Sequence[str] = DEFAULT_MEMORY_TOKENS) -> None:
        self._tokens = tuple(tokens)

    async def evaluate(self, text: str) -> FilterDecision:
        lowered = text.lower()
        matched = [token for token in self._tokens if token in text or token in lowered]
        if matched:
            return FilterDecision(
                should_extract=True,
                reason=f"matched_tokens:{','.join(matched[:3])}",
                source="regex",
                confidence=0.8,
            )
        return FilterDecision(
            should_extract=False,
            reason="no_tokens_matched",
            source="regex",
            confidence=0.0,
        )


__all__ = ["RegexMemoryFilter"]
