"""GenAI semantic mapper Protocol（ADR-0063 PR-10）。

每个 mapper 把一类 JournalEvent 映射为 OTel GenAI 属性 dict；
OtelProjector 收到事件后按 type 派发到 mapper 链。

事件 → mapper → OTel 属性
   ↑                          ↑
   └ 自EventDescriptorRegistry  └ registry 排序、failure-isolated
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import StampedEvent


@runtime_checkable
class GenAISemanticMapper(Protocol):
    """把已盖章事件映射为 OTel GenAI 语义属性 dict。"""

    @property
    def event_type(self) -> str:
        """mapper 监听的事件类型名（精确匹配 StampedEvent.event_type）。"""

    @property
    def runtime_kind(self) -> str:
        """运行解释域（plugin/ll/tool/memory/transport/code/permission/retry/error）。"""

    def map(self, stamped: StampedEvent) -> dict[str, str]:
        """返回 OTel 属性 dict；空 dict 表示该事件无 GenAI 属性可映射。"""
