"""默认 Debate 多轮收敛能力测试。"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lca.contracts.enums import TeamProcess
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.protocols import LLMAdapter
from lca.layer4_app.api import Agent, MultiAgentTeam
from lca.layer4_app.defaults import ensure_defaults

ensure_defaults()


def _decision(**kwargs):
    import json

    return json.dumps(kwargs, ensure_ascii=False)


class DebatePricingLLM(LLMAdapter):
    name = "debate-pricing-mock-llm"

    async def complete(self, prompt: str, **kwargs):
        import re

        m = re.search(r"ROLE:\s*([^\n]+)", prompt)
        role = m.group(1).strip() if m else ""
        converging = "Previous proposals" in prompt
        if not converging:
            price = 39.9 if "保守" in role else 59.9
            return _decision(
                action_type="respond", response_text=f"PROPOSAL: ${price}", confidence=0.7
            )
        return _decision(
            action_type="respond", response_text="PROPOSAL: $49.9 折衷", confidence=0.9
        )

    async def stream(self, prompt: str, **kwargs):
        yield await self.complete(prompt)


class TestDebateStrategyCapability(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.llm = DebatePricingLLM()
        self.a = Agent(role="保守派定价策略师", goal="", backstory="", tools=[], llm=self.llm)
        self.b = Agent(role="激进派定价策略师", goal="", backstory="", tools=[], llm=self.llm)

    async def test_default_debate_multi_round(self):
        team = MultiAgentTeam(members=[self.a, self.b], process=TeamProcess.DEBATE, max_rounds=3)
        result = await team.run("请定价")
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(result.total_steps, 2)


if __name__ == "__main__":
    unittest.main()
