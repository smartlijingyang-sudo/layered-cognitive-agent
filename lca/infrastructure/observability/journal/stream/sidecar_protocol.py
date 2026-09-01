"""SidecarHook 接缝 —— 让 JsonlJournalProjector 在事件 / 收尾时回调。

ADR-0164 Phase 4: NarrativeSidecar 已删除(由 StepNarrativeWriter 接管),
仅保留 Protocol 作为扩展接缝。 自定义 sidecar(快照 / metrics) 可实现它。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SidecarHook(Protocol):
    """``JsonlJournalProjector`` 在每条事件 / 收尾时回调。

    实现类只需有 ``name`` 属性 + ``on_event`` + ``finalize`` 两个方法。
    """

    name: str

    def on_event(self, stamped: Any, record: dict[str, Any]) -> None: ...

    def finalize(self) -> None: ...


__all__ = ["SidecarHook"]
