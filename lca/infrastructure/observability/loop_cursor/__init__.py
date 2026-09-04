"""LoopCursor 默认实现族(ADR-0169 D8 缝族)。

仅暴露 ``InMemoryLoopCursor``(测试替身)+ ``StdLoopCursor``(默认实现)
+ ``LoopCursorFactory``(PR-14,Profile 装配入口)
+ ``SpineWritePortAdapter`` / ``install_run_cursor`` / ``reset_run_cursor``(PR-1.5,EventSpine → WritePort 协议桥)
+ ``PersistenceCoordinator`` / ``NullPersistenceCoordinator`` / ``FilePersistenceCoordinator``(PR-25,持久化协同);
不暴露任何空实现 cursor 类(ADR-0169 L13,NullLoopCursor 不存在)。

ADR-0185 PR-4:``CurrentReasonerPrompt`` 已迁出至
``lca.plugins.events.hooks.model_visible.reasoner_prompt``;旧 capture 类
一并删除(viewer / replay / explain 改走 spine.jsonl + foldRequestHeader)。
"""

from lca.infrastructure.observability.loop_cursor.bind import (
    SpineWritePortAdapter,
    install_run_cursor,
    reset_run_cursor,
)
from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
    FilePersistenceCoordinator,
    NullPersistenceCoordinator,
    PersistenceCoordinator,
)
from lca.infrastructure.observability.loop_cursor.std import StdLoopCursor

__all__ = [
    "FilePersistenceCoordinator",
    "InMemoryLoopCursor",
    "LoopCursorFactory",
    "NullPersistenceCoordinator",
    "PersistenceCoordinator",
    "SpineWritePortAdapter",
    "StdLoopCursor",
    "install_run_cursor",
    "reset_run_cursor",
]
