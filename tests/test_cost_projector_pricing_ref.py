"""CostProjector + DefaultCostPricingTable 测试(ADR-0065 PR-6)。

- 同 ledger + 同 pricing_ref → 同 cost(可重复)
- 价格表升级不改写历史(已 emit 的 entry 用旧 ref)
- CostCalculator 找不到 model → 0 cost + 保留 ref + model
- CostProjector 写入 materialization 目录
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.observability.journal import LlmCallCompleted, StampedEvent
from lca.contracts.observability.cost import (
    CostCalculator,
    ModelPricing,
)
from lca.infrastructure.observability.cost.default_pricing import (
    _DEFAULT_PRICING_REF,
    DefaultCostPricingTable,
)
from lca.infrastructure.observability.cost.projector import CostProjector


def _make_event(
    seq: int,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    pricing_ref: str = "",
) -> StampedEvent:
    from lca.contracts.models.observability.journal import RunScope

    return StampedEvent(
        seq=seq,
        ts=0.0,
        scope=RunScope(),
        event=LlmCallCompleted(
            model=model,
            ok=True,
            latency_ms=100,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
        event_type="LlmCallCompleted",
        data={"pricing_ref": pricing_ref} if pricing_ref else {},
    )


def test_cost_calculator_recomputable_with_same_ref() -> None:
    """同一 ledger + 同一 pricing_ref → 同一 cost。"""
    table = DefaultCostPricingTable()
    calc = CostCalculator(table=table, pricing_ref=_DEFAULT_PRICING_REF)
    entry_a = calc.compute(model="gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
    entry_b = calc.compute(model="gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
    assert entry_a.cost_usd == entry_b.cost_usd
    assert entry_a.pricing_ref == entry_b.pricing_ref == _DEFAULT_PRICING_REF


def test_cost_calculator_unknown_model_returns_zero() -> None:
    """未定价 model → cost=0,保留 ref + model 名供审计。"""
    table = DefaultCostPricingTable()
    calc = CostCalculator(table=table, pricing_ref=_DEFAULT_PRICING_REF)
    entry = calc.compute(model="unknown-model", prompt_tokens=1000, completion_tokens=500)
    assert entry.cost_usd == 0.0
    assert entry.model == "unknown-model"
    assert entry.pricing_ref == _DEFAULT_PRICING_REF


def test_pricing_ref_upgrade_does_not_overwrite_history() -> None:
    """升级价目 → 旧 pricing_ref 的 entry 仍按旧价算。"""
    table = DefaultCostPricingTable()
    calc_v1 = CostCalculator(table=table, pricing_ref=_DEFAULT_PRICING_REF)
    entry_v1 = calc_v1.compute(model="gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
    cost_v1 = entry_v1.cost_usd

    # 升级:增加 v2 价格(更便宜)
    table.register_pricings(
        "lca.cost/v2",
        [
            ModelPricing(
                model="gpt-4o-mini",
                input_per_1k=0.0001,
                output_per_1k=0.0004,
                pricing_ref="lca.cost/v2",
            )
        ],
    )
    calc_v2 = CostCalculator(table=table, pricing_ref="lca.cost/v2")
    entry_v2 = calc_v2.compute(model="gpt-4o-mini", prompt_tokens=1000, completion_tokens=500)
    assert entry_v2.cost_usd < cost_v1
    # 旧的 entry 不变
    assert entry_v1.cost_usd == cost_v1
    assert entry_v1.pricing_ref == _DEFAULT_PRICING_REF


def test_cost_projector_accumulates_by_pricing_ref() -> None:
    """CostProjector 按 pricing_ref 分桶累加。"""
    projector = CostProjector(
        calculator=CostCalculator(DefaultCostPricingTable(), pricing_ref=_DEFAULT_PRICING_REF)
    )
    projector.on_event(_make_event(1, "gpt-4o-mini", 1000, 500, _DEFAULT_PRICING_REF))
    projector.on_event(_make_event(2, "gpt-4o-mini", 2000, 1000, _DEFAULT_PRICING_REF))

    assert projector.total_cost(_DEFAULT_PRICING_REF) > 0
    assert projector.total_cost("nonexistent-ref") == 0


def test_cost_projector_ignores_non_llm_events() -> None:
    projector = CostProjector()
    # StampedEvent with non-LlmCallCompleted event
    from lca.contracts.models.observability.journal import (
        AgentRunStarted,
        RunScope,
    )

    non_llm = StampedEvent(
        seq=1,
        ts=0.0,
        scope=RunScope(),
        event=AgentRunStarted(agent_role="r"),
        event_type="AgentRunStarted",
        data={},
    )
    projector.on_event(non_llm)
    assert projector.total_cost() == 0


def test_cost_projector_write_to_materialization(tmp_path: Path) -> None:
    """CostProjector.write() 写到 materialization_dir/cost.json。"""
    projector = CostProjector()
    projector.on_event(_make_event(1, "gpt-4o-mini", 1000, 500, _DEFAULT_PRICING_REF))
    out_dir = tmp_path / "cost-projector" / "v1"
    out = projector.write(out_dir, generator_version="v1")

    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "lca.cost_report/1"
    assert payload["generator_id"] == "cost_projector"
    assert payload["generator_version"] == "v1"
    assert payload["total_usd"] >= 0


def test_pricing_table_default_ref_is_deterministic() -> None:
    table_a = DefaultCostPricingTable()
    table_b = DefaultCostPricingTable()
    assert table_a.current_ref() == table_b.current_ref() == _DEFAULT_PRICING_REF
    assert "deepseek-chat" in table_a.get(_DEFAULT_PRICING_REF)
    assert "gpt-4o-mini" in table_a.get(_DEFAULT_PRICING_REF)


def test_pricing_table_list_refs() -> None:
    table = DefaultCostPricingTable()
    refs = table.list_refs()
    assert _DEFAULT_PRICING_REF in refs
    table.register_pricings("lca.cost/v2", [])
    assert "lca.cost/v2" in table.list_refs()
