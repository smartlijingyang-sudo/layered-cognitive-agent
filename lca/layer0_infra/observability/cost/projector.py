"""CostProjector —— ADR-0065 §六 / PR-6。

订阅 ``LlmCallCompleted`` 事件累加 cost,按 ``pricing_ref`` 版本分组;输出
``cost.json`` 到 materialization 目录(由外部调用者触发,不挂在 run 关闭
同步路径 —— 0065 §六:"不得被 run 关闭同步地视为完成前提")。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal import LlmCallCompleted, StampedEvent
from lca.contracts.observability.cost import (
    CostCalculator,
    CostEntry,
)
from lca.layer0_infra.observability.cost.default_pricing import DefaultCostPricingTable


@dataclass(slots=True)
class CostProjector:
    """订阅 LlmCallCompleted 累加成本;输出按 model + pricing_ref 分组。"""

    calculator: CostCalculator = field(
        default_factory=lambda: CostCalculator(DefaultCostPricingTable())
    )
    _by_model: dict[str, dict[str, CostEntry]] = field(default_factory=dict)

    def on_event(self, stamped: StampedEvent) -> None:
        event = stamped.event
        if not isinstance(event, LlmCallCompleted):
            return
        # pricing_ref 取 stamped.data['pricing_ref'];缺省用 table.current_ref()
        pricing_ref = ""
        if isinstance(stamped.data, dict):
            pricing_ref = str(stamped.data.get("pricing_ref", "") or "")
        entry = self.calculator.compute(
            model=event.model,
            prompt_tokens=event.prompt_tokens,
            completion_tokens=event.completion_tokens,
            pricing_ref=pricing_ref or None,
        )
        bucket = self._by_model.setdefault(entry.pricing_ref, {})
        existing = bucket.get(event.model)
        if existing is None:
            bucket[event.model] = entry
        else:
            bucket[event.model] = CostEntry(
                model=event.model,
                pricing_ref=entry.pricing_ref,
                cost_usd=existing.cost_usd + entry.cost_usd,
                input_tokens=existing.input_tokens + entry.input_tokens,
                output_tokens=existing.output_tokens + entry.output_tokens,
            )

    def total_cost(self, pricing_ref: str | None = None) -> float:
        """累加 cost;按 pricing_ref 过滤(全 0 时返回 0)。"""
        total = 0.0
        for ref, bucket in self._by_model.items():
            if pricing_ref is not None and ref != pricing_ref:
                continue
            for entry in bucket.values():
                total += entry.cost_usd
        return total

    def render(self) -> dict[str, Any]:
        """生成 cost.json 内容。"""
        return {
            "schema": "lca.cost_report/1",
            "generated_at": time.time(),
            "by_pricing_ref": {
                ref: {
                    "models": {
                        model: {
                            "input_tokens": entry.input_tokens,
                            "output_tokens": entry.output_tokens,
                            "cost_usd": entry.cost_usd,
                            "pricing_ref": entry.pricing_ref,
                        }
                        for model, entry in bucket.items()
                    },
                    "total_usd": sum(e.cost_usd for e in bucket.values()),
                }
                for ref, bucket in self._by_model.items()
            },
            "total_usd": self.total_cost(),
        }

    def write(self, materialization_dir: Path, *, generator_version: str) -> Path:
        """把 cost.json 写到 materialization_dir;带 ledger_high_watermark 等元数据。"""
        materialization_dir.mkdir(parents=True, exist_ok=True)
        payload = self.render()
        payload["generator_id"] = "cost_projector"
        payload["generator_version"] = generator_version
        out = materialization_dir / "cost.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


__all__ = ["CostProjector"]
