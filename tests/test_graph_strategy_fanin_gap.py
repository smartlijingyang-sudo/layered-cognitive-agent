"""Graph fan-in capability test."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.team.graph import EdgeType, ExecutionGraph, GraphEdge, GraphNode, NodeType
from lca.contracts.protocols import LLMAdapter, TeamStage
from lca.layer3_agent.member_invoke import TransportMemberInvoker
from lca.layer3_agent.orchestration_strategies import GraphStrategy
from lca.layer4_app.api import Agent
from lca.plugins.composer.team_transport import build_team_transport
from tests.support.graph_node_executors import build_default_graph_node_executor_registry


class _LLM(LLMAdapter):
    name = "g"

    async def complete(self, prompt: str, **kwargs):
        import json
        import re

        role_m = re.search(r"ROLE:\s*([^\n]+)", prompt)
        role = role_m.group(1).strip() if role_m else ""
        if "市场" in role:
            r = "MARKET_ANALYSIS"
        elif "定价" in role:
            r = "PRICE_RECOMMENDATION"
        elif "风控" in role or "风险" in role:
            r = "RISK_REVIEW"
        else:
            r = "OK"
        return LLMResponse(
            text=json.dumps({"action_type": "respond", "response_text": r, "confidence": 0.8})
        )

    async def stream(self, prompt: str, **kwargs):
        response = await self.complete(prompt, **kwargs)
        yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)


class TestGraphFanIn(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from lca.layer4_app.api import ensure_default_ctx

        await ensure_default_ctx()

    async def test_parallel_outputs_visible(self):
        llm = _LLM()
        members = [
            Agent(role="市场分析师", goal="", backstory="", tools=[], llm=llm)._agent,
            Agent(role="定价专员", goal="", backstory="", tools=[], llm=llm)._agent,
            Agent(role="风控专员", goal="", backstory="", tools=[], llm=llm)._agent,
        ]
        g = ExecutionGraph()
        g.add_node(GraphNode(id="entry", type=NodeType.ENTRY))
        g.add_node(GraphNode(id="market", type=NodeType.AGENT, config={"role": "市场分析师"}))
        g.add_node(GraphNode(id="pricing", type=NodeType.AGENT, config={"role": "定价专员"}))
        g.add_node(GraphNode(id="risk", type=NodeType.AGENT, config={"role": "风控专员"}))
        g.add_node(GraphNode(id="exit", type=NodeType.EXIT))
        g.add_edge(GraphEdge(source="entry", target="market"))
        g.add_edge(GraphEdge(source="market", target="pricing", type=EdgeType.PARALLEL))
        g.add_edge(GraphEdge(source="market", target="risk", type=EdgeType.PARALLEL))
        g.add_edge(GraphEdge(source="pricing", target="exit"))
        g.add_edge(GraphEdge(source="risk", target="exit"))
        transport = build_team_transport(members)
        stage = TeamStage(members=tuple(members), invoker=TransportMemberInvoker(transport))
        result = await GraphStrategy(
            stage,
            execution_graph=g,
            node_executors=build_default_graph_node_executor_registry(),
        ).run("launch")
        self.assertEqual(result.status, TaskStatus.COMPLETED)
        out = result.output or ""
        self.assertIn("PRICE_RECOMMENDATION", out)
        self.assertIn("RISK_REVIEW", out)


if __name__ == "__main__":
    unittest.main()
