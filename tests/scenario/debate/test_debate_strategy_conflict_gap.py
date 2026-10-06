"""默认 Debate 多轮收敛能力测试。"""

from __future__ import annotations

# Scripted/mock run: boots the kernel, so it must pass the reasoner
# fail-loud credential gate (see tests/conftest.py _ensure_no_env).
# The mock/scripted adapter never touches the network; ambient dummy key is enough.
__keep_llm_key__ = True

import unittest

from lca.application.api.api import Agent, Team
from lca.contracts.atoms.enums.enums import LLMStreamEventType
from lca.contracts.models.core.conversation.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.models.team.team.coordination import Debate
from lca.contracts.protocols import LLMAdapter
from tests.support.session_gate_helpers import bound_session


def _decision(**kwargs):
    import json

    return json.dumps(kwargs, ensure_ascii=False)


class DebatePricingLLM(LLMAdapter):
    name = "debate-pricing-mock-llm"

    async def complete(self, prompt: str, **kwargs):
        import re

        # ROLE 行在 system kwarg（prompt 架构迁移）；保留 prompt 回退。
        m = re.search(r"ROLE:\s*([^\n]+)", str(kwargs.get("system") or ""))
        if m is None:
            m = re.search(r"ROLE:\s*([^\n]+)", prompt)
        role = m.group(1).strip() if m else ""
        converging = "Previous proposals" in prompt
        if not converging:
            price = 39.9 if "保守" in role else 59.9
            return LLMResponse(
                text=_decision(
                    action_type="respond", response_text=f"PROPOSAL: ${price}", confidence=0.7
                )
            )
        return LLMResponse(
            text=_decision(
                action_type="respond", response_text="PROPOSAL: $49.9 折衷", confidence=0.9
            )
        )

    async def stream(self, prompt: str, **kwargs):
        response = await self.complete(prompt, **kwargs)
        yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)


class TestDebateStrategyCapability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from lca.application.api.api import ensure_default_ctx

        await ensure_default_ctx()
        self._session_ctx = bound_session()
        self._session_ctx.__enter__()
        self.llm = DebatePricingLLM()
        self.a = Agent(role="保守派定价策略师", goal="", backstory="", tools=[], llm=self.llm)
        self.b = Agent(role="激进派定价策略师", goal="", backstory="", tools=[], llm=self.llm)

    async def asyncTearDown(self):
        self._session_ctx.__exit__(None, None, None)

    async def test_default_debate_multi_round(self):
        team = Team(members=[self.a, self.b], coordination=Debate(max_rounds=3))
        result = await team.run("请定价")
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(result.total_steps, 2)


if __name__ == "__main__":
    unittest.main()
