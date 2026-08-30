"""DefaultCostPricingTable —— ADR-0065 PR-6 默认价目表。

内置定价覆盖常用模型;价格升级不改写历史(每条 LlmCallCompleted 必须显式
``pricing_ref``)。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lca.contracts.observability.cost import CostPricingTable, ModelPricing

_DEFAULT_PRICING_REF = "lca.cost/v1"


# 默认价目(USD / 1K tokens);pricing_ref=``lca.cost/v1``
_DEFAULT_PRICINGS_V1: tuple[ModelPricing, ...] = (
    ModelPricing(
        model="deepseek-chat",
        input_per_1k=0.00014,
        output_per_1k=0.00028,
        pricing_ref=_DEFAULT_PRICING_REF,
    ),
    ModelPricing(
        model="deepseek-reasoner",
        input_per_1k=0.00055,
        output_per_1k=2.19,
        pricing_ref=_DEFAULT_PRICING_REF,
    ),
    ModelPricing(
        model="gpt-4o",
        input_per_1k=0.0025,
        output_per_1k=0.01,
        pricing_ref=_DEFAULT_PRICING_REF,
    ),
    ModelPricing(
        model="gpt-4o-mini",
        input_per_1k=0.00015,
        output_per_1k=0.0006,
        pricing_ref=_DEFAULT_PRICING_REF,
    ),
    ModelPricing(
        model="qwen3.7-plus",
        input_per_1k=0.0008,
        output_per_1k=0.002,
        pricing_ref=_DEFAULT_PRICING_REF,
    ),
    ModelPricing(
        model="claude-3.5-sonnet",
        input_per_1k=0.003,
        output_per_1k=0.015,
        pricing_ref=_DEFAULT_PRICING_REF,
    ),
)


@dataclass(slots=True)
class DefaultCostPricingTable(CostPricingTable):
    """默认价目表;支持 ``register_pricings(ref, [...])`` 升级版本。"""

    _tables: dict[str, dict[str, ModelPricing]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if _DEFAULT_PRICING_REF not in self._tables:
            self._tables[_DEFAULT_PRICING_REF] = {p.model: p for p in _DEFAULT_PRICINGS_V1}

    def get(self, pricing_ref: str) -> dict[str, ModelPricing]:
        return dict(self._tables.get(pricing_ref, {}))

    def current_ref(self) -> str:
        return _DEFAULT_PRICING_REF

    def list_refs(self) -> tuple[str, ...]:
        return tuple(self._tables.keys())

    def register_pricings(self, pricing_ref: str, pricings: list[ModelPricing]) -> None:
        """新增一个 ``pricing_ref`` 版本;不影响历史成本。"""
        self._tables[pricing_ref] = {p.model: p for p in pricings}


__all__ = [
    "_DEFAULT_PRICING_REF",
    "DefaultCostPricingTable",
]
