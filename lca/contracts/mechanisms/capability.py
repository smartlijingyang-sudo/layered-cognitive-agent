"""Capability context — Definition 拥有的活服务键（DSH ctx 的 Python 形态）。

Seam 运行时：
    ctx.mount("llm", LlmService())     # Definition 占据键
    ctx.llm.register("mock", adapter)  # Provider 挂到 Definition
    reasoner = PromptReasoner(ctx.llm) # Consumer 只拿 Definition

Consumer 永不 import Provider。换 Provider 只改挂载，不改 Consumer。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable


class SeamKey(str, Enum):
    """全部能力接缝键。仅可替换后端进此表；编排（Brain/Loop/Team）不是 seam。"""

    LLM = "llm"
    SANDBOX = "sandbox"
    MEMORY = "memory"
    STATE_STORE = "state_store"
    SEARCH = "search"
    TOOLS = "tools"
    TRANSPORT = "transport"
    SKILLS = "skills"
    FILE_STORE = "file_store"
    OBSERVABILITY = "observability"


REQUIRED_SEAM_KEYS: tuple[SeamKey, ...] = tuple(SeamKey)


class MissingCapabilityError(KeyError):
    """ctx 上尚未 mount 该 Definition。"""


@runtime_checkable
class CapabilityContext(Protocol):
    """活接缝上下文：键上只有 Definition 服务。"""

    def mount(self, key: str, service: Any) -> None: ...

    def require(self, key: str) -> Any: ...

    def get(self, key: str) -> Any | None: ...

    def keys(self) -> list[str]: ...
