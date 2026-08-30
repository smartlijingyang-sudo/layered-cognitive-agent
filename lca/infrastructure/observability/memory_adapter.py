"""记忆边界的 OTel 与运行诊断适配器。"""

from __future__ import annotations

from lca.contracts.atoms.enums import MemoryLayer
from lca.contracts.atoms.telemetry import ATTR_HIT, ATTR_MEMORY_LAYER, SpanName
from lca.contracts.models.core.decision import Observation, Reflection
from lca.contracts.models.core.memory import MemoryRecord
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols import MemorySystem
from lca.infrastructure.observability.diagnostic_emitters import record_memory_operation
from lca.infrastructure.observability.facade import span

_MEMORY_LAYER_PERCEIVE = "perceive"
_MEMORY_LAYER_UPDATE = "update"


class TelemetryMemoryAdapter(MemorySystem):
    """装饰器：记忆边界写 OTel span 与 run-scoped diagnostic。"""

    def __init__(self, inner: MemorySystem) -> None:
        self._inner = inner

    @property
    def inner(self) -> MemorySystem:
        """被装饰的记忆系统（组合无损性内省用）。"""
        return self._inner

    async def perceive(self, state: AgentState) -> AgentState:
        with span(SpanName.MEMORY_READ, **{ATTR_MEMORY_LAYER: _MEMORY_LAYER_PERCEIVE}) as handle:
            result = await self._inner.perceive(state)
            hit = bool(result.retrieved_context)
            handle.attributes[ATTR_HIT] = hit
            record_memory_operation(
                "memory.perceive",
                self._inner,
                output={"hit": hit, "record_count": len(result.retrieved_context)},
            )
            return result

    async def update(
        self, state: AgentState, observation: Observation, reflection: Reflection
    ) -> None:
        with span(SpanName.MEMORY_WRITE, **{ATTR_MEMORY_LAYER: _MEMORY_LAYER_UPDATE}):
            await self._inner.update(state, observation, reflection)
        record_memory_operation(
            "memory.update", self._inner, attributes={"layer": _MEMORY_LAYER_UPDATE}
        )

    def query(self, layer: MemoryLayer) -> list[MemoryRecord]:
        with span(SpanName.MEMORY_READ, **{ATTR_MEMORY_LAYER: layer.value}) as handle:
            records = self._inner.query(layer)
            hit = bool(records)
            handle.attributes[ATTR_HIT] = hit
            record_memory_operation(
                "memory.query",
                self._inner,
                attributes={"layer": layer.value},
                output={"hit": hit, "record_count": len(records)},
            )
            return records


__all__ = ["TelemetryMemoryAdapter"]
