"""LoopCursor 默认实现族(ADR-0169 D8 五缝)。

仅暴露 ``InMemoryLoopCursor``(测试替身)+ ``StdLoopCursor``(默认实现)
+ ``StdModelVisibleCapture``(PR-12,LLM 边界 5 件套捕获)
+ ``StdReasonerPromptCapture``(ADR-0175 D1,brain prompt 真值落盘)
+ ``LoopCursorFactory``(PR-14,Profile 装配入口)
+ ``SpineWritePortAdapter`` / ``install_run_cursor`` / ``reset_run_cursor``(PR-1.5,EventSpine → WritePort 协议桥)
+ ``PersistenceCoordinator`` / ``NullPersistenceCoordinator`` / ``FilePersistenceCoordinator``(PR-25,持久化协同);
不暴露任何空实现 cursor 类(ADR-0169 L13,NullLoopCursor 不存在)。
"""

from lca.infrastructure.observability.loop_cursor.bind import (
    SpineWritePortAdapter,
    install_run_cursor,
    reset_run_cursor,
)
from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
from lca.infrastructure.observability.loop_cursor.model_visible_binding import (
    bind_current_capture,
    get_current_model_visible_capture,
    install_model_visible_capture,
    reset_current_capture,
    reset_model_visible_capture,
)
from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
    StdModelVisibleCapture,
)
from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
    FilePersistenceCoordinator,
    NullPersistenceCoordinator,
    PersistenceCoordinator,
)
from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
    CurrentReasonerPrompt,
    bind_current_reasoner_prompt,
    get_current_reasoner_prompt,
    install_reasoner_prompt,
    reset_current_reasoner_prompt,
    reset_reasoner_prompt,
)
from lca.infrastructure.observability.loop_cursor.reasoner_prompt_capture import (
    StdReasonerPromptCapture,
)
from lca.infrastructure.observability.loop_cursor.std import StdLoopCursor

__all__ = [
    "CurrentReasonerPrompt",
    "FilePersistenceCoordinator",
    "InMemoryLoopCursor",
    "LoopCursorFactory",
    "NullPersistenceCoordinator",
    "PersistenceCoordinator",
    "SpineWritePortAdapter",
    "StdLoopCursor",
    "StdModelVisibleCapture",
    "StdReasonerPromptCapture",
    "bind_current_capture",
    "bind_current_reasoner_prompt",
    "get_current_model_visible_capture",
    "get_current_reasoner_prompt",
    "install_model_visible_capture",
    "install_reasoner_prompt",
    "install_run_cursor",
    "reset_current_capture",
    "reset_current_reasoner_prompt",
    "reset_model_visible_capture",
    "reset_reasoner_prompt",
    "reset_run_cursor",
]
