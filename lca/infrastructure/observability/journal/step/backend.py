"""StepGroupedBackend —— JournalBackend 适配, 让 facade 透明路由到 step-tree。

职责:
    - 实现 JournalBackend.write(event): 兼容旧 facade 入口。 但 step-tree
      时代, 业务层不再调 write(event) —— 直接调 step_lifecycle 模块
      facade(open_step / record_* / close_step)。
    - 持有 StepLifecycleStore 引用, 在 close_document 时把最终 document
      交给 StepGroupedProjector 落盘。
    - 暴露 ``flush_document(document)`` 让 runtime 显式触发落盘。

跟 MemoryJournal 的关系:
    - 共存: 两个 backend 可同时 bind, 各管各的。 facade.record(event) 走
      MemoryJournal(老路径, 暂时仍可用), facade.flush_document() 走
      StepGroupedBackend(新路径)。
    - Phase 3 切换后, MemoryJournal 退化为 debug-only, StepGroupedBackend
      是真值。 Phase 4 删 MemoryJournal。

不做的:
    - 不在 write(event) 里把 event 转成 step。 那是 Phase 3 reasoner / body
      切换的事, facade 不知道 step 边界。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lca.contracts.models.observability.journal import JournalEvent, StampedEvent
from lca.contracts.models.observability.journal_doc import JournalDocument
from lca.contracts.observability.ports import JournalBackend
from lca.infrastructure.observability.journal.step.projector import (
    StepGroupedProjector,
)
from lca.runtime.step_lifecycle import StepLifecycleStore


@dataclass
class StepGroupedBackend(JournalBackend):
    """step-tree 主存储 backend。

    参数:
        output_path: journal.json 落盘路径
        lifecycle_store: 当前 run 的 step_lifecycle store 引用
                      (boot 期绑定, run 期间复用)
    """

    output_path: Path
    lifecycle_store: StepLifecycleStore

    def __post_init__(self) -> None:
        self._projector = StepGroupedProjector(self.output_path)

    @property
    def projector(self) -> StepGroupedProjector:
        return self._projector

    # ── JournalBackend 协议(兼容 facade.record(event) 旧路径) ──

    def write(self, event: JournalEvent) -> StampedEvent | None:
        """旧路径 —— step-tree 时代, 业务层应直接调 step_lifecycle。

        这里 no-op + log warning, 引导调用方迁移。 不会破坏现有 trace。
        """
        import structlog

        _log = structlog.get_logger("lca.observability.step_backend")
        _log.warning(
            "write_to_step_backend_deprecated",
            event_type=type(event).__name__,
            hint="call step_lifecycle.open_step/record_*/close_step directly",
        )
        return None

    def flush(self) -> None:
        """把 lifecycle_store 当前 document 落盘(若已 close_document)。

        safe to call 多次: 第二次发现 store 没 document → no-op。
        """
        doc = self.lifecycle_store.document
        if doc is None:
            return
        if doc.closed_at is None:
            # 还没 close_document → 不写半截
            return
        self._projector.write(doc)

    def close(self) -> None:
        """flush + 资源释放。 step-tree 没有需要释放的文件句柄, 仅 flush。"""
        self.flush()

    # ── 新主路径(给 runtime 显式调) ──

    def write_document(self, document: JournalDocument) -> Path:
        """新主路径 —— 直接写完整 document。 用于 close_document 之后。

        比 flush() 更明确: 调用方传递的 document 一定是要落盘的,
        不依赖 lifecycle_store 的内部状态。
        """
        return self._projector.write(document)


__all__ = ["StepGroupedBackend"]
