"""Gateway 集成测试用的 scripted LLM resolver（测试包注入，gateway 不 import tests）。"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.protocols import LLMAdapter
from tests.harness.modes import scripted_llm_for_mode


@dataclass(frozen=True)
class ScriptedLLMResolver:
    """CI / 无 API Key 环境：通过依赖注入使用确定性 scripted adapter。"""

    def is_available(self) -> bool:
        return True

    def resolve(self, *, mode: str) -> LLMAdapter:
        return scripted_llm_for_mode(mode)
