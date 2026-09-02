"""LoopCursor 默认实现族(ADR-0169 D8 五缝)。

仅暴露 ``InMemoryLoopCursor``(测试替身)+ ``StdLoopCursor``(默认实现)
+ ``StdModelVisibleCapture``(PR-12,LLM 边界 5 件套捕获)
+ ``LoopCursorFactory``(PR-14,Profile 装配入口)
+ ``PersistenceCoordinator`` / ``NullPersistenceCoordinator`` / ``FilePersistenceCoordinator``(PR-25,持久化协同);
不暴露 null_loop_cursor(ADR-0169 L13)。
"""

from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
    StdModelVisibleCapture,
)
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
    "StdLoopCursor",
    "StdModelVisibleCapture",
]
