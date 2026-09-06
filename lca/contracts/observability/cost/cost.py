"""Cost contracts —— ADR-0065 §六 / PR-6。

``LlmCallCompleted`` 必须带 ``pricing_ref``(语义化版本);CostProjector 根据
该版本化价目计算成本。任何"当前默认价格"不得追溯改写历史成本。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ModelPricing:
    """单个模型的价目(USD / 1K tokens)。"""

    model: str
    input_per_1k: float
    output_per_1k: float
    pricing_ref: str = ""
    notes: str = ""


@dataclass(frozen=True)
class CostEntry:
    """单次 LLM 调用的成本计算结果。"""

    model: str
    pricing_ref: str
    cost_usd: float
    input_tokens: int
    output_tokens: int


@runtime_checkable
class CostPricingTable(Protocol):
    """Versioned 价目表;按 ``pricing_ref`` 解析。"""

    def get(self, pricing_ref: str) -> Mapping[str, ModelPricing]:
        """返回该 ``pricing_ref`` 下的所有 ModelPricing。"""

    def current_ref(self) -> str:
        """当前默认 pricing_ref(不应追溯改写历史)。"""

    def list_refs(self) -> tuple[str, ...]:
        """所有已注册 pricing_ref;按注册顺序。"""


@dataclass(frozen=True)
class CostCalculator:
    """纯函数 cost 计算器;由 pricing_ref + 模型 + token 数算 USD。"""

    table: CostPricingTable
    pricing_ref: str = ""

    def compute(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        pricing_ref: str | None = None,
    ) -> CostEntry:
        ref = pricing_ref or self.pricing_ref or self.table.current_ref()
        prices = self.table.get(ref)
        price = prices.get(model)
        if price is None:
            # 未定价 —— 返回 0 cost,保留 model + pricing_ref 以供后续审计
            return CostEntry(
                model=model,
                pricing_ref=ref,
                cost_usd=0.0,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            )
        cost = (prompt_tokens / 1000.0) * price.input_per_1k + (
            completion_tokens / 1000.0
        ) * price.output_per_1k
        return CostEntry(
            model=model,
            pricing_ref=ref,
            cost_usd=cost,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )


__all__ = [
    "CostCalculator",
    "CostEntry",
    "CostPricingTable",
    "ModelPricing",
]
