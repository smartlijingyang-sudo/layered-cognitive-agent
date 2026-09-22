"""基于 TypeSafe (Jev) System One Noul 原语的语义记忆门禁。"""

from __future__ import annotations

import asyncio
import os

from typesafe_sdk import AsyncTypeSafeClient, Noul

from lca.contracts.protocols.memory.filter import FilterDecision, MemoryPreFilter


class TypeSafeMemoryFilter(MemoryPreFilter):
    """基于 TypeSafe (Jev) System One Noul 原语的语义记忆门禁。"""

    def __init__(
        self,
        api_key: str | None = None,
        threshold: float = 0.50,
        timeout_seconds: float = 1.5,
    ) -> None:
        if api_key is None:
            from lca.infrastructure.llm_adapter.factory.factory import load_dotenv_if_present

            load_dotenv_if_present()
            self._api_key = os.getenv("TYPESAFE_API_KEY", "")
        else:
            self._api_key = api_key
        self._threshold = threshold
        self._timeout_seconds = timeout_seconds

    async def evaluate(self, text: str) -> FilterDecision:
        if not self._api_key:
            raise ValueError("TYPESAFE_API_KEY is not configured")

        async with asyncio.timeout(self._timeout_seconds):
            async with AsyncTypeSafeClient(api_key=self._api_key) as client:
                res = await client.system_one(
                    state={"statement": text},
                    questions={
                        "should_memorize": Noul(
                            instructions=(
                                "该用户陈述是否表达了应当被长期记住的个人身份角色、"
                                "习惯偏好、项目指导方针、系统约束或环境配置？"
                            )
                        )
                    },
                )
                prob = float(res.nouls["should_memorize"].noul)
                should = prob >= self._threshold
                return FilterDecision(
                    should_extract=should,
                    reason=f"noul_prob:{prob:.2f}",
                    source="typesafe",
                    confidence=prob,
                )


__all__ = ["TypeSafeMemoryFilter"]
