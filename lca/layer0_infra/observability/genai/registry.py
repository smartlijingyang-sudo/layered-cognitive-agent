"""GenAISemanticMapper 注册中心（ADR-0063 PR-10）。

按 event_type 派发 mapper；每个 mapper 是独立插件，
新增事件类型 = 新 mapper 插件 + 在 build_default_registry 末尾追加。
"""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.observability.genai_semantic import GenAISemanticMapper


class GenAISemanticMapperRegistry:
    """按 event_type 索引的 mapper 注册中心。"""

    def __init__(self, initial: Iterable[GenAISemanticMapper] = ()) -> None:
        self._by_event: dict[str, GenAISemanticMapper] = {}
        self._by_kind: dict[str, GenAISemanticMapper] = {}
        for mapper in initial:
            self.register(mapper)

    def register(self, mapper: GenAISemanticMapper) -> None:
        self._by_event[mapper.event_type] = mapper
        self._by_kind.setdefault(mapper.runtime_kind, mapper)

    def for_event(self, stamped: StampedEvent) -> GenAISemanticMapper | None:
        # 优先用 stamped.event_type（RunStore 注入），fallback 到类型名（手工构造）
        event_type = stamped.event_type or type(stamped.event).__name__
        return self._by_event.get(event_type) or self._by_kind.get(
            getattr(stamped.event, "kind", "")
        )

    def all(self) -> Iterable[GenAISemanticMapper]:
        return tuple(self._by_event.values())


def build_default_registry() -> GenAISemanticMapperRegistry:
    """默认注册中心：含 LLM 与 Tool 两个内置 mapper。"""
    from lca.layer0_infra.observability.genai.llm import LlmGenAIMapper
    from lca.layer0_infra.observability.genai.tool import ToolGenAIMapper

    return GenAISemanticMapperRegistry(
        [
            LlmGenAIMapper(),
            ToolGenAIMapper(),
        ]
    )
