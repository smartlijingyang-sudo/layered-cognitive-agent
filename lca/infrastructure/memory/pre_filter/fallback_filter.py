"""带断路器 (Circuit Breaker) 与优雅降级的复合记忆门禁策略。"""

from __future__ import annotations

import logging
import os
import time

from lca.contracts.protocols.memory.filter import FilterDecision, MemoryPreFilter
from lca.infrastructure.memory.pre_filter.regex_filter import RegexMemoryFilter
from lca.infrastructure.memory.pre_filter.typesafe_filter import TypeSafeMemoryFilter

logger = logging.getLogger(__name__)


class FallbackMemoryFilter(MemoryPreFilter):
    """带断路器 (Circuit Breaker) 与优雅降级的复合记忆门禁。

    优雅保护机制：
    1. 特性开关：若 LCA_TYPESAFE_ENABLED=false，零网络开销旁路至本地规则；
    2. 凭证检查：未配置 TYPESAFE_API_KEY 时直接走本地规则，不报错；
    3. 断路器（熔断）：若遇 429、QuotaExceeded 或超时异常，熔断进入静默期；
    4. 零阻断 Fail-Soft：主循环绝不抛异常，100% 返回可用判定。
    """

    def __init__(
        self,
        primary: MemoryPreFilter | None = None,
        fallback: MemoryPreFilter | None = None,
        enabled: bool | None = None,
        circuit_breaker_seconds: float | None = None,
    ) -> None:
        from lca.infrastructure.llm_adapter.factory.factory import load_dotenv_if_present

        load_dotenv_if_present()
        self._primary = primary
        self._fallback = fallback if fallback is not None else RegexMemoryFilter()
        if enabled is not None:
            self._enabled = enabled
        else:
            self._enabled = os.getenv("LCA_TYPESAFE_ENABLED", "true").strip().lower() in (
                "true",
                "1",
                "yes",
            )

        if circuit_breaker_seconds is not None:
            self._circuit_breaker_seconds = circuit_breaker_seconds
        else:
            try:
                minutes = float(os.getenv("LCA_TYPESAFE_CIRCUIT_MINUTES", "10"))
                self._circuit_breaker_seconds = minutes * 60.0
            except (ValueError, TypeError):
                self._circuit_breaker_seconds = 600.0

        self._circuit_open_until: float = 0.0

    def is_circuit_open(self) -> bool:
        """检查断路器当前是否处于 OPEN (熔断短路) 状态。"""
        return time.time() < self._circuit_open_until

    async def evaluate(self, text: str) -> FilterDecision:
        if not self._enabled:
            return await self._fallback.evaluate(text)

        if self.is_circuit_open():
            res = await self._fallback.evaluate(text)
            return FilterDecision(
                should_extract=res.should_extract,
                reason=f"circuit_open_fallback:{res.reason}",
                source="circuit_breaker",
                confidence=res.confidence,
            )

        if self._primary is None:
            api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
            if not api_key:
                return await self._fallback.evaluate(text)
            self._primary = TypeSafeMemoryFilter(api_key=api_key)

        try:
            res = await self._primary.evaluate(text)
            if res.should_extract:
                return res
            # ADR-0247 准则：漏报丢记忆不可接受，误报仅多一次 LLM 抽取。
            # 若语义评分略低于阈值，但本地规则命中显式关键词，由本地规则放行。
            fallback_res = await self._fallback.evaluate(text)
            if fallback_res.should_extract:
                return FilterDecision(
                    should_extract=True,
                    reason=f"fallback_cooperative_match:{fallback_res.reason}",
                    source=f"{res.source}+regex",
                    confidence=max(res.confidence, fallback_res.confidence),
                )
            return res
        except Exception as exc:
            logger.warning("TypeSafeMemoryFilter 调用失败或额度耗尽，触发断路器熔断降级: %s", exc)
            self._circuit_open_until = time.time() + self._circuit_breaker_seconds
            res = await self._fallback.evaluate(text)
            return FilterDecision(
                should_extract=res.should_extract,
                reason=f"tripped_circuit_fallback:{res.reason}",
                source="circuit_breaker",
                confidence=res.confidence,
            )


__all__ = ["FallbackMemoryFilter"]
